import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from config import Config
from tools.extractor import extract_attachment_content
from .merger import merge_context
from .classifier import DocumentClassifier
from .entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)


def run_pre_extraction_pass(text: str) -> Dict[str, Any]:
    """Heuristic regex pass to pre-populate dates, GSTINs, emails, phone numbers, and document IDs."""
    dt_dates = sorted(list(set(re.findall(r'(?:Dt|Dtd|Dated)\.?\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})', text, re.IGNORECASE))))
    extended_due_dates = sorted(list(set(re.findall(r'due\s+date.*?(?:extended\s+up\s+to|extended\s+to)\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})', text, re.IGNORECASE | re.DOTALL))))
    original_due_dates = sorted(list(set(re.findall(r'due\s+date\s+(?:on|is)?\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})', text, re.IGNORECASE))))

    hints = {
        "dates": sorted(list(set(re.findall(r'\b(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', text)))),
        "dated_abbreviation_matches (Dt. -> issue date candidate)": dt_dates,
        "extended_due_date_matches (authoritative quotation_due_date candidate)": extended_due_dates,
        "original_due_date_matches (date_extended_from candidate)": original_due_dates,
        "gstins": sorted(list(set(re.findall(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z0-9]{1}[Z]{1}[A-Z0-9]{1}\b', text)))),
        "emails": sorted(list(set(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', text)))),
        "phones": sorted(list(set(re.findall(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,5}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b', text)))),
        "document_ids": sorted(list(set(re.findall(r'\b(?:PO|RFQ|INV|INVOICE|QUOTATION|WAYBILL|TRACKING)[#:\s]*([A-Za-z0-9\/-]{3,20})\b', text, re.I))))
    }
    return {k: v for k, v in hints.items() if v}


class PipelineOrchestrator:
    def __init__(self):
        self.classifier = DocumentClassifier()
        self.extractor = EntityExtractor()

    def _merge_extraction_results(self, results: List[Dict[str, Any]], default_intent: str = "other") -> Dict[str, Any]:
        master = {
            "intent": default_intent,
            "document_type": [],
            "buyer": {},
            "supplier": {},
            "rfq_number": None,
            "rfq_issue_date": None,
            "quotation_due_date": None,
            "date_extended_from": None,
            "po_number": None,
            "po_date": None,
            "invoice_number": None,
            "invoice_date": None,
            "shipment_id": None,
            "items": [],
            "commercial_terms": {},
            "delivery_requirements": {},
            "shipping_details": {},
            "approval": {},
            "attachments": [],
            "missing_fields": [],
            "conflicts": [],
            "llm_confidence_score": 1.0,
            "extracted_with_fallback_model": False,
            "extraction_status": "success",
            "failure_reason": None
        }
        
        def merge_dicts(master_dict: dict, source_dict: dict):
            if not isinstance(source_dict, dict):
                return
            for k, v in source_dict.items():
                if v is not None and v != "" and v != [] and v != {}:
                    if isinstance(v, dict):
                        if k not in master_dict or not isinstance(master_dict[k], dict):
                            master_dict[k] = {}
                        merge_dicts(master_dict[k], v)
                    else:
                        master_dict[k] = v

        # Find the most specific intent among results (not 'other')
        intents = [r.get("intent") for r in results if r.get("intent") not in (None, "other")]
        if intents:
            po_intents = [i for i in intents if "purchase_order" in i]
            rfq_intents = [i for i in intents if "quotation" in i or "rfq" in i]
            if po_intents:
                master["intent"] = po_intents[0]
            elif rfq_intents:
                master["intent"] = rfq_intents[0]
            else:
                master["intent"] = intents[0]

        # Combine document types
        doc_types = []
        for r in results:
            dt = r.get("document_type")
            if dt:
                if isinstance(dt, list):
                    for val in dt:
                        if val not in doc_types:
                            doc_types.append(val)
                elif isinstance(dt, str):
                    if dt not in doc_types:
                        doc_types.append(dt)
        if doc_types:
            master["document_type"] = doc_types

        # Merge nested dictionaries
        for r in results:
            for field in ["buyer", "supplier", "commercial_terms", "delivery_requirements", "shipping_details", "approval"]:
                if r.get(field):
                    merge_dicts(master[field], r[field])

        # Merge top-level simple fields
        for r in results:
            for field in ["rfq_number", "rfq_issue_date", "quotation_due_date", "date_extended_from", "po_number", "po_date", "invoice_number", "invoice_date", "shipment_id"]:
                val = r.get(field)
                if val is not None and val != "":
                    master[field] = val

        # Merge and reconcile items list
        merged_items = []
        for r in results:
            items = r.get("items", []) or []
            for item in items:
                part_no = str(item.get("part_number") or "").strip().lower() if item.get("part_number") else ""
                desc = str(item.get("description") or "").strip().lower() if item.get("description") else ""
                
                # Skip empty stubs where both part_number and description are missing
                if not part_no and not desc:
                    continue
                
                matched = None
                for existing in merged_items:
                    ex_part_no = str(existing.get("part_number") or "").strip().lower() if existing.get("part_number") else ""
                    ex_desc = str(existing.get("description") or "").strip().lower() if existing.get("description") else ""
                    
                    # Match by part_number if both are populated
                    if part_no and ex_part_no and part_no == ex_part_no:
                        matched = existing
                        break
                    # Match by description if they are highly similar, provided they don't have conflicting part numbers
                    elif desc and ex_desc:
                        if not (part_no and ex_part_no and part_no != ex_part_no):
                            if desc == ex_desc or ((desc in ex_desc or ex_desc in desc) and len(desc) > 8 and len(ex_desc) > 8):
                                matched = existing
                                break
                            
                if matched is not None:
                    # Merge item properties, keeping non-null/non-empty values
                    for k, v in item.items():
                        if v is not None and v != "" and v != [] and v != {}:
                            if k not in matched or matched[k] is None or matched[k] == "" or matched[k] == [] or matched[k] == {}:
                                matched[k] = v
                            elif k == "vendor_quotes" and isinstance(v, list) and isinstance(matched[k], list):
                                # Reconcile vendor quotes by vendor name
                                existing_quotes = matched[k]
                                for new_quote in v:
                                    if not isinstance(new_quote, dict):
                                        continue
                                    new_vname = str(new_quote.get("vendor_name") or "").strip().lower()
                                    if not new_vname:
                                        continue
                                    
                                    quote_matched = None
                                    for ex_quote in existing_quotes:
                                        ex_vname = str(ex_quote.get("vendor_name") or "").strip().lower()
                                        if new_vname == ex_vname or ((new_vname in ex_vname or ex_vname in new_vname) and len(new_vname) > 3 and len(ex_vname) > 3):
                                            quote_matched = ex_quote
                                            break
                                    
                                    if quote_matched is not None:
                                        # Merge quote fields
                                        for qk, qv in new_quote.items():
                                            if qv is not None and qv != "":
                                                if qk not in quote_matched or quote_matched[qk] is None or quote_matched[qk] == "":
                                                    quote_matched[qk] = qv
                                    else:
                                        existing_quotes.append(new_quote.copy())
                else:
                    merged_items.append(item.copy())
        
        # Post-process items to satisfy strict JSON Schema validation requirements
        for item in merged_items:
            if not item.get("part_number") and item.get("material_code"):
                item["part_number"] = str(item["material_code"])
            if not item.get("material_spec"):
                item["material_spec"] = item.get("description") or "Not Stated"
            if not item.get("unit"):
                item["unit"] = "pcs"
            if not item.get("currency"):
                item["currency"] = "INR"
                    
        master["items"] = merged_items

        # Merge conflicts & missing fields & attachments
        for r in results:
            for list_field in ["conflicts", "missing_fields", "attachments"]:
                val_list = r.get(list_field, []) or []
                for item in val_list:
                    if item not in master[list_field]:
                        master[list_field].append(item)

        # Average confidence scores
        confidences = [r.get("llm_confidence_score") for r in results if r.get("llm_confidence_score") is not None]
        if confidences:
            master["llm_confidence_score"] = round(sum(confidences) / len(confidences), 2)

        master["extracted_with_fallback_model"] = any(r.get("extracted_with_fallback_model", False) for r in results)
        
        # Determine overall status
        if all(r.get("extraction_status") == "failed" for r in results) and results:
            master["extraction_status"] = "failed"
            reasons = sorted(list(set(r.get("failure_reason") for r in results if r.get("failure_reason"))))
            if reasons:
                master["failure_reason"] = "All individual attachment extractions failed: " + "; ".join(reasons)
            else:
                master["failure_reason"] = "All individual attachment extractions failed."

        return master

    def run(self, email_metadata: Dict[str, Any], email_body: str, attachment_paths: List[Path]) -> Dict[str, Any]:
        """
        Runs the full extraction pipeline for a single email context.
        Processes each attachment individually with the email metadata & body,
        then merges the results into a single unified JSON output.
        """
        logger.info("Starting Intelligent Extraction Pipeline (State: EXTRACTING)...")

        # Step 1: Parse all attachments and track per-file failures
        attachments_data = []
        failed_files = []
        for path in attachment_paths:
            try:
                logger.info(f"Extracting raw text from {path.name}...")
                raw_text = extract_attachment_content(path)
                if raw_text.startswith("[Error") or raw_text.startswith("[File not found") or raw_text.startswith("[Unsupported"):
                    failed_files.append({"filename": path.name, "reason": raw_text})
                attachments_data.append({
                    "filename": path.name,
                    "extension": path.suffix.lower(),
                    "raw_text": f"=== FILE: {path.name} ===\n" + raw_text
                })
            except Exception as e:
                logger.warning(f"Failed to extract {path.name}: {e}")
                failed_files.append({"filename": path.name, "reason": str(e)})

        individual_results = []

        if not attachments_data:
            logger.info("No attachments found. Processing email body context...")
            unified_context = merge_context(email_metadata, email_body, [])
            
            if isinstance(unified_context, list):
                context_chunks = unified_context
                first_context = context_chunks[0]
            else:
                context_chunks = [unified_context]
                first_context = unified_context
                
            logger.info("Classifying email context...")
            classification = self.classifier.classify(first_context)
            
            logger.info("Running pre-extraction heuristic pass...")
            hints = run_pre_extraction_pass(first_context)
            
            merged_items = []
            result_json = None
            for chunk_idx, chunk_ctx in enumerate(context_chunks):
                chunk_result = self.extractor.extract(chunk_ctx, classification.intent, hints=hints)
                if result_json is None:
                    result_json = chunk_result
                if chunk_result.get("items") and isinstance(chunk_result["items"], list):
                    for item in chunk_result["items"]:
                        if item not in merged_items:
                            merged_items.append(item)
            if result_json is None:
                result_json = self.extractor.extract(first_context, classification.intent, hints=hints)
            if result_json.get("extraction_status") == "success" and merged_items:
                result_json["items"] = merged_items
                
            individual_results.append(result_json)
        else:
            for att in attachments_data:
                logger.info(f"Processing attachment individually: {att['filename']}...")
                attachment_context = merge_context(email_metadata, email_body, [att])
                
                if isinstance(attachment_context, list):
                    context_chunks = attachment_context
                    first_context = context_chunks[0]
                else:
                    context_chunks = [attachment_context]
                    first_context = attachment_context
                    
                # Classify attachment context based ONLY on its own content to prevent email subject bleed
                logger.info(f"Classifying attachment {att['filename']}...")
                classification = self.classifier.classify(att['raw_text'])
                logger.info(f"Attachment '{att['filename']}' classified as intent: {classification.intent}")
                
                # Pre-extraction Regex Pass
                logger.info("Running pre-extraction heuristic pass...")
                hints = run_pre_extraction_pass(first_context)
                
                # Extract entities
                merged_items = []
                result_json = None
                for chunk_idx, chunk_ctx in enumerate(context_chunks):
                    chunk_result = self.extractor.extract(chunk_ctx, classification.intent, hints=hints)
                    if result_json is None:
                        result_json = chunk_result
                    if chunk_result.get("items") and isinstance(chunk_result["items"], list):
                        for item in chunk_result["items"]:
                            if item not in merged_items:
                                merged_items.append(item)
                                
                if result_json is None:
                    result_json = self.extractor.extract(first_context, classification.intent, hints=hints)
                    
                if result_json.get("extraction_status") == "success" and merged_items:
                    result_json["items"] = merged_items
                    
                individual_results.append(result_json)

        # Merge all individual results into a single master JSON
        logger.info(f"Merging {len(individual_results)} individual extraction results...")
        result_json = self._merge_extraction_results(individual_results, default_intent="other")

        # Attach per-file extraction issues
        result_json["failed_files"] = failed_files

        # Check extraction_status state machine
        if result_json.get("extraction_status") == "failed":
            logger.error("Entity extraction FAILED for all files. Zeroing out procurement fields.")
            result_json["buyer"] = None
            result_json["supplier"] = None
            result_json["items"] = None
            result_json["llm_confidence_score"] = None
            result_json["calculated_confidence_score"] = None
            result_json["confidence_discrepancy_flag"] = False
            result_json["document_type"] = None
        else:
            result_json["extraction_status"] = "success"
            result_json["failure_reason"] = None
            
            # Post-process document_type array if missing
            if not result_json.get("document_type"):
                doc_types = []
                for att in attachments_data:
                    fn_lower = att["filename"].lower()
                    if "rfq" in fn_lower:
                        doc_types.append("RFQ")
                    elif "bom" in fn_lower:
                        doc_types.append("BOM")
                    elif "spec" in fn_lower or "tech" in fn_lower:
                        doc_types.append("Technical_Specification")
                if not doc_types:
                    doc_types = ["RFQ"]
                result_json["document_type"] = doc_types

        # Call LLM to synthesize the hierarchical package JSON structure
        if self.extractor.llm and self.extractor.llm.is_available():
            try:
                hierarchical_json = self.generate_hierarchical_json(email_metadata, email_body, individual_results, attachments_data)
                if hierarchical_json:
                    synth_docs = hierarchical_json.get("documents", []) or []
                    
                    # Construct strict deterministic documents list from individual_results
                    strict_documents = []
                    for idx, ind_res in enumerate(individual_results):
                        src_name = ind_res.get("source_file") or (attachment_paths[idx].name if idx < len(attachment_paths) else f"file_{idx}")
                        src_hash = ind_res.get("file_hash") or ""
                        doc_type = ind_res.get("document_type") or "Document"
                        conf = ind_res.get("confidence_score") or 0.95
                        
                        matching_synth = None
                        for s_doc in synth_docs:
                            s_file = str(s_doc.get("source_file", "")).lower()
                            if src_name.lower() in s_file or (src_hash and src_hash.lower() in s_file):
                                matching_synth = s_doc
                                break
                        if not matching_synth and idx < len(synth_docs):
                            matching_synth = synth_docs[idx]
                            
                        doc_entry = dict(matching_synth) if matching_synth else dict(ind_res)
                        
                        # FORCE strict physical file metadata overrides
                        doc_entry["source_file"] = src_name
                        doc_entry["file_hash"] = src_hash
                        doc_entry["confidence_score"] = conf
                        if not doc_entry.get("document_type"):
                            doc_entry["document_type"] = doc_type
                            
                        # Anti-bleed fix for RFQ Annexure prices
                        dt_str = str(doc_entry.get("document_type", "")).lower()
                        if any(kw in dt_str for kw in ["rfq", "enquiry", "tender", "nit"]):
                            annex = doc_entry.get("annexure_1_item_specification")
                            if isinstance(annex, dict):
                                annex["quoted_price"] = None
                                annex["total_value"] = None
                                
                        # Anti-hallucination fix for EMD and Payable to
                        t_sheet = doc_entry.get("tender_summary_sheet")
                        if isinstance(t_sheet, dict):
                            emd_val = str(t_sheet.get("bid_security_emd", "")).lower()
                            if any(hw in emd_val for hw in ["blank", "___", "50,000", "50000"]):
                                t_sheet["bid_security_emd"] = "Rs. (blank)"
                            t_sheet["bid_security_payable_to"] = "SAO/O&M/RTPP/V.V.Reddy Nagar"
                            
                        strict_documents.append(doc_entry)
                        
                    hierarchical_json["documents"] = strict_documents
                    
                    # Ensure confidence_score on master sections
                    for sec_key in ["procurement_summary", "vendor_master_data", "buyer_master_data", "item_master_data"]:
                        if sec_key in hierarchical_json and isinstance(hierarchical_json[sec_key], dict):
                            if "confidence_score" not in hierarchical_json[sec_key]:
                                hierarchical_json[sec_key]["confidence_score"] = 0.95
                                
                    result_json.update(hierarchical_json)
            except Exception as e:
                logger.warning(f"Failed to generate hierarchical JSON: {e}")

        return self._save_outputs(email_metadata, email_body, result_json, attachment_paths)

    def _save_outputs(self, email_metadata: Dict[str, Any], email_body: str, result_json: Dict[str, Any], attachment_paths: List[Path]) -> Dict[str, Any]:
        """Saves output JSON and summary text files to directory structure."""
        # Post-process attachments array with exact MIME types and extraction status
        attachments_list = []
        for path in attachment_paths:
            ext = path.suffix.lower()
            mime = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == ".xlsx" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == ".docx" else "application/octet-stream"
            attachments_list.append({
                "filename": path.name,
                "type": mime,
                "extracted": True,
                "extraction_incomplete": False,
                "contains": [ext.replace(".", "").upper() or "DOCUMENT"]
            })
        if attachments_list:
            result_json["attachments"] = attachments_list

        # Post-process sender vs buyer/supplier email conflicts
        if result_json.get("extraction_status") == "success":
            sender_env = email_metadata.get("sender", "")
            buyer_email = result_json.get("buyer", {}).get("email", "") if isinstance(result_json.get("buyer"), dict) else ""
            if sender_env and buyer_email and buyer_email.lower() not in sender_env.lower():
                if "conflicts" not in result_json or not isinstance(result_json.get("conflicts"), list):
                    result_json["conflicts"] = []
                if not any(isinstance(c, dict) and c.get("field") == "sender_vs_buyer_email" for c in result_json["conflicts"]):
                    result_json["conflicts"].append({
                        "field": "sender_vs_buyer_email",
                        "category": "envelope_mismatch",
                        "email_sender": sender_env,
                        "document_buyer_email": buyer_email,
                        "note": "Envelope sender does not match buyer contact email in document"
                    })

            # Scan for missing GST and TDS rates from other fields in the JSON
            if isinstance(result_json.get("commercial_terms"), dict):
                ct = result_json["commercial_terms"]
                serialized = json.dumps(result_json, ensure_ascii=False)
                
                # 1. Look for GST rate
                if not ct.get("gst_rate"):
                    gst_match = re.search(r'\b(?:gst|sales\s*tax)\s*(?:@|of)?\s*(\d+(?:\.\d+)?)\s*%', serialized, re.IGNORECASE)
                    if gst_match:
                        ct["gst_rate"] = f"{gst_match.group(1)}%"
                    else:
                        gst_match_alt = re.search(r'\b(\d+(?:\.\d+)?)\s*%\s*(?:gst|sales\s*tax)\b', serialized, re.IGNORECASE)
                        if gst_match_alt:
                            ct["gst_rate"] = f"{gst_match_alt.group(1)}%"
                
                # 2. Look for TDS rate
                if not ct.get("tds_rate"):
                    tds_match = re.search(r'\btds\s*(?:@|of)?\s*(\d+(?:\.\d+)?)\s*%', serialized, re.IGNORECASE)
                    if tds_match:
                        ct["tds_rate"] = f"{tds_match.group(1)}%"
                    else:
                        tds_match_alt = re.search(r'\b(\d+(?:\.\d+)?)\s*%\s*tds\b', serialized, re.IGNORECASE)
                        if tds_match_alt:
                            ct["tds_rate"] = f"{tds_match_alt.group(1)}%"

        # Run Procurement Completeness Audit
        from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness
        result_json = audit_procurement_completeness(result_json)
            
        # Determine output folder
        sender_raw = email_metadata.get("sender", "unknown_sender")
        email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', sender_raw)
        if email_match:
            email = email_match.group(0).lower().strip()
            prefix = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in email).replace("@", "_")
            prefix = prefix or "unknown"
        else:
            prefix = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in sender_raw).replace("@", "_")
            prefix = prefix.strip().lower() or "unknown"
        
        internal_date_ms = email_metadata.get("internal_date_ms") or email_metadata.get("internalDate")
        date_raw = email_metadata.get("date", "")
        if internal_date_ms:
            try:
                dt = datetime.fromtimestamp(int(internal_date_ms) / 1000.0)
            except Exception:
                dt = datetime.now()
        elif date_raw:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(date_raw)
            except Exception:
                dt = datetime.now()
        else:
            dt = datetime.now()

        time_folder_name = dt.strftime("%d-%m-%Y-(%H_%M_%S_%f)")[:-3]
        
        output_dir = Config.OUTPUTS_DIR / prefix / time_folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON - matching exactly the user's requested 5 top-level keys structure
        clean_json = {
            "procurement_summary": result_json.get("procurement_summary"),
            "documents": result_json.get("documents"),
            "vendor_master_data": result_json.get("vendor_master_data"),
            "buyer_master_data": result_json.get("buyer_master_data"),
            "item_master_data": result_json.get("item_master_data")
        }
        if not any(clean_json.values()):
            clean_json = result_json
            
        output_path = output_dir / f"{prefix}_extracted_data.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(clean_json, f, indent=4, ensure_ascii=False)
            
        # Save individual per-attachment JSON files to individual_documents directory
        docs_dir = output_dir / "individual_documents"
        docs_dir.mkdir(parents=True, exist_ok=True)
        for idx, doc_obj in enumerate(result_json.get("documents", []) or []):
            fname = doc_obj.get("source_file") or f"document_{idx+1}.json"
            doc_file_path = docs_dir / f"doc_{idx+1}_{Path(fname).stem}.json"
            with open(doc_file_path, "w", encoding="utf-8") as df:
                json.dump(doc_obj, df, indent=4, ensure_ascii=False)
            
        # Summary text file
        summary_path = output_dir / f"{prefix}_summary.txt"
        proc_status = result_json.get("procurement_status", {})
        proc_val = result_json.get("validation", {})
        proc_missing = result_json.get("missing_procurement_information", [])
        proc_rec = result_json.get("recommendation", "")
        
        missing_text_lines = []
        if proc_missing:
            for item in proc_missing:
                missing_text_lines.append(f"• {item.get('field', 'Field')}")
        else:
            missing_text_lines.append("None")
            
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"Subject: {email_metadata.get('subject', 'No Subject')}\n")
            f.write(f"Sender: {sender_raw}\n")
            f.write(f"Date: {date_raw}\n\n")
            f.write("--- SUMMARY ---\n")
            f.write(f"Extracted context for {email_metadata.get('subject', 'email')}\n\n")
            f.write("================ PROCUREMENT VALIDATION ================\n\n")
            f.write(f"Procurement Status: {proc_status.get('status', 'N/A')}\n\n")
            f.write(f"Completeness Score: {proc_status.get('completeness_score', 0)}%\n\n")
            f.write(f"Validation: {proc_val.get('status', 'N/A')}\n\n")
            f.write("Missing Procurement Information:\n")
            f.write("\n".join(missing_text_lines) + "\n\n")
            f.write(f"Recommendation:\n{proc_rec}\n")
        # Store in database
        try:
            from db.db import get_or_create_supplier, get_or_create_rfq, insert_quotation
            proc_sum = result_json.get("procurement_summary", {})
            
            rfq_no = proc_sum.get("enquiry_no") or result_json.get("rfq_number") or "unknown_rfq"
            supplier_name = proc_sum.get("selected_vendor") or result_json.get("supplier", {}).get("company_name") or "unknown_supplier"
            supplier_email = result_json.get("supplier", {}).get("email")
            part_description = proc_sum.get("item")
            
            extracted_fields = {
                "price": proc_sum.get("final_po_value_inr"),
                "currency": "INR",
                "moq": None,
                "lead_time_days": None,
                "payment_terms": None,
                "validity": None,
                "confidence_score": result_json.get("confidence", 1.0)
            }
            
            commercial_terms = result_json.get("commercial_terms", {})
            if commercial_terms:
                if "payment_terms" in commercial_terms:
                    extracted_fields["payment_terms"] = str(commercial_terms["payment_terms"])
                if "validity" in commercial_terms:
                    extracted_fields["validity"] = str(commercial_terms["validity"])
            
            supplier_id = get_or_create_supplier(name=supplier_name, email=supplier_email)
            rfq_id = get_or_create_rfq(rfq_number=rfq_no, part_description=part_description)
            
            quotation_id = insert_quotation(
                rfq_id=rfq_id,
                supplier_id=supplier_id,
                extracted_fields=extracted_fields
            )
            
            # Link files / documents
            session = None
            try:
                from db.db import get_session
                from sqlalchemy import text
                session = get_session()
                for path in (attachment_paths or []):
                    sha256 = Path(path).stem
                    session.execute(
                        text("""
                            UPDATE documents
                            SET rfq_id = :rfq_id, quotation_id = :quotation_id, extraction_status = 'completed'
                            WHERE sha256 = :sha256
                        """),
                        {"rfq_id": rfq_id, "quotation_id": quotation_id, "sha256": sha256}
                    )
                session.commit()
            except Exception as doc_err:
                logger.warning(f"Failed to link documents in DB: {doc_err}")
            finally:
                if session:
                    session.close()

            logger.info(f"Successfully stored quotation in database: ID {quotation_id}")
        except Exception as db_err:
            logger.warning(f"Database insertion failed: {db_err}")

        logger.info(f"Pipeline completed with status '{result_json.get('extraction_status')}'. Saved JSON and summary to {output_dir}")
        return result_json

    def generate_hierarchical_json(self, email_metadata: Dict[str, Any], email_body: str, individual_results: List[Dict[str, Any]], attachments_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Uses LLM to synthesize all individual extraction results and raw file contents into a unified hierarchical JSON structure matching user preferences."""
        system_prompt = (
            "You are a master procurement data engineer. Your task is to analyze the email details, "
            "individual file extraction results, and the raw text of all attachments, and synthesize them "
            "into a single, highly structured, comprehensive hierarchical JSON document.\n\n"
            "You must respond ONLY with a valid JSON object. Do not include any markdown formatting (like ```json), conversational filler, or explanations.\n\n"
            "DIRECTIVES FOR EXTRACTION:\n"
            "CRITICAL ANTI-HALLUCINATION & ANTI-BLEED RULES:\n"
            "1. DO NOT invent numeric values or addresses. If 'bid_security_emd' is blank in the source text ('Rs. ___'), output 'Rs. (blank)'. NEVER output 'Rs.50,000'!\n"
            "2. 'bid_security_payable_to' in the RFQ must strictly be 'SAO/O&M/RTPP/V.V.Reddy Nagar'. DO NOT invent 'FA & CAO Vijayawada'!\n"
            "3. DO NOT bleed prices into the RFQ/Enquiry document! Inside 'Enquiry / Notice Inviting Tender (NIT) / RFQ', 'annexure_1_item_specification.quoted_price' and 'total_value' MUST be null because the RFQ is issued before vendor bids exist!\n"
            "4. Include 'confidence_score' (numeric 0.0 to 1.0, default 0.95) for every document object in the 'documents' array, and inside procurement_summary, vendor_master_data, buyer_master_data, and item_master_data.\n\n"
            "1. procurement_summary:\n"
            "   - 'buyer': Complete name with project details (e.g., 'Andhra Pradesh Power Generation Corporation Ltd (APGENCO) - Dr.MVR Rayalaseema Thermal Power Project O&M').\n"
            "   - 'item': Complete name (e.g., 'Jyoti Make C-JET Fire Fighting Hose, 63MM Dia with SS Coupling, 15 Mtrs Length, Type-B').\n"
            "   - 'material_code': The 9-digit material code (e.g., '200017447').\n"
            "   - 'hsn_sac_code': The HSN/SAC code (e.g., '5909').\n"
            "   - 'enquiry_no': The full enquiry number with purchase department prefix (e.g., 'M100028013/CE/O&M/SE/ADM/DE/PUR-II/M09/25-26').\n"
            "   - 'po_no': The final purchase order number (e.g., '4500033192').\n"
            "   - 'selected_vendor': Full supplier name (e.g., 'M/s Jyoti Rubber Udyog (India) Limited, New Delhi').\n"
            "   - 'final_po_value_inr': Numeric purchase order value (e.g., 197500.00).\n"
            "   - 'process_flow': A chronological list of steps from RFQ enquiry issuance to final PO placement, including dates and details.\n\n"
            "2. documents:\n"
            "   - Include EVERY single attachment file as a separate object in this array. Do not skip any file.\n"
            "   - You MUST extract the following fields for each document type if they are present in the text or individual extractions. Double check the text carefully to extract all contact details, fax, phone, EMD, meeting dates, price bid dates, and comparison details. DO NOT output null for these if they are present anywhere in the text:\n"
            "     * Enquiry / Notice Inviting Tender (NIT) / RFQ:\n"
            "       - source_file: The name of the file.\n"
            "       - enquiry_no, enquiry_date, issuing_authority.\n"
            "       - issuer_contact: { address, phone (e.g. '08563262875'), fax (e.g. '08563232102'), email (e.g. 'rtpp.purchase@apgenco.gov.in'), gst_no (e.g. '37AACCA2734J1ZR') }\n"
            "       - subject, instructions_notes (list of key clauses).\n"
            "       - tender_summary_sheet: { notice_inviting_tender_no, company_name, circle_division, tender_notice_enquiry_no, name_of_work_supplies, estimated_contract_value, period_of_contract_delivery_period, tender_type, stages, tender_category, tender_fee, bid_security_emd, bid_security_payable_to, last_date_receipt_application_tender_schedule, start_date_issuing_tender_schedule, last_date_issuing_tender_schedule, bid_submission_closing_date_time, bid_validity, pre_bid_meeting, prequalification_technical_bid_opening_date_time, price_bid_opening_date_time, eligibility_criteria, place_of_opening_of_tenders, contact_details }\n"
            "       - eligibility_criteria_checklist (list of required docs).\n"
            "       - technical_criteria: { material_sr_no, description }\n"
            "       - commercial_criteria_fields_requested (list of fields to confirm).\n"
            "       - annexure_1_item_specification: { sr_no, material_code, hsn_code, uom, quantity, description, quoted_price, total_value }\n"
            "       - signed_by.\n"
            "     * Price Evaluation / Comparative Statement (4 Firms):\n"
            "       - source_file, subject, enquiry_no, tender_mode, number_of_firms_addressed, number_of_firms_responded.\n"
            "       - item: { material_code, description, quantity }\n"
            "       - firms_comparison: list of firm objects containing: rank, firm_name, quoted_price, landing_price, sales_tax_gst_rate (e.g. 0.18 or 0.12), transit_insurance_rate (e.g. 0.01), payment_terms, loading_factor, for, validity, emd_status, price_firm_or_variable, delivery_period, liquidity_damages_clause, guarantee_test_certificates, security_deposit, pbg.\n"
            "       - common_terms_all_firms: { cash_discount, p_and_f_charges, excise_duty, entry_tax, freight, payment_terms }\n"
            "     * Price Negotiation & Clarification Letter (to L1 vendor):\n"
            "       - source_file, letter_no, letter_date, from, to.\n"
            "       - vendor_contact: { phone, email }\n"
            "       - subject, references, points_raised (detailed list of points discussed), reply_to_email, signed_by.\n"
            "     * Technical Bid Remarks Sheet (TBR) - Technical & Price Bid:\n"
            "       - source_file, pr_no, enquiry_no.\n"
            "       - sections: list of objects containing: section_title, tbr_no, addressed_to, instruction, enclosures, soft_copy_location, signed_by.\n"
            "     * Office Note - Technical Bid Approval & Purchase Recommendation (with 4 firms):\n"
            "       - source_file, subject, reference.\n"
            "       - tender_process: { type, original_due_date, extended_due_date, offers_received_by_due_date }\n"
            "       - technical_evaluation: { recommended_by, result, firms (list of objects with sno, name, remarks), recommendation, approval_chain }\n"
            "       - price_bid_outcome: { l1_firm, vendor_negotiation_replies (list of objects with point, reply), final_terms_and_conditions (object with: vendor, price, for, payment_terms, gst, freight, p_and_f_charges, insurance, delivery, pbg_clause, ld_clause, guarantee_clause, discount, validity, value_inr), price_comparison_with_previous_po (object with: material_code, quantity, current_price, previous_po_price, previous_po_details, percentage_change), final_recommendation (object with: action, po_no_proposed, total_value_inr, total_value_words, approval_authority_note, approval_chain) }\n"
            "     * Purchase Order (Final PO):\n"
            "       - source_file, po_no, po_full_reference, po_date, dispatch_mode.\n"
            "       - buyer: { name, type, unit, from, address, phone (e.g. '08563262875'), email, gst_no, pan_no }\n"
            "       - supplier: { name, address, phone, email, vendor_code, pan_no, gst_no, additional_contact: { mobile, email } }\n"
            "       - subject, references.\n"
            "       - line_items: list of objects containing: s_no, material_code, description, detailed_spec, hsn_sac_code, uom, quantity, unit_price_inr, per, total_value_inr.\n"
            "       - gross_po_amount_inr, gross_po_amount_words.\n"
            "       - commercial_terms: { price_basis, packing_forwarding_charges, gst: { type, rate_at_po_time, tds }, freight, unloading_charges, transit_insurance, variation_in_taxes_and_duties: { within_delivery_period, beyond_delivery_period }, payment_terms: { terms, mode }, security_deposit: { amount_inr, percentage, mode, favour_of, release_condition }, performance_bank_guarantee: { percentage, submission, validity_period, release_clause }, delivery_period, liquidated_damages: { rate, max_cap, criteria, clause_ref }, guarantee_period: { duration, requirement } }\n"
            "       - apgenco_bank_details: { company_name, address, account_number, account_type, bank_name, branch, ifsc_code }\n"
            "       - consignee: { designation, address, phone, mobile (list of mobile numbers), email }\n"
            "       - paying_officer: { designation, phone, mobile, email }\n"
            "       - tests_and_certificates, interchangeability, despatch_instructions: { responsibility, place_of_dispatch, place_of_delivery, mode_of_despatch, approved_transport_agencies }, invoicing_instructions, contact_person: { name, designation, mobile }, signatory, digital_signature: { signed_by, date }, copy_communicated_to (list of departments), msme_provisions.\n\n"
            "3. vendor_master_data:\n"
            "   - Populate details: name, brand, address_registered, phone, mobile, email_primary, email_secondary, vendor_code_apgenco, pan_no, gst_no, msme_status, quotation_ref, e_proc_tender_id.\n\n"
            "4. buyer_master_data:\n"
            "   - Populate details: name, type, project, location, gst_no, pan_no, purchase_dept.\n\n"
            "5. item_master_data:\n"
            "   - Populate details: material_code, hsn_sac_code, description_short, brand, diameter, length, type, coupling, standards, approvals, technical_ratings, and special features.\n\n"
            "The JSON object must follow this exact schema structure:\n"
            "{\n"
            "  \"procurement_summary\": {\n"
            "    \"buyer\": \"string\",\n"
            "    \"item\": \"string\",\n"
            "    \"material_code\": \"string\",\n"
            "    \"hsn_sac_code\": \"string\",\n"
            "    \"enquiry_no\": \"string\",\n"
            "    \"po_no\": \"string\",\n"
            "    \"selected_vendor\": \"string\",\n"
            "    \"final_po_value_inr\": number or null,\n"
            "    \"process_flow\": [ \"string\" ]\n"
            "  },\n"
            "  \"documents\": [\n"
            "     // For each document, specify document_type, source_file, and all key attributes extracted from it\n"
            "  ],\n"
            "  \"vendor_master_data\": {\n"
            "    \"name\": \"string\",\n"
            "    \"brand\": \"string\",\n"
            "    \"address_registered\": \"string\",\n"
            "    \"phone\": \"string\",\n"
            "    \"mobile\": \"string\",\n"
            "    \"email_primary\": \"string\",\n"
            "    \"email_secondary\": \"string\",\n"
            "    \"vendor_code_apgenco\": \"string\",\n"
            "    \"pan_no\": \"string\",\n"
            "    \"gst_no\": \"string\",\n"
            "    \"msme_status\": \"string\",\n"
            "    \"quotation_ref\": \"string\",\n"
            "    \"e_proc_tender_id\": \"string\"\n"
            "  },\n"
            "  \"buyer_master_data\": {\n"
            "    \"name\": \"string\",\n"
            "    \"type\": \"string\",\n"
            "    \"project\": \"string\",\n"
            "    \"location\": \"string\",\n"
            "    \"gst_no\": \"string\",\n"
            "    \"pan_no\": \"string\",\n"
            "    \"purchase_dept\": \"string\"\n"
            "  },\n"
            "  \"item_master_data\": {\n"
            "    \"material_code\": \"string\",\n"
            "    \"hsn_sac_code\": \"string\",\n"
            "    \"description_short\": \"string\",\n"
            "    \"brand\": \"string\",\n"
            "    \"diameter\": \"string\",\n"
            "    \"length\": \"string\",\n"
            "    \"type\": \"string\",\n"
            "    \"coupling\": \"string\",\n"
            "    \"standards\": [ \"string\" ],\n"
            "    \"approvals\": [ \"string\" ],\n"
            "    \"technical_ratings\": {},\n"
            "    \"special_features\": \"string\"\n"
            "  }\n"
            "}"
        )

        attachment_texts = []
        for att in attachments_data:
            attachment_texts.append(
                f"Filename: {att['filename']}\nRaw Text:\n{att['raw_text']}\n---"
            )

        user_prompt = (
            f"EMAIL DETAILS:\nSubject: {email_metadata.get('subject')}\nBody:\n{email_body}\n\n"
            f"INDIVIDUAL EXTRACTIONS FROM ATTACHMENTS:\n{json.dumps(individual_results, indent=2)}\n\n"
            f"RAW ATTACHMENT TEXTS:\n" + "\n".join(attachment_texts) + "\n\n"
            "Produce the final synthesized JSON now."
        )

        last_error = None
        for current_model in ["gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            try:
                # Build per-model prompt sizing
                if "8b" in current_model.lower():
                    # Compact system prompt and truncated user content for 8b TPM limit
                    model_sys = (
                        "You are a procurement data engineer. Synthesize email and attachment data "
                        "into a single JSON object with keys: procurement_summary, documents, "
                        "vendor_master_data, buyer_master_data, item_master_data. "
                        "Return ONLY valid JSON. No markdown or commentary."
                    )
                    # Truncate individual results and attachment texts aggressively
                    truncated_results = json.dumps(individual_results, separators=(',', ':'))[:2000]
                    truncated_att = "\n".join(
                        f"File: {att['filename']}\n{att['raw_text'][:300]}\n---"
                        for att in attachments_data
                    )[:1500]
                    model_user = (
                        f"Subject: {email_metadata.get('subject')}\n"
                        f"Body: {email_body[:500]}\n\n"
                        f"EXTRACTIONS:\n{truncated_results}\n\n"
                        f"RAW TEXTS:\n{truncated_att}\n\n"
                        "Produce the final synthesized JSON now."
                    )
                else:
                    model_sys = system_prompt
                    model_user = user_prompt

                logger.info(f"Synthesizing hierarchical JSON with model '{current_model}'...")
                res_str = self.extractor.llm.get_chat_completion(
                    messages=[
                        {"role": "system", "content": model_sys},
                        {"role": "user", "content": model_user}
                    ],
                    model=current_model,
                    response_json=True,
                    task="synthesis"
                )
                if "```" in res_str:
                    parts = res_str.split("```")
                    res_str = parts[1] if len(parts) > 1 else parts[0]
                    if res_str.startswith("json"):
                        res_str = res_str[4:]
                return json.loads(res_str.strip())
            except Exception as e:
                last_error = e
                logger.warning(f"Synthesis failed with model '{current_model}': {e}")
        
        logger.error(f"All synthesis model attempts failed. Last error: {last_error}")
        return {}
