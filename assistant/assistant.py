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
                for p in paths:
                    attachment_contents[p.name] = extract_attachment_content(p)
                    
                resources = extract_resources(email["body"] + "\n" + email["html_body"])
                summary = summarize_email(email, resources, attachment_contents)
                save_extraction_outputs(email, summary, attachment_contents)
                
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
            
            # Use Groq client for document summary
            groq = GroqClient()
            if groq.is_available():
                system_prompt = (
                    "You are a document analyzer. Summarize the following document content in a structured "
                    "bullet-point report. Highlight key takeaways, dates, and amounts if applicable."
                )
                summary_report = groq.get_completion(system_prompt, content[:5000])
                print("\n" + "=" * 30 + f" SUMMARY OF {filename.upper()} " + "=" * 30)
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
                
                print("\n" + "=" * 30 + " EXTRACTION COMPLETE " + "=" * 30)
                print(f"Document Type: {result.get('intent', 'Unknown')}")
                print(f"Buyer:       {result.get('buyer', {}).get('company_name', '')}")
                print(f"Supplier:    {result.get('supplier', {}).get('company_name', '')}")
                if result.get("missing_fields"):
                    print(f"Missing:     {', '.join(result['missing_fields'])}")
                if result.get("conflicts"):
                    print(f"Conflicts:   {len(result['conflicts'])}")
                
                # Run Schema Validation
                is_valid, errors, warnings, schema_used = validate_extraction(result)
                if is_valid:
                    print(f"Validation:  ✅ PASSED ({schema_used})")
                else:
                    print(f"Validation:  ❌ FAILED ({len(errors)} errors) against {schema_used}")
                    for err in errors[:3]:
                        print(f"             - {err}")
                    if len(errors) > 3:
                        print(f"             ... and {len(errors)-3} more")
                if warnings:
                    print(f"Warnings:    {len(warnings)} warnings")
                    for warn in warnings:
                        # Provide a short 2 to 3 word explanation of the warning
                        words = warn.split()
                        short_warn = " ".join(words[:4]) + "..." if len(words) > 4 else warn
                        print(f"             ⚠ {short_warn}")
                    
                print(f"Extraction JSON (extracted_data.json) and summary.txt saved under reader/outputs/<sender_prefix>/<timestamp>/")
                print("=" * 81 + "\n")
            
        except GmailAuthError as auth_err:
            print(f"[OAuth Error] {auth_err}")
        except Exception as e:
            logger.exception("Intelligent extraction error.")
            print(f"[System Error] Intelligent extraction failed: {e}")


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
