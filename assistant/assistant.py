"""
Main Orchestrator Entry Point for the Unified AI Assistant.
Integrates Sender and Reader modules to handle cross-project instructions,
such as reading mail, downloading files, performing OCR, and drafting replies.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

# Setup path configuration and imports via config
import assistant.config as ast_config
from assistant.config import import_sender_module, import_reader_module

# 1. Dynamically import Sender Tools
sender_parser_mod = import_sender_module("tools.parser")
sender_validator_mod = import_sender_module("tools.validator")
sender_gen_mod = import_sender_module("tools.email_generator")
sender_send_mod = import_sender_module("tools.email_sender")

parse_natural_language_command = sender_parser_mod.parse_natural_language_command
validate_email = sender_validator_mod.validate_email
validate_attachments = sender_validator_mod.validate_attachments
EmailAIValidationError = sender_validator_mod.EmailAIValidationError
generate_email_content = sender_gen_mod.generate_email_content
send_email = sender_send_mod.send_email
EmailAISendError = sender_send_mod.EmailAISendError

# 2. Dynamically import Reader Tools
reader_auth_mod = import_reader_module("tools.gmail_auth")
reader_read_mod = import_reader_module("tools.gmail_reader")
reader_dl_mod = import_reader_module("tools.attachment_downloader")
reader_links_mod = import_reader_module("tools.link_extractor")
reader_ext_mod = import_reader_module("tools.extractor")
reader_sum_mod = import_reader_module("tools.summarizer")
reader_groq_mod = import_reader_module("tools.groq_client")
reader_utils_mod = import_reader_module("tools.utils")

get_gmail_service = reader_auth_mod.get_gmail_service
GmailAuthError = reader_auth_mod.GmailAuthError
build_search_query = reader_read_mod.build_search_query
fetch_emails = reader_read_mod.fetch_emails
download_all_attachments = reader_dl_mod.download_all_attachments
extract_resources = reader_links_mod.extract_resources
extract_attachment_content = reader_ext_mod.extract_attachment_content
summarize_email = reader_sum_mod.summarize_email
save_extraction_outputs = reader_sum_mod.save_extraction_outputs
GroqClient = reader_groq_mod.GroqClient
setup_logger = reader_utils_mod.setup_logger
reader_search_mod = import_reader_module("tools.search_engine")
SearchEngine = reader_search_mod.SearchEngine
reader_intelligent_mod = import_reader_module("tools.intelligent_extractor")
PipelineOrchestrator = reader_intelligent_mod.PipelineOrchestrator
reader_validate_mod = import_reader_module("tools.intelligent_extractor.validate_extraction")
validate_extraction = reader_validate_mod.validate_extraction

# Import router which is part of assistant
from assistant.router import route_instruction

logger = setup_logger("assistant")


def print_banner() -> None:
    """Prints a premium style CLI ASCII banner."""
    print("=" * 80)
    print("                     UNIFIED EMAIL & DOCUMENT AI ASSISTANT                      ")
    print("=" * 80)
    print("Welcome! I can send emails, read your inbox, summarize documents, and OCR files.")
    print("Examples:")
    print("  - Send mail to manager regarding progress report saying I finished the task.")
    print("  - Summarize latest mail from boss@corp.com.")
    print("  - Download latest attachments from hr@gmail.com.")
    print("  - Extract document invoice_789.pdf.")
    print("  - Summarize resume.docx.")
    print("Type 'exit' or 'quit' to terminate.")
    print("=" * 80)


class UnifiedAssistant:
    """Orchestrator class that handles dispatching commands to specific modules."""

    def __init__(self) -> None:
        self.gmail_service = None

    def _ensure_gmail_service(self) -> Any:
        """Lazily authenticates and returns the Gmail service API."""
        if not self.gmail_service:
            print("Connecting to Gmail API...")
            self.gmail_service = get_gmail_service()
        return self.gmail_service

    def handle_send_email(self, instruction: str) -> None:
        """Executes email sending workflow using Sender tools."""
        print("\n--> Launching Email Sender...")
        try:
            # Reuse logic from sender main
            parsed = parse_natural_language_command(instruction)
            recipients = parsed.get("recipients", [])
            if not recipients:
                print("Error: No recipients identified in instruction.")
                return

            for r in recipients:
                validate_email(r, "recipients")
            
            attachments = parsed.get("attachments", [])
            paths = []
            for name in attachments:
                sender_file = ast_config.SENDER_DIR / "files" / name
                reader_file = ast_config.READER_DIR / "files" / name
                if sender_file.exists():
                    paths.append(sender_file)
                elif reader_file.exists():
                    paths.append(reader_file)
                else:
                    paths.append(sender_file)
                    
            validated_paths = validate_attachments([p.name for p in paths])
            
            email_content = generate_email_content(
                subject_hint=parsed.get("subject_hint", ""),
                body_hint=parsed.get("body_hint", ""),
                tone=parsed.get("tone", "default"),
                sender_name=ast_config.SENDER_CONFIG.SMTP_EMAIL
            )
            
            subject = email_content.get("subject", "No Subject")
            text_body = email_content.get("text_body", "")
            
            # Print draft details
            print(f"\nDraft Subject: {subject}")
            print(f"To:            {', '.join(recipients)}")
            if validated_paths:
                print(f"Attachments:   {', '.join(p.name for p in validated_paths)}")
            print("-" * 50)
            print(text_body)
            print("-" * 50)
            
            confirm = input("Send this email? (yes/no): ").strip().lower()
            if confirm in ("yes", "y"):
                send_email(
                    recipients=recipients,
                    subject=subject,
                    text_body=text_body,
                    html_body=email_content.get("html_body", ""),
                    attachments=validated_paths
                )
                print("Done! Email sent.")
            else:
                print("Sending aborted.")
                
        except EmailAIValidationError as e:
            print(f"[Validation Error] {e}")
        except EmailAISendError as e:
            print(f"[SMTP Transmission Error] {e}")
        except Exception as e:
            logger.exception("Sender error.")
            print(f"[System Error] Send failed: {e}")

    def handle_read_email(self, parameters: Dict[str, Any]) -> None:
        """Fetches and displays matching emails."""
        print("\n--> Fetching emails...")
        try:
            service = self._ensure_gmail_service()
            raw_sender = parameters.get("sender")
            senders = None
            if raw_sender:
                if isinstance(raw_sender, list):
                    senders = [str(s).strip() for s in raw_sender if str(s).strip()]
                else:
                    import re
                    split_senders = re.split(r',|\band\b', str(raw_sender))
                    senders = [s.strip() for s in split_senders if s.strip()]
            q = build_search_query(senders=senders)
            
            # Parse 'n' from message
            max_results = 5
            q_context = parameters.get("query_context", "").lower()
            import re
            n_match = re.search(r'\b(?:last|latest|next)\s+(\d+)\b|\b(\d+)\s+(?:attachments|mails|emails|messages)\b', q_context)
            if n_match:
                matched_num = next(g for g in n_match.groups() if g is not None)
                max_results = int(matched_num)
            elif "latest" in q_context or "last" in q_context:
                max_results = 1
                
            emails = fetch_emails(service, query=q, max_results=max_results)
            if not emails:
                print("No matching emails found.")
                return
                
            print(f"\nFound {len(emails)} emails:")
            for i, email in enumerate(emails):
                print(f"[{i+1}] Date: {email['date']} | From: {email['sender']} | Subject: {email['subject']}")
                snippet = email["body"][:120].replace("\n", " ").strip()
                print(f"    Snippet: {snippet}...")
                
        except GmailAuthError as auth_err:
            print(f"[OAuth Error] {auth_err}")
        except Exception as e:
            logger.exception("Gmail reader error.")
            print(f"[System Error] Could not read email: {e}")

    def handle_summarize_email(self, parameters: Dict[str, Any]) -> None:
        """Fetches, downloads attachments, parses, and summarizes emails."""
        print("\n--> Summarizing email inbox...")
        try:
            service = self._ensure_gmail_service()
            raw_sender = parameters.get("sender")
            senders = None
            if raw_sender:
                if isinstance(raw_sender, list):
                    senders = [str(s).strip() for s in raw_sender if str(s).strip()]
                else:
                    import re
                    split_senders = re.split(r',|\band\b', str(raw_sender))
                    senders = [s.strip() for s in split_senders if s.strip()]
            # Query each sender independently to ensure we retrieve emails from all target accounts
            targets = senders if senders else [None]
            emails = []
            for target in targets:
                q = build_search_query(senders=[target] if target else None)
                # Parse 'n' from message
                max_results = 1
                q_context = parameters.get("query_context", "").lower()
                import re
                n_match = re.search(r'\b(?:last|latest|next)\s+(\d+)\b|\b(\d+)\s+(?:attachments|mails|emails|messages)\b', q_context)
                if n_match:
                    matched_num = next(g for g in n_match.groups() if g is not None)
                    max_results = int(matched_num)
                target_emails = fetch_emails(service, query=q, max_results=max_results)
                emails.extend(target_emails)
                
            if not emails:
                print("No recent email found to summarize.")
                return
                
            for email in emails:
                print(f"\nSummarizing: '{email['subject']}' from {email['sender']}")
                
                # Download attachments
                paths = download_all_attachments(service, email)
                
                # Extract content from attachments
                attachment_contents = {}
                aggregated_warnings = []
                import re
                for p in paths:
                    content = extract_attachment_content(p)
                    meta_match = re.search(r'__PDF_META__\|pages_detected:(\d+)\|pages_processed:(\d+)\|ocr_pages:(True|False)', content)
                    if meta_match:
                        detected = int(meta_match.group(1))
                        processed = int(meta_match.group(2))
                        if detected > processed:
                            aggregated_warnings.append(f"⚠️ WARNING: PDF Page Count Discrepancy in {p.name}! ({processed} of {detected} pages processed). Some scanned pages may have been skipped. Consider running OCR preprocessing.")
                        content = content[:meta_match.start()].strip()
                    attachment_contents[p.name] = content
                metadata = {
                    "subject": email.get("subject", ""),
                    "sender": email.get("sender", ""),
                    "date": email.get("date", ""),
                    "internal_date_ms": email.get("internalDate", "")
                }
                body = email.get("body", "") + "\n" + email.get("html_body", "")

                # Run Intelligent Extraction Pipeline
                orchestrator = PipelineOrchestrator()
                structured_extractions = orchestrator.run(metadata, body, paths)

                resources = extract_resources(body)
                summary = summarize_email(email, resources, attachment_contents)
                
                # Prepend warnings to the summary text so it's included in outputs
                if aggregated_warnings:
                    warnings_text = "\n".join(aggregated_warnings) + "\n\n"
                    summary["summary"] = warnings_text + summary.get("summary", "")
                    
                save_extraction_outputs(email, summary, attachment_contents, structured_extractions=structured_extractions)
                
                # Display report
                print("\n" + "=" * 30 + " AI EMAIL REPORT " + "=" * 30)
                print(f"Subject:    {summary.get('subject')}")
                print(f"From:       {summary.get('sender')}")
                print(f"Priority:   {summary.get('priority')}")
                print(f"Summary:    {summary.get('summary')}")
                print("\nAction Items:")
                for item in summary.get("action_items", []):
                    print(f"  - {item}")
                print("=" * 77 + "\n")
            
        except GmailAuthError as auth_err:
            print(f"[OAuth Error] {auth_err}")
        except Exception as e:
            logger.exception("Summarization error.")
            print(f"[System Error] Summarization failed: {e}")

    def handle_download_attachments(self, parameters: Dict[str, Any]) -> None:
        """Downloads files/attachments from matching emails."""
        print("\n--> Fetching email attachments...")
        try:
            service = self._ensure_gmail_service()
            raw_sender = parameters.get("sender")
            senders = None
            if raw_sender:
                if isinstance(raw_sender, list):
                    senders = [str(s).strip() for s in raw_sender if str(s).strip()]
                else:
                    import re
                    split_senders = re.split(r',|\band\b', str(raw_sender))
                    senders = [s.strip() for s in split_senders if s.strip()]
            # Parse 'n' from message
            max_results = 3
            q_context = parameters.get("query_context", "").lower()
            import re
            n_match = re.search(r'\b(?:last|latest|next)\s+(\d+)\b|\b(\d+)\s+(?:attachments|mails|emails|messages)\b', q_context)
            if n_match:
                matched_num = next(g for g in n_match.groups() if g is not None)
                max_results = int(matched_num)
            elif "latest" in q_context or "last" in q_context:
                max_results = 1
            
            # Query each sender independently to ensure we retrieve emails from all target accounts
            targets = senders if senders else [None]
            emails = []
            for target in targets:
                q = build_search_query(senders=[target] if target else None, has_attachments=True)
                target_emails = fetch_emails(service, query=q, max_results=max_results)
                emails.extend(target_emails)
                
            if not emails:
                print("No emails with attachments found.")
                return
                
            for email in emails:
                print(f"\nProcessing attachments for email: '{email['subject']}'")
                paths = download_all_attachments(service, email)
                if paths:
                    print(f"Downloaded files: {', '.join(p.name for p in paths)}")
                else:
                    print("No attachments downloaded.")
                    
        except GmailAuthError as auth_err:
            print(f"[OAuth Error] {auth_err}")
        except Exception as e:
            logger.exception("Attachment fetch error.")
            print(f"[System Error] Attachment fetch failed: {e}")

    def handle_extract_file(self, parameters: Dict[str, Any]) -> None:
        """Locates a file on disk (sender or reader folder) and extracts contents."""
        filename = parameters.get("filename")
        if not filename:
            print("Error: No file name provided.")
            return

        print(f"\n--> Locating and extracting text from '{filename}'...")
        
        # Search recursively inside reader/files/ and sender/files/
        reader_matches = list(ast_config.READER_DIR.glob(f"files/**/{filename}"))
        sender_matches = list(ast_config.SENDER_DIR.glob(f"files/**/{filename}"))
        
        file_path = None
        if reader_matches:
            file_path = reader_matches[0]
        elif sender_matches:
            file_path = sender_matches[0]
            
        if not file_path or not file_path.exists():
            print(f"Error: File '{filename}' not found on disk.")
            print(f"Troubleshooting: Please place the file in 'reader/files/' or 'sender/files/'.")
            return
            
        try:
            content = extract_attachment_content(file_path)
            print("\n" + "-" * 30 + " FILE CONTENT " + "-" * 30)
            if len(content) > 1000:
                print(content[:1000] + "\n... [TRUNCATED FOR DISPLAY] ...")
            else:
                print(content)
            print("-" * 74)
        except Exception as e:
            print(f"Extraction failed: {e}")

    def handle_summarize_file(self, parameters: Dict[str, Any]) -> None:
        """Extracts contents from a file and runs AI summarization."""
        filename = parameters.get("filename")
        if not filename:
            print("Error: No file name provided.")
            return

        print(f"\n--> Summarizing file: '{filename}'...")
        
        # Search recursively inside reader/files/ and sender/files/
        reader_matches = list(ast_config.READER_DIR.glob(f"files/**/{filename}"))
        sender_matches = list(ast_config.SENDER_DIR.glob(f"files/**/{filename}"))
        
        file_path = None
        if reader_matches:
            file_path = reader_matches[0]
        elif sender_matches:
            file_path = sender_matches[0]
            
        if not file_path or not file_path.exists():
            print(f"Error: File '{filename}' not found.")
            return
            
        try:
            content = extract_attachment_content(file_path)
            
            # FILE TRACEABILITY LOG
            file_stat = file_path.stat()
            import datetime
            mod_time = datetime.datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"FILE TRACEABILITY: Read {file_path.resolve()} (Modified: {mod_time}, Size: {file_stat.st_size} bytes)")
            print(f"\n[Traceability] Reading exact file: {file_path.resolve()}\n[Traceability] Last Modified: {mod_time}, Size: {file_stat.st_size} bytes\n")
            
            # Parse and strip __PDF_META__ block
            warning_prefix = ""
            import re
            meta_match = re.search(r'__PDF_META__\|pages_detected:(\d+)\|pages_processed:(\d+)\|ocr_pages:(True|False)', content)
            if meta_match:
                detected = int(meta_match.group(1))
                processed = int(meta_match.group(2))
                if detected > processed:
                    warning_prefix = f"⚠️ WARNING: PDF Page Count Discrepancy detected! ({processed} of {detected} pages processed). Some scanned pages may have been skipped. Consider running OCR preprocessing.\n\n"
                # Strip the meta block from the content sent to LLM
                content = content[:meta_match.start()].strip()
            
            # Use Groq client for document summary
            groq = GroqClient()
            if groq.is_available():
                system_prompt = (
                    "You are a document analyzer. Summarize the following document content in a structured "
                    "bullet-point report. Highlight key takeaways, dates, and amounts if applicable."
                )
                summary_report = groq.get_completion(system_prompt, content)
                print("\n" + "=" * 30 + f" SUMMARY OF {filename.upper()} " + "=" * 30)
                if warning_prefix:
                    print(warning_prefix)
                print(summary_report)
                print("=" * 70 + "\n")
            else:
                print(f"AI summary is offline. Fallback: document has {len(content)} characters.")
                print(content[:300] + "...")
                
        except Exception as e:
            print(f"Summarizing file failed: {e}")

    def handle_search_documents(self, user_query: str) -> None:
        """Runs natural language search over the indexed documents."""
        print(f"\n--> Running AI Semantic Search for: '{user_query}'...")
        try:
            search_engine = SearchEngine()
            results = search_engine.search(user_query)
            
            if not results:
                print("\nNo matching files found.")
                return
                
            print(f"\nFound {len(results)} matching files\n")
            for i, res in enumerate(results):
                print(f"{i + 1}.")
                print(f"📄 File Name:     {res['filename']}")
                print(f"👤 Sender:        {res['sender']}")
                print(f"🕒 Download Time: {res['downloaded_time']}")
                print(f"📂 Folder:        {res['timestamp_folder']}")
                print(f"📁 Full Path:     {res['relative_path']}")
                print(f"📑 File Type:     {res['doc_type'].upper()}")
                print(f"⭐ Match Score:    {res['score']}%")
                print(f"Explanation:     {res['snippet']}")
                print()
                
        except Exception as e:
            logger.exception("Search execution failed.")
            print(f"[System Error] Search failed: {e}")

    def handle_intelligent_extract(self, parameters: Dict[str, Any]) -> None:
        """Runs the Version 2 Intelligent Extraction Pipeline."""
        print("\n--> Running Intelligent Extraction Pipeline...")
        try:
            service = self._ensure_gmail_service()
            raw_sender = parameters.get("sender")
            senders = None
            if raw_sender:
                if isinstance(raw_sender, list):
                    senders = [str(s).strip() for s in raw_sender if str(s).strip()]
                else:
                    import re
                    split_senders = re.split(r',|\band\b', str(raw_sender))
                    senders = [s.strip() for s in split_senders if s.strip()]
                    
            # Query each sender independently to ensure we retrieve emails from all target accounts
            targets = senders if senders else [None]
            emails = []
            for target in targets:
                q = build_search_query(senders=[target] if target else None)
                # Fetch 1 latest email per sender for extraction
                target_emails = fetch_emails(service, query=q, max_results=1)
                emails.extend(target_emails)
                
            if not emails:
                print("No matching emails found for extraction.")
                return
                
            for email in emails:
                print(f"\nExtracting from: '{email['subject']}' sent by {email['sender']}")
                
                # Download attachments
                paths = download_all_attachments(service, email)
                
                # Setup metadata
                metadata = {
                    "subject": email.get("subject", ""),
                    "sender": email.get("sender", ""),
                    "date": email.get("date", ""),
                    "internal_date_ms": email.get("internalDate", "")
                }
                body = email.get("body", "") + "\n" + email.get("html_body", "")
                
                # Run pipeline
                orchestrator = PipelineOrchestrator()
                result = orchestrator.run(metadata, body, paths)
                
                # Extract procurement status details
                proc_status = result.get("procurement_status", {})
                proc_val = result.get("validation", {})
                proc_missing = result.get("missing_procurement_information", [])
                proc_rec = result.get("recommendation", "")
                conflicts_count = len(result.get("conflicts", []))
                
                if result.get("extraction_status") == "failed":
                    fail_reason = result.get("failure_reason", "LLM extraction failed across all models")
                    print("\n" + "=" * 25 + " EXTRACTION FAILED " + "=" * 25 + "\n")
                    print(f"Status        : FAILED")
                    print(f"Failure Reason: {fail_reason}")
                    print("Buyer         : null")
                    print("Supplier      : null")
                    print("Confidence    : null")
                    print("\nRecommendation:")
                    print("The extraction pipeline failed due to LLM API errors (e.g. rate limits).")
                    print("No procurement information was populated. Please retry later.\n")
                    print("Output Files\n")
                    print("[+] extracted_data.json\n")
                    print("[+] summary.txt")
                    print("\n" + "=" * 69 + "\n")
                    continue

                intent_raw = result.get("intent")
                if intent_raw and str(intent_raw).strip():
                    if isinstance(intent_raw, list) and len(intent_raw) > 0:
                        raw_type = str(intent_raw[0]).strip()
                    else:
                        raw_type = str(intent_raw).strip()
                else:
                    doc_type_val = result.get("document_type")
                    if doc_type_val:
                        if isinstance(doc_type_val, list) and len(doc_type_val) > 0:
                            raw_type = str(doc_type_val[0]).strip()
                        elif isinstance(doc_type_val, str) and doc_type_val.strip():
                            raw_type = doc_type_val.strip()
                        else:
                            raw_type = "other"
                    else:
                        raw_type = "other"
                doc_type_display = raw_type



                buyer_name = result.get("buyer", {}).get("company_name") or result.get("buyer", {}).get("contact_name") or "Not Specified"
                supplier_name = result.get("supplier", {}).get("company_name") or result.get("supplier", {}).get("contact_name") or "Not Specified"
                status_str = proc_status.get("status", "INCOMPLETE")
                score_val = proc_status.get("completeness_score", 0)
                val_status = proc_val.get("status", "FAILED")
                val_display = "[+] PASSED" if val_status == "PASSED" else "[X] FAILED"
                
                print("\n" + "=" * 17 + " PROCUREMENT INFO " + "=" * 17 + "\n")
                print(f"Document Type (LLM Intent): {doc_type_display}\n")
                print(f"Buyer : {buyer_name}\n")
                print(f"Supplier : {supplier_name}\n")
                print(f"Conflicts : {conflicts_count}\n")
                print(f"Confidence : {result.get('confidence_score', 1.0)}\n")
                print(f"Validation : {val_display} (Score: {score_val}) - {status_str}\n")
                
                # Expose the comparative audit table for all 6 types
                try:
                    reader_validate_proc = import_reader_module("tools.intelligent_extractor.validate_procurement")
                    evaluate_doc_for_type = reader_validate_proc.evaluate_doc_for_type
                    
                    doc_types_list = [
                        "request_for_quotation",
                        "purchase_order",
                        "invoice",
                        "delivery_note",
                        "quotation_response",
                        "vendor_price_list"
                    ]
                    
                    print("-" * 100)
                    print(f"{'Audit Type':<25} | {'Score':<5} | {'Status':<15} | {'Fields (Pres/Req)':<18} | {'Missing Fields'}")
                    print("-" * 100)
                    for dt in doc_types_list:
                        res = evaluate_doc_for_type(result, dt)
                        missing_str = ", ".join(res["missing"]) if res["missing"] else "None (100% complete)"
                        print(f"{dt:<25} | {res['score']:<5} | {res['status']:<15} | {res['present']}/{res['total']:<16} | {missing_str}")
                    print("-" * 100 + "\n")
                except Exception as eval_err:
                    print(f"[Error printing comparative audit table: {eval_err}]\n")
                    
                is_valid, errors, warnings, schema_used = validate_extraction(result)
                if warnings:
                    print(f"Warnings : {len(warnings)}")
                    for warn in warnings:
                        words = warn.split()
                        short_warn = " ".join(words[:4]) + "..." if len(words) > 4 else warn
                        print(f"- {short_warn}")
                    print()
                else:
                    print("Warnings : None\n")
                    
                if proc_rec:
                    print(f"Recommendation\n{proc_rec}\n")
                    
                print("Output Files\n")
                print("[+] extracted_data.json\n")
                print("[+] summary.txt")
                print("\n" + "=" * 52 + "\n")
            
        except GmailAuthError as auth_err:
            print(f"[OAuth Error] {auth_err}")
        except Exception as e:
            logger.exception("Intelligent extraction error.")
            print(f"[System Error] Intelligent extraction failed: {e}")

    def handle_test_all_summaries(self, parameters: Dict[str, Any]) -> None:
        """Test feature to summarize all attachments from a sender into a test folder."""
        print("\n--> Running test feature: Summarize all attachments...")
        try:
            service = self._ensure_gmail_service()
            raw_sender = parameters.get("sender")
            if not raw_sender:
                print("Error: No sender email identified.")
                return

            q = build_search_query(senders=[str(raw_sender)])
            emails = fetch_emails(service, query=q, max_results=1)
            
            if not emails:
                print(f"No matching emails found for {raw_sender}.")
                return
                
            email = emails[0]
            print(f"\nExtracting from: '{email['subject']}' sent by {email['sender']}")
            
            paths = download_all_attachments(service, email)
            if not paths:
                print("No attachments found.")
                return

            # Extract username from email
            username = raw_sender.split('@')[0]
            
            # Create test_all/username folder
            test_dir = Path("test_all") / username
            test_dir.mkdir(parents=True, exist_ok=True)
            
            groq = GroqClient()
            system_prompt = """            system_prompt = You are a precision document summarizer for procurement, tender, and purchase-order 
documents (POs, NITs, tender notices, office notes, correspondence, comparative 
statements). Your summaries are used by people who will act on them — approve payments, 
track deadlines, verify compliance — so factual accuracy outranks brevity.

# NON-NEGOTIABLE RULES

1. NEVER invent, guess, round, or "auto-correct" a number, date, or ID.
   - If a value is unclear, illegible, or ambiguous, write [UNCLEAR: best guess] 
     rather than silently picking one.
   - Do NOT change a year, date, or figure to what "looks more plausible." 
     Copy it exactly as written in the source, character for character.

2. ALWAYS double-check every date, amount, percentage, and reference number 
   against the source text before including it. After drafting the summary, 
   re-scan the source and re-scan your draft side-by-side for every digit.

3. NEVER drop a clause just because it's "routine" or "boilerplate" — 
   see the "Not specified" rule below.

# DISTINGUISHING ABSENCE FROM UNCERTAINTY

Before writing "Not specified" for any Required Field, you must have actually 
searched the full source text for that information. Do not write "Not specified" 
from assumption or pattern — only after confirming it is genuinely absent.

Use exactly these three labels, and only these:
- "[value]" — found verbatim in source
- "Not present in this document" — you searched and confirmed it is absent
- "[UNCLEAR — source unreadable/ambiguous at this point]" — visible but 
  illegible/contradictory. NEVER pair this with a fabricated specific value.

NEVER pull a fact from a different document in the batch to fill a gap in 
the current one, even if they relate to the same procurement. Each summary 
must be generated strictly from its own source file.

# CRITICAL CORRECTION — MANDATORY BEFORE OUTPUT

You have a documented history of two specific errors. You MUST actively guard against both.

## ERROR TYPE 1: Detecting a problem and reporting it anyway
Example of what you did wrong: noticing a number looks wrong but printing it unchanged anyway.

RULE: If any date, number, or ID looks internally inconsistent, unusual, 
or contradicts another date/number in the same document, this is a STOP 
condition, not a flag condition. You must:
  1. Stop.
  2. Re-locate that exact field in the source text character by character.
  3. Copy the literal characters from the source — do not reconstruct it from memory.
  4. Only write it in the summary once you have re-read it directly.
It is NEVER acceptable to print a value in the summary body that you know or suspect is an OCR misread. 

## ERROR TYPE 2: Fabricating plausible specificity
Example of what you did wrong: generating a completely wrong year or adding seconds to a time when none exist in the source. Any time the OCR outputs a list of un-labeled dates, do NOT guess which one is the deadline. If you cannot confidently tie a date to a label, output "[UNCLEAR - Multiple unlabeled dates found]" instead of guessing.

## ERROR TYPE 3: Writing "Not specified" for fields that exist in the source
Example of what you did wrong: writing "Delivery period: Not specified" 
in a Purchase Order summary when the source document contains an entire 
numbered clause ("12. DELIVERY PERIOD") elsewhere.

RULE: Before writing "Not specified" or "Not present in this document" 
for ANY field, you must perform an explicit verification step:
  1. Scan the ENTIRE source document top to bottom.
  2. Purchase Orders ALMOST ALWAYS contain numbered clauses for: delivery period, despatch instructions, 
     consignee details, paying officer, liquidated damages, guarantee 
     period, and test certificates. If you are about to mark ANY of these 
     "Not specified", treat that as a red flag and re-read the full document.

## ERROR TYPE 4: Skipping Middle-of-Table Fields
Example of what you did wrong: marking "Tender Type: Not specified" when it was clearly listed in row 7 of a 23-row Summary Sheet table.
RULE: When the source contains ANY numbered or tabular field list (e.g., a Summary Sheet with items 1-23), you MUST process it as a strict checklist. Go row-by-row through every numbered item in any such table and confirm each one is either included in the summary or explicitly confirmed absent. Do not summarize a table by "reading the gist" of it.

## CROSS-FIELD DATE SANITY CHECK (mandatory before finalizing any date):

Tender and procurement documents follow a fixed logical order:
  issue date  ->  submission deadline  ->  bid opening date

The submission deadline can NEVER be later than the bid opening date — opening happens after submission closes, always, with no exceptions in this document type.

Before writing any date into the summary, check it against this rule:
  - If "bid submission deadline" > "bid opening date" as literally read, this is IMPOSSIBLE, not just "inconsistent." One of the two OCR readings is wrong.
  - When this happens, do NOT print either date as fact. Instead, output: "Bid submission deadline: [UNRELIABLE OCR — verify against source; raw text read as <date>, which is chronologically impossible given bid opening date <date>]"
  - This applies to any date pair in the document, not just this one field — apply the same logical check to issue date vs. deadline, deadline vs. validity period, etc.

This check must happen BEFORE the value is written into the summary body, not after (do not print a wrong value in the body and only mention the problem in a separate Flags section — the two must never disagree).

## REQUIRED FIELDS CHECKLIST
If the document is a Tender Notice, NIT, or RFQ, you MUST explicitly check for the following fields and report if they are present or absent:
- Tender Type
- Tender Category
- Bid Validity (e.g., "120 Days")
(For all other document types like Purchase Orders, Comparative Statements, or letters, do NOT include these fields in the summary).

## MANDATORY FINAL PASS
After drafting the full summary, do a dedicated second pass:
  - Read your own draft top to bottom.
  - For every "Not specified" / "Not present" line, re-search once more.
  - For every date/time/number, re-compare digit-by-digit against source.
  - VALIDATION PASS FOR ADDRESSES/PINS: Check PIN codes for structural formatting. If a 6-digit PIN has a space (e.g. "5163 12"), auto-correct it by removing the space ("516312") since it's a pure formatting fix. NEVER silently auto-correct character-level typos (e.g., "V.W" -> "V.V"). Instead, flag them: "Address reads 'V.W Reddy Nagar' — likely OCR misread of 'V.V Reddy Nagar' based on matching addresses elsewhere in this document set, but not auto-corrected — please verify."
  - For every "Not specified" / "Not present" line, re-search once more.
  - For every date/time/number, re-compare digit-by-digit against source.

Do not proceed to final output until this pass is complete.
"""
            
            import re
            for path in paths:
                print(f"  - Extracting: {path.name}")
                content = extract_attachment_content(path)
                
                # FILE TRACEABILITY LOG
                file_stat = path.stat()
                import datetime
                mod_time = datetime.datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"FILE TRACEABILITY: Read {path.resolve()} (Modified: {mod_time}, Size: {file_stat.st_size} bytes)")
                print(f"    [Traceability] Last Modified: {mod_time}, Size: {file_stat.st_size} bytes")
                
                # Parse and strip __PDF_META__ block
                warning_prefix = ""
                meta_match = re.search(r'__PDF_META__\|pages_detected:(\d+)\|pages_processed:(\d+)\|ocr_pages:(True|False)', content)
                if meta_match:
                    detected = int(meta_match.group(1))
                    processed = int(meta_match.group(2))
                    if detected > processed:
                        warning_prefix = f"⚠️ WARNING: PDF Page Count Discrepancy detected! ({processed} of {detected} pages processed). Some scanned pages may have been skipped. Consider running OCR preprocessing.\n\n"
                    # Strip the meta block from the content sent to LLM
                    content = content[:meta_match.start()].strip()
                
                try:
                    if groq.is_available():
                        summary = groq.get_completion(system_prompt, content)
                    else:
                        summary = "LLM not available."
                except Exception as e:
                    summary = f"Summary failed: {e}"
                    
                final_output = warning_prefix + summary
                    
                test_dir.mkdir(parents=True, exist_ok=True)
                out_file = test_dir / f"{path.name}_summary.txt"
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(final_output)
                    
                print(f"Saved summary to {out_file}")
                
            print(f"\nDone! All summaries saved in {test_dir.resolve()}")
            
        except Exception as e:
            logger.exception("Test summaries error.")
            print(f"[System Error] Test summaries failed: {e}")


def main() -> None:
    """Main CLI run loop for Assistant."""
    assistant = UnifiedAssistant()
    print_banner()
    
    while True:
        try:
            instruction = input("\nASSISTANT > ").strip()
            if not instruction:
                continue
            if instruction.lower() in ("exit", "quit"):
                print("Exiting UNIFIED ASSISTANT. Goodbye!")
                break
                
            # Parse & Route
            routed = route_instruction(instruction)
            action = routed.get("action")
            params = routed.get("parameters", {})
            
            logger.info(f"Routed action: {action} with parameters: {params}")
            
            if action == "SEND_EMAIL":
                assistant.handle_send_email(instruction)
            elif action == "READ_EMAIL":
                assistant.handle_read_email(params)
            elif action == "SUMMARIZE_EMAIL":
                assistant.handle_summarize_email(params)
            elif action == "DOWNLOAD_ATTACHMENTS":
                assistant.handle_download_attachments(params)
            elif action == "EXTRACT_FILE":
                assistant.handle_extract_file(params)
            elif action == "SUMMARIZE_FILE":
                assistant.handle_summarize_file(params)
            elif action == "SEARCH_DOCUMENTS":
                assistant.handle_search_documents(instruction)
            elif action == "INTELLIGENT_EXTRACT":
                assistant.handle_intelligent_extract(params)
            elif action == "TEST_ALL_SUMMARIES":
                assistant.handle_test_all_summaries(params)
            else:
                print(f"Unknown action: '{action}'. I might not be able to handle that command yet.")
                
        except (KeyboardInterrupt, EOFError):
            print("\nExiting UNIFIED ASSISTANT. Goodbye!")
            break
        except Exception as e:
            logger.exception("Assistant failure.")
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
