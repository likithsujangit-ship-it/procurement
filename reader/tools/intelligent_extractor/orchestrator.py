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

    def run(self, email_metadata: Dict[str, Any], email_body: str, attachment_paths: List[Path]) -> Dict[str, Any]:
        """
        Runs the full extraction pipeline for a single email context.
        State machine: PENDING -> EXTRACTING -> SUCCESS or FAILED.
        Handles multi-file attachment batching.
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

        # Step 5: Merge Context (supporting multi-chunk context strings)
        unified_context = merge_context(email_metadata, email_body, attachments_data)
        
        if isinstance(unified_context, list):
            context_chunks = unified_context
            first_context = context_chunks[0]
        else:
            context_chunks = [unified_context]
            first_context = unified_context

        # Step 4: Classify Document
        logger.info("Classifying document type...")
        classification = self.classifier.classify(first_context)
        
        # Pre-extraction Regex Pass
        logger.info("Running pre-extraction heuristic pass...")
        hints = run_pre_extraction_pass(first_context)
        logger.debug(f"Pre-extracted hints: {hints}")

        # Step 6 & 7: Extract Entities & Detect Conflicts (across chunks)
        logger.info(f"Extracting entities. Intent identified as: {classification.intent}")
        
        merged_items = []
        result_json = None
        for chunk_idx, chunk_ctx in enumerate(context_chunks):
            if chunk_idx > 0:
                logger.info(f"Processing context chunk {chunk_idx + 1}/{len(context_chunks)} for item extraction...")
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

        # Attach per-file extraction issues
        result_json["failed_files"] = failed_files

        # Check extraction_status state machine
        if result_json.get("extraction_status") == "failed" or result_json.get("extraction_failed"):
            result_json["extraction_status"] = "failed"
            fail_reason = result_json.get("failure_reason") or result_json.get("error") or "All LLM model attempts failed"
            result_json["failure_reason"] = fail_reason
            
            logger.error(f"Entity extraction FAILED: {fail_reason}. Zeroing out procurement fields.")
            
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
            
            # Post-process document_type array for SUCCESS state
            if "document_type" not in result_json or not isinstance(result_json.get("document_type"), list) or not result_json["document_type"]:
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

            # Add LLM confidence score for SUCCESS state if missing
            llm_conf = result_json.get("llm_confidence_score")
            if llm_conf is None:
                llm_conf = result_json.get("confidence_score")
            if llm_conf is None:
                llm_conf = classification.confidence
            result_json["llm_confidence_score"] = llm_conf
            if "confidence_score" in result_json:
                result_json.pop("confidence_score", None)

            fallback_used = result_json.get("extracted_with_fallback_model", False)
            model_info = "fallback model" if fallback_used else "primary model"
            logger.info(f"Entity extraction SUCCESS using {model_info}.")

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
                "extraction_incomplete": False
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

        # Run Procurement Completeness Audit
        from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness
        result_json = audit_procurement_completeness(result_json)
            
        # Determine output folder
        sender_raw = email_metadata.get("sender", "unknown_sender")
        email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', sender_raw)
        email = email_match.group(0) if email_match else sender_raw.strip().lower()
        prefix = email.split("@")[0].strip() if "@" in email else email
        prefix = "".join(c for c in prefix if c.isalnum() or c in ("-", "_", "."))
        if not prefix:
            prefix = "unknown"
        
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
        
        # Save JSON
        output_path = output_dir / f"{prefix}_extracted_data.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=4, ensure_ascii=False)
            
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
            
        logger.info(f"Pipeline completed with status '{result_json.get('extraction_status')}'. Saved JSON and summary to {output_dir}")
        return result_json
