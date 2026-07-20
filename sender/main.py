"""
Main Entry Point for the EMAIL SENDER Application.
Provides an interactive command-line interface for sending emails using natural language instructions.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

from config import Config
from tools.utils import setup_logger
from tools.parser import parse_natural_language_command
from tools.validator import validate_email, validate_attachments, EmailAIValidationError
from tools.email_generator import generate_email_content
from tools.email_sender import send_email, EmailAISendError

logger = setup_logger("main")


def print_banner() -> None:
    """Prints a premium style CLI ASCII banner."""
    print("=" * 80)
    print("                      EMAIL SENDER - AI ASSISTANT (EMAIL_AI)                     ")
    print("=" * 80)
    print("Type a natural language instruction to draft and send an email.")
    print("Examples:")
    print("  - Send mail to hr regarding internship saying I want to apply.")
    print("  - Send resume.pdf and photo.png to contact@domain.com saying hello.")
    print("  - Send email to boss@corp.com and cc secretary@corp.com regarding status.")
    print("Type 'exit' or 'quit' to close the program.")
    print("=" * 80)


def preview_draft(parsed_data: Dict[str, Any], subject: str, text_body: str, attachments: List[Path]) -> None:
    """Displays a neat formatted preview of the drafted email."""
    print("\n" + "-" * 40 + " EMAIL DRAFT PREVIEW " + "-" * 40)
    print(f"To:          {', '.join(parsed_data['recipients'])}")
    if parsed_data.get("cc"):
        print(f"CC:          {', '.join(parsed_data['cc'])}")
    if parsed_data.get("bcc"):
        print(f"BCC:         {', '.join(parsed_data['bcc'])}")
    print(f"Subject:     {subject}")
    print(f"Tone style:  {parsed_data['tone']}")
    
    if attachments:
        print(f"Attachments: {', '.join(p.name for p in attachments)} (verified on disk)")
    else:
        print("Attachments: None")
        
    print("-" * 101)
    print(text_body)
    print("-" * 101)


def process_command(instruction: str) -> None:
    """Processes a single natural language instruction to draft and send an email."""
    try:
        # 1. Parse natural language using LLM or regex fallback
        parsed_data = parse_natural_language_command(instruction)
        
        # 2. Validate recipients & attachments
        recipients = parsed_data.get("recipients", [])
        if not recipients:
            print("\nError: No recipients found in your instruction.")
            print("Troubleshooting: Explicitly mention an email (abc@gmail.com) or contact name (hr, manager).")
            return
            
        # Validate recipient emails syntax
        for recipient in recipients:
            validate_email(recipient, "recipients")
            
        for cc_recip in parsed_data.get("cc", []):
            validate_email(cc_recip, "cc")
            
        for bcc_recip in parsed_data.get("bcc", []):
            validate_email(bcc_recip, "bcc")
            
        # Validate and retrieve file paths for attachments
        attachments = parsed_data.get("attachments", [])
        validated_attachment_paths = validate_attachments(attachments)
        
        # 3. Generate email content (Subject, Plain text, HTML)
        subject_hint = parsed_data.get("subject_hint", "")
        body_hint = parsed_data.get("body_hint", "")
        tone = parsed_data.get("tone", "default")
        
        email_content = generate_email_content(
            subject_hint=subject_hint,
            body_hint=body_hint,
            tone=tone,
            sender_name=Config.SMTP_EMAIL
        )
        
        subject = email_content.get("subject", "No Subject")
        text_body = email_content.get("text_body", "")
        html_body = email_content.get("html_body", "")
        
        # 4. Show Draft Preview to User
        preview_draft(parsed_data, subject, text_body, validated_attachment_paths)
        
        # 5. Confirm before sending
        confirm = input("Confirm sending this email? (yes/no): ").strip().lower()
        if confirm in ("yes", "y"):
            print("Sending email...")
            send_email(
                recipients=recipients,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                cc=parsed_data.get("cc"),
                bcc=parsed_data.get("bcc"),
                attachments=validated_attachment_paths
            )
            print("Done! Email sent successfully.")
        else:
            print("Email sending cancelled. Draft discarded.")
            
    except EmailAIValidationError as val_err:
        print(f"\n[Validation Error] {val_err}")
    except EmailAISendError as send_err:
        print(f"\n[SMTP Transmission Error] {send_err}")
    except Exception as e:
        logger.exception("An unexpected error occurred during command processing.")
        print(f"\n[System Error] An unexpected error occurred: {e}")
        print("Troubleshooting: Please check the application logs for a full stack trace.")


def main() -> None:
    """Main CLI run loop."""
    print("Initializing configuration...")
    try:
        Config.validate()
        logger.info("Configuration validation succeeded.")
    except ValueError as val_err:
        print(f"\n[Configuration Error] {val_err}")
        print("\nStarting in DEMO/DRY-RUN mode. Actual SMTP sending will be bypassed.")
        Config.DRY_RUN = True

    print_banner()
    
    while True:
        try:
            instruction = input("\nEMAIL_SENDER > ").strip()
            if not instruction:
                continue
            if instruction.lower() in ("exit", "quit"):
                print("Exiting EMAIL SENDER. Goodbye!")
                break
            process_command(instruction)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting EMAIL SENDER. Goodbye!")
            break


if __name__ == "__main__":
    main()
