import json
import jsonschema
from jsonschema.exceptions import ValidationError
from datetime import datetime
import sys
import argparse
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"

PRECEDENCE_ORDER = [
    "invoice",
    "invoice_only",
    "delivery_note",
    "shipment_dispatch_notification",
    "purchase_order",
    "purchase_order_issuance",
    "request_for_quotation",
    "quotation_response",
    "vendor_price_list",
    "other"
]

INTENT_SCHEMA_MAP = {
    "invoice": "invoice",
    "invoice_only": "invoice",
    "delivery_note": "delivery_note",
    "shipment_dispatch_notification": "delivery_note",
    "purchase_order": "purchase_order",
    "purchase_order_issuance": "purchase_order",
    "request_for_quotation": "request_for_quotation",
    "quotation_response": "quotation_response",
    "vendor_price_list": "vendor_price_list"
}

def resolve_best_intent(intent) -> str:
    from typing import Any
    if isinstance(intent, list):
        valid_intents = [i for i in intent if i in PRECEDENCE_ORDER]
        if valid_intents:
            return min(valid_intents, key=lambda x: PRECEDENCE_ORDER.index(x))
        return intent[0] if intent else "other"
    return str(intent) if intent else "other"

def load_schema(intent: str):
    best_intent = resolve_best_intent(intent)
    mapped_name = INTENT_SCHEMA_MAP.get(best_intent, best_intent)
    schema_path = SCHEMA_DIR / f"{mapped_name}_schema.json"
    if not schema_path.exists():
        return None
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)

def is_valid_date(date_str):
    if not isinstance(date_str, str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        pass
    try:
        datetime.fromisoformat(date_str)
        return True
    except ValueError:
        pass
    try:
        datetime.strptime(date_str, "%Y/%m/%d")
        return True
    except ValueError:
        pass
    return False

def validate_extraction(data: dict) -> tuple[bool, list[str], list[str], str]:
    """
    Validates extraction output data against the dynamic JSON Schema and custom rules.
    Returns: (is_valid, errors, warnings, schema_used)
    """
    intent = data.get("intent", "unknown")
    best_intent = resolve_best_intent(intent)
    schema = load_schema(intent)
    errors = []
    warnings = []
    mapped_name = INTENT_SCHEMA_MAP.get(best_intent, best_intent)
    schema_used = f"{mapped_name}_schema.json"

    if not schema:
        warnings.append(f"No schema available for this intent ('{best_intent}') — routed to manual review")
        return True, errors, warnings, "none"
        
    # 1. JSON Schema validation
    try:
        validator = jsonschema.Draft7Validator(schema)
        for e in validator.iter_errors(data):
            path = ".".join([str(p) for p in e.path]) if e.path else "root"
            if "Additional properties" in e.message:
                continue
            elif "is a required property" in e.message:
                warnings.append(f"Missing field: {e.message}")
            elif "is not of type 'string'" in e.message and ("None" in e.message or "null" in e.message):
                warnings.append(f"Missing field: {path} is null")
            else:
                errors.append(f"{path}: {e.message}")
    except Exception as e:
        errors.append(f"Schema validation exception: {str(e)}")
    
    if not isinstance(data, dict):
        return len(errors) == 0, errors, warnings, schema_used

    # 2. Custom Rule: Attachments[].type ⊆ document_type (Allow MIME types and common document formats)
    doc_types = set(data.get("document_type", []))
    for i, attachment in enumerate(data.get("attachments", [])):
        att_type = attachment.get("type")
        if att_type and att_type not in doc_types:
            if "/" in att_type or att_type.lower() in ("pdf", "docx", "doc", "xlsx", "xls", "png", "jpg", "jpeg", "csv", "zip"):
                continue
            errors.append(f"attachments[{i}].type: '{att_type}' not in document_type array {list(doc_types)}")
            
    # 2b. Custom Rule: Filename-based sanity check
    for i, attachment in enumerate(data.get("attachments", [])):
        filename = attachment.get("filename", "").lower()
        att_type = attachment.get("type", "")
        if "purchase_order" in filename and att_type != "Purchase_Order":
            warnings.append(f"attachments[{i}].type is '{att_type}', but filename '{attachment.get('filename')}' strongly implies 'Purchase_Order'")

    # 3. Custom Rule: Valid calendar dates for all fields ending in _date or date
    for key, value in data.items():
        if isinstance(key, str) and (key.endswith("_date") or key == "date") and isinstance(value, str):
            if not is_valid_date(value):
                errors.append(f"{key}: '{value}' is not a valid calendar date in YYYY-MM-DD or ISO format")

    # 4. Custom Rule: Due date >= rfq date (Warning for RFQ only)
    if intent == "request_for_quotation":
        rfq_date_str = data.get("rfq_date")
        due_date_str = data.get("quotation_due_date")
        if rfq_date_str and due_date_str and is_valid_date(rfq_date_str) and is_valid_date(due_date_str):
            if due_date_str < rfq_date_str:
                warnings.append(f"quotation_due_date ({due_date_str}) is before rfq_date ({rfq_date_str})")

    # 5. Custom Rule: missing_fields should be actual keys in the schema (Warning)
    allowed_missing_fields = set(schema.get("properties", {}).keys())
    allowed_missing_fields.update(["freight_cost", "insurance_terms", "specific_bank_account_details"])
    
    for missing_field in data.get("missing_fields", []):
        base_field = missing_field.split(".")[0]
        if base_field not in allowed_missing_fields:
            warnings.append(f"missing_fields contains '{missing_field}' which is not a recognized top-level schema field")

    # 6. JSON serialization check for item quantities (ensure numeric quantity)
    for i, item in enumerate(data.get("items", [])):
        q = item.get("quantity")
        if q is not None and not isinstance(q, (int, float)):
            errors.append(f"items[{i}].quantity: expected integer/number, got {type(q).__name__} ({q})")
            
    is_valid = len(errors) == 0
    return is_valid, errors, warnings, schema_used


def main():
    parser = argparse.ArgumentParser(description="Validate extraction JSON against dynamic schema.")
    parser.add_argument("file", type=str, help="Path to the JSON output file")
    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"Error: File '{filepath}' does not exist.")
        sys.exit(1)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON file - {e}")
        sys.exit(1)

    is_valid, errors, warnings, schema_used = validate_extraction(data)

    if not is_valid:
        print(f"\n❌ VALIDATION FAILED ({len(errors)} errors, {len(warnings)} warnings) against {schema_used}")
        for err in errors:
            print(f"  - {err}")
        for warn in warnings:
            print(f"  ⚠ {warn}")
        sys.exit(1)
    else:
        print(f"\n✅ VALIDATION PASSED — output conforms to {schema_used}")
        if warnings:
            print(f"  ({len(warnings)} warnings)")
            for warn in warnings:
                print(f"  ⚠ {warn}")
        sys.exit(0)

if __name__ == "__main__":
    main()
