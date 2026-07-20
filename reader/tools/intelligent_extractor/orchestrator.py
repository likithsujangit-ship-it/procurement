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
        
        # Add metadata manually since we bypassed a single pydantic model
        result_json["confidence_score"] = classification.confidence
            
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
        # 1. Parse sender for username folder
        sender_raw = email_metadata.get("sender", "unknown_sender")
        # Extract email or name
        import re
        from datetime import datetime
        email_match = re.search(r'<([^>]+)>', sender_raw)
        sender_name = email_match.group(1).split('@')[0] if email_match else sender_raw.split('@')[0]
        clean_sender = "".join([c if c.isalnum() else "_" for c in sender_name])
        
        # 2. Parse date for time folder: DD-MM-YYYY-(HH_MM_SS_fff)
        date_raw = email_metadata.get("date", "")
        folder_time = "unknown_date"
        if date_raw:
            try:
                # Typical email date format: "Mon, 20 Jul 2026 12:34:56 +0000" or similar
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(date_raw)
                folder_time = dt.strftime("%d-%m-%Y-(%H_%M_%S_000)")
            except Exception:
                # Fallback if unparseable
                folder_time = "".join([c if c.isalnum() else "_" for c in date_raw])[:25]
        
        output_dir = Config.OUTPUTS_DIR / "intelligent_extraction" / clean_sender / folder_time
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 3. Save JSON
        output_path = output_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=4)
            
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
            
        summary_path = output_dir / "summary.txt"
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"Subject: {email_metadata.get('subject', 'No Subject')}\n")
            f.write(f"Sender: {sender_raw}\n")
            f.write(f"Date: {date_raw}\n\n")
            f.write("--- SUMMARY ---\n")
            f.write(summary_text)
            
        logger.info(f"Pipeline completed successfully. Saved JSON and summary to {output_dir}")
        return result_json
