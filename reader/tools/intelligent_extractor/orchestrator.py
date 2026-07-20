import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from config import Config
from tools.extractor import extract_attachment_content
from .merger import merge_context
from .classifier import DocumentClassifier
from .entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    def __init__(self):
        self.classifier = DocumentClassifier()
        self.extractor = EntityExtractor()

    def run(self, email_metadata: Dict[str, Any], email_body: str, attachment_paths: List[Path]) -> Dict[str, Any]:
        """
        Runs the full extraction pipeline for a single email context.
        """
        logger.info("Starting Intelligent Extraction Pipeline...")
        
        # Step 2 & 3: Parse all attachments
        attachments_data = []
        for path in attachment_paths:
            try:
                logger.info(f"Extracting raw text from {path.name}...")
                raw_text = extract_attachment_content(path)
                attachments_data.append({
                    "filename": path.name,
                    "extension": path.suffix.lower(),
                    "raw_text": raw_text
                })
            except Exception as e:
                logger.warning(f"Failed to extract {path.name}: {e}")

        # Step 5: Merge Context
        unified_context = merge_context(email_metadata, email_body, attachments_data)
        
        # Step 4: Classify Document
        logger.info("Classifying document type...")
        classification = self.classifier.classify(unified_context)
        
        # Step 6 & 7: Extract Entities & Detect Conflicts
        logger.info(f"Extracting entities. Intent identified as: {classification.intent}")
        result_json = self.extractor.extract(unified_context, classification.intent)
        
        # 1. Post-process document_type array
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

        # 2. Post-process attachments array with exact MIME types and extraction status
        attachments_list = []
        for att in attachments_data:
            ext = att["extension"]
            mime = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == ".xlsx" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == ".docx" else "application/octet-stream"
            attachments_list.append({
                "filename": att["filename"],
                "type": mime,
                "extracted": bool(att["raw_text"].strip())
            })
        result_json["attachments"] = attachments_list

        # 3. Post-process sender vs buyer/supplier email conflicts
        sender_env = email_metadata.get("sender", "")
        buyer_email = result_json.get("buyer", {}).get("email", "") if isinstance(result_json.get("buyer"), dict) else ""
        if sender_env and buyer_email and buyer_email.lower() not in sender_env.lower():
            if "conflicts" not in result_json or not isinstance(result_json.get("conflicts"), list):
                result_json["conflicts"] = []
            if not any(isinstance(c, dict) and c.get("field") == "sender_vs_buyer_email" for c in result_json["conflicts"]):
                result_json["conflicts"].append({
                    "field": "sender_vs_buyer_email",
                    "email_sender": sender_env,
                    "document_buyer_email": buyer_email,
                    "note": "Envelope sender does not match buyer contact email in document"
                })

        # 4. Add confidence score
        if "confidence_score" not in result_json:
            result_json["confidence_score"] = classification.confidence

        # 5. Run Procurement Completeness Audit
        from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness
        result_json = audit_procurement_completeness(result_json)
            
        # Determine dynamic filename as per user request
        doc_type = result_json.get("intent", classification.intent)
        user_name = result_json.get("buyer", {}).get("contact_name", "") or result_json.get("supplier", {}).get("contact_name", "unknown_user")
        product = "product"
        if result_json.get("items") and len(result_json.get("items")) > 0:
            product = result_json["items"][0].get("description", result_json["items"][0].get("part_number", "product"))
            
        # Clean up string for filename
        clean_user = "".join([c if c.isalnum() else "_" for c in user_name])
        clean_product = "".join([c if c.isalnum() else "_" for c in product])
        filename = f"{doc_type}_{clean_user}_{clean_product}.json".lower()
        
        # Save to outputs
        # 1. Parse sender for username folder using standard format
        sender_raw = email_metadata.get("sender", "unknown_sender")
        import re
        from datetime import datetime
        email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', sender_raw)
        email = email_match.group(0) if email_match else sender_raw.strip().lower()
        prefix = email.split("@")[0].strip() if "@" in email else email
        prefix = "".join(c for c in prefix if c.isalnum() or c in ("-", "_", "."))
        if not prefix:
            prefix = "unknown"
        
        # 2. Parse date for time folder: DD-MM-YYYY-(HH_MM_SS_fff)
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

        time_folder_name = dt.strftime("%d-%m-%Y - (%HH_%MM_%SS)")
        
        output_dir = Config.OUTPUTS_DIR / prefix / time_folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 3. Save JSON
        output_path = output_dir / f"{prefix}_extracted_data.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=4, ensure_ascii=False)
            
        # 4. Generate and save summary.txt
        logger.info("Generating summary of the mail context...")
        try:
            from tools.groq_client import GroqClient
            llm = GroqClient()
            summary_prompt = "Summarize the context and key points of the following email concisely:"
            summary_text = llm.get_completion(summary_prompt, email_body)
        except Exception as e:
            logger.warning(f"Failed to generate summary: {e}")
            summary_text = f"Failed to generate summary. Raw email body:\n\n{email_body}"
            
        summary_path = output_dir / f"{prefix}_summary.txt"
        
        # Format PROCUREMENT VALIDATION section for summary.txt
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
            f.write(f"{summary_text}\n\n")
            f.write("================ PROCUREMENT VALIDATION ================\n\n")
            f.write(f"Procurement Status: {proc_status.get('status', 'N/A')}\n\n")
            f.write(f"Completeness Score: {proc_status.get('completeness_score', 0)}%\n\n")
            f.write(f"Validation: {proc_val.get('status', 'N/A')}\n\n")
            f.write("Missing Procurement Information:\n")
            f.write("\n".join(missing_text_lines) + "\n\n")
            f.write(f"Recommendation:\n{proc_rec}\n")
            
        logger.info(f"Pipeline completed successfully. Saved JSON and summary to {output_dir}")
        return result_json
