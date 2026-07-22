"""
Main Entry Point for the EMAIL READER Application.
Authorizes with Gmail, fetches emails using user filters, downloads attachments,
extracts document text/data, generates structured summaries, and writes files.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import Config
from tools.utils import setup_logger
from tools.gmail_auth import get_gmail_service, GmailAuthError
from tools.gmail_reader import build_search_query, fetch_emails
from tools.attachment_downloader import download_all_attachments
from tools.link_extractor import extract_resources
from tools.extractor import extract_attachment_content
from tools.summarizer import summarize_email, save_extraction_outputs

logger = setup_logger("main")


def print_banner() -> None:
    """Prints a premium style CLI ASCII banner."""
    print("=" * 80)
    print("                      EMAIL READER - AI ASSISTANT (EMAIL_AI)                     ")
    print("=" * 80)
    print("Allows querying Gmail, downloading attachments, and generating AI summaries.")
    print("Options:")
    print("  1. Read latest N emails (e.g. 5)")
    print("  2. Read unread emails")
    print("  3. Read starred / important emails")
    print("  4. Read emails from specific senders")
    print("  5. Read emails with attachments only")
    print("  6. Exit")
    print("=" * 80)


def display_email_summary(summary_data: Dict[str, Any]) -> None:
    """Prints a beautiful formatted summary to standard output."""
    print("\n" + "#" * 30 + " EMAIL INSIGHT REPORT " + "#" * 30)
    print(f"FROM:       {summary_data.get('sender')}")
    print(f"SUBJECT:    {summary_data.get('subject')}")
    print(f"DATE:       {summary_data.get('date')}")
    print(f"PRIORITY:   {summary_data.get('priority')}")
    print("-" * 82)
    print(f"SUMMARY:\n{summary_data.get('summary')}")
    print("-" * 82)
    
    print("ACTION ITEMS:")
    for item in summary_data.get("action_items", []):
        print(f"  [ ] {item}")
    if not summary_data.get("action_items"):
        print("  None")
        
    print("\nMEETING DATES / TIMES:")
    for m_date in summary_data.get("meeting_dates", []):
        print(f"  - {m_date}")
    if not summary_data.get("meeting_dates"):
        print("  None")

    print("\nRESOURCES FOUND:")
    res = summary_data.get("resources", {})
    found_any = False
    for k, v in res.items():
        if v:
            print(f"  - {k.replace('_', ' ').title()}: {', '.join(v)}")
            found_any = True
    if not found_any:
        print("  None")

    print("\nATTACHMENTS DETECTED:")
    for att in summary_data.get("attachment_summary", []):
        print(f"  - File: {att.get('filename')} | Summary: {att.get('content_summary')}")
    if not summary_data.get("attachment_summary"):
        print("  None")
    print("#" * 82 + "\n")


def process_emails(emails: List[Dict[str, Any]], service: Any) -> None:
    """Downloads attachments, extracts info, summarizes, and saves files for a list of emails."""
    if not emails:
        print("No emails found to process.")
        return

    print(f"Processing {len(emails)} emails...")
    for idx, email in enumerate(emails):
        print(f"\n[{idx + 1}/{len(emails)}] Processing: '{email['subject']}' from {email['sender']}")
        
        # 1. Download any attachments automatically
        attachment_paths = download_all_attachments(service, email)
        
        # 2. Extract content from attachments
        attachment_contents = {}
        for path in attachment_paths:
            content = extract_attachment_content(path)
            attachment_contents[path.name] = content

        # 3. Extract links, OTPs, tracking codes using regex from email body text
        resources = extract_resources(email["body"] + "\n" + email["html_body"])
        
        # 4. Generate structured summary
        summary = summarize_email(email, resources, attachment_contents)
        
        # 5. Save outputs into mail-named timestamp folder
        save_extraction_outputs(email, summary, attachment_contents)
        
        # 6. Display to console
        display_email_summary(summary)


def run_interactive_menu(service: Any) -> None:
    """Runs a loop showing choices to the user."""
    while True:
        print_banner()
        choice = input("Enter choice (1-6): ").strip()
        
        if choice == "6" or choice.lower() in ("exit", "quit"):
            print("Exiting EMAIL READER. Goodbye!")
            break
            
        query = ""
        max_results = Config.DEFAULT_MAX_RESULTS
        
        if choice == "1":
            n_str = input("How many emails to retrieve? (default 5): ").strip()
            max_results = int(n_str) if n_str.isdigit() else Config.DEFAULT_MAX_RESULTS
            query = build_search_query()
            
        elif choice == "2":
            query = build_search_query(is_unread=True)
            
        elif choice == "3":
            sub_choice = input("Filter by (1) Starred or (2) Important? ").strip()
            if sub_choice == "1":
                query = build_search_query(is_starred=True)
            else:
                query = build_search_query(is_important=True)
                
        elif choice == "4":
            sender_str = input("Enter sender emails (comma-separated): ").strip()
            senders = [s.strip() for s in sender_str.split(",") if s.strip()]
            query = build_search_query(senders=senders)
            
        elif choice == "5":
            query = build_search_query(has_attachments=True)
            
        else:
            print("Invalid selection. Please choose between 1 and 6.")
            continue
            
        try:
            emails = fetch_emails(service, query, max_results)
            process_emails(emails, service)
        except Exception as e:
            logger.exception("Failed to process emails.")
            print(f"Error: Failed to process query. Details: {e}")


def main() -> None:
    """Main CLI run loop."""
    print("Initializing Google Gmail API Authentication...")
    try:
        service = get_gmail_service()
    except GmailAuthError as auth_err:
        print(f"\n[Gmail OAuth Authentication Failure] {auth_err}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[System Error] Initialization failed: {e}")
        sys.exit(1)
        
    run_interactive_menu(service)


if __name__ == "__main__":
    main()
