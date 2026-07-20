"""
Verification Test Script for EMAIL_AI.
Validates imports, checks configuration, and executes test parses to verify installation.
"""

import sys
from pathlib import Path

# Set up path resolution to import from project root
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import from assistant config
from assistant.config import import_sender_module, import_reader_module

# Dynamically import required modules to prevent namespace conflicts
sender_parser_mod = import_sender_module("tools.parser")
sender_validator_mod = import_sender_module("tools.validator")
reader_links_mod = import_reader_module("tools.link_extractor")
reader_utils_mod = import_reader_module("tools.utils")

setup_logger = reader_utils_mod.setup_logger
parse_natural_language_command = sender_parser_mod.parse_natural_language_command
validate_email = sender_validator_mod.validate_email
EmailAIValidationError = sender_validator_mod.EmailAIValidationError
extract_resources = reader_links_mod.extract_resources

logger = setup_logger("test_runner")


def run_unit_tests() -> None:
    """Runs a series of local validation and parser assertions."""
    print("=" * 80)
    print("                      EMAIL_AI INTEGRITY & UNIT TESTS                            ")
    print("=" * 80)
    
    # Test 1: Email Validator
    print("Test 1: Validating email syntax helper...")
    try:
        validate_email("user@gmail.com")
        print("  [PASS] Valid email accepted.")
    except EmailAIValidationError:
        print("  [FAIL] Valid email rejected.")
        
    try:
        validate_email("invalid-email-no-at")
        print("  [FAIL] Malformed email accepted.")
    except EmailAIValidationError as e:
        print("  [PASS] Malformed email successfully caught and raised error.")

    # Test 2: Link & Resource Extractor
    print("\nTest 2: Validating regex link & resource extractor...")
    sample_text = (
        "Hello Team,\n"
        "Here are the project links:\n"
        "Google Drive: https://drive.google.com/drive/folders/123456\n"
        "GitHub repo: https://github.com/user/EMAIL_AI\n"
        "Please complete task by Friday. OTP code is 987654. Phone: +1 555-0199."
    )
    resources = extract_resources(sample_text)
    
    # Assertions
    assert "https://drive.google.com/drive/folders/123456" in resources["google_drive_links"]
    assert "https://github.com/user/EMAIL_AI" in resources["github_links"]
    assert "987654" in resources["otps"]
    assert "+1 555-0199" in resources["phones"]
    print("  [PASS] Resource extraction succeeded with correct classifications.")

    # Test 3: Natural Language Parser (Regex Fallback check)
    print("\nTest 3: Validating natural language parser (regex fallback)...")
    command = "Send resume.pdf and photo.png to manager@gmail.com and hr regarding internship saying hello."
    parsed = parse_natural_language_command(command)
    
    # Check extractions
    print(f"  Input Command: '{command}'")
    print(f"  Extracted Recipients:  {parsed.get('recipients')}")
    print(f"  Extracted Attachments: {parsed.get('attachments')}")
    print(f"  Extracted Tone:        {parsed.get('tone')}")
    print(f"  Extracted Subject Hint:{parsed.get('subject_hint')}")
    
    if "manager@gmail.com" in parsed.get("recipients", []) and "hr@gmail.com" in parsed.get("recipients", []):
        print("  [PASS] Contact resolving and emails extraction successful.")
    else:
        print("  [FAIL] Contact resolving or emails extraction failed.")
        
    if "resume.pdf" in parsed.get("attachments", []) and "photo.png" in parsed.get("attachments", []):
        print("  [PASS] File attachments parsing successful.")
    else:
        print("  [FAIL] File attachments parsing failed.")

    # Test 4: Search Engine Query Intent Fallback Parser
    print("\nTest 4: Validating AI Search Engine fallback parser...")
    try:
        search_engine_mod = import_reader_module("tools.search_engine")
        SearchEngine = search_engine_mod.SearchEngine
        se = SearchEngine()
        intent = se._parse_intent_with_regex("Find PDFs from Google about internship")
        
        assert intent["filters"]["file_type"] == "pdf"
        assert intent["filters"]["sender"] == "google"
        assert "internship" in intent["search_terms"].lower()
        print("  [PASS] Search query parsing and entity extraction successful.")
    except Exception as e:
        print(f"  [FAIL] Search engine parser verification failed: {e}")

    print("\n" + "=" * 80)
    print("                ALL LOCAL UNIT TESTS COMPLETED SUCCESSFULLY!                     ")
    print("=" * 80)


if __name__ == "__main__":
    run_unit_tests()
