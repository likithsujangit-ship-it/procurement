"""
Procurement Completeness Validation Engine for EMAIL_AI.
Calculates completeness score and status strictly based on document-specific schemas.
Respects extraction_status state machine and avoids false confidence defaults.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


REQUIRED_FIELDS_CONFIG_PATH = Path(__file__).with_name("required_fields_config.json")


def load_document_field_config() -> Dict[str, Dict[str, List[str]]]:
    """Load the required/optional field definitions shared by all completeness checks."""
    with REQUIRED_FIELDS_CONFIG_PATH.open(encoding="utf-8") as config_file:
        return json.load(config_file)


DOCUMENT_FIELD_CONFIG = load_document_field_config()
ENVELOPE_MISMATCH = "envelope_mismatch"
DATA_CONFLICT = "data_conflict"
ENVELOPE_MISMATCH_FIELDS = {
    "sender_vs_buyer_email",
    "sender_vs_supplier_email",
    "envelope_sender_vs_buyer_email",
    "envelope_sender_vs_supplier_email",
}


def get_required_fields(doc_type: str) -> List[str]:
    return DOCUMENT_FIELD_CONFIG.get(doc_type, {}).get("required_fields", [])


def get_optional_fields(doc_type: str) -> List[str]:
    return DOCUMENT_FIELD_CONFIG.get(doc_type, {}).get("optional_fields", [])

def get_nested_field(data: dict, path: str) -> Any:
    parts = path.split(".")
    curr = data
    for part in parts:
        if not isinstance(curr, dict):
            return None
        curr = curr.get(part)
        if curr is None:
            return None
    return curr

def is_val_present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return len(v) > 0
    if isinstance(v, dict):
        return len(v) > 0 and any(is_val_present(sub_v) for sub_v in v.values())
    return bool(v)

def is_field_present(data: Dict[str, Any], path: str) -> bool:
    val = get_nested_field(data, path)
    return is_val_present(val)

def check_field(data: Dict[str, Any], field: str) -> bool:
    if field == "rfq_issue_date":
        return is_field_present(data, "rfq_issue_date") or is_field_present(data, "rfq_date") or is_field_present(data, "issue_date") or is_field_present(data, "date")
    if field == "po_date":
        return is_field_present(data, "po_date") or is_field_present(data, "date")
    if field == "invoice_date":
        return is_field_present(data, "invoice_date") or is_field_present(data, "date")
    if field == "quotation_date":
        return is_field_present(data, "quotation_date") or is_field_present(data, "date")
    if field == "approval":
        return is_field_present(data, "approval") or is_field_present(data, "approval_status")
    if field == "commercial_terms.payment_terms":
        return is_field_present(data, "commercial_terms.payment_terms") or is_field_present(data, "payment_terms")
    if field == "commercial_terms.amount_due":
        return is_field_present(data, "commercial_terms.amount_due") or is_field_present(data, "commercial_terms.total_value") or is_field_present(data, "total_amount")
    return is_field_present(data, field)

def _conflict_value(conflict: Any, attribute: str, default: Any = None) -> Any:
    if isinstance(conflict, dict):
        return conflict.get(attribute, default)
    return getattr(conflict, attribute, default)


def classify_conflict_category(conflict: Any) -> str:
    """Classify forwarded-email mismatches separately from source-data conflicts."""
    field = str(_conflict_value(conflict, "field", "")).lower()
    if field in ENVELOPE_MISMATCH_FIELDS or (field.startswith("sender_vs_") and "email" in field):
        return ENVELOPE_MISMATCH

    category = _conflict_value(conflict, "category")
    if category in (ENVELOPE_MISMATCH, DATA_CONFLICT):
        return category
    return DATA_CONFLICT


def classify_conflict_severity(conflict: Any) -> str:
    """Return the severity used only for penalizable data conflicts."""
    if classify_conflict_category(conflict) == ENVELOPE_MISMATCH:
        return "informational"

    if isinstance(conflict, dict):
        severity = conflict.get("severity")
        if severity in ("critical", "medium", "minor"):
            return severity
        field = str(conflict.get("field", "")).lower()
    else:
        severity = getattr(conflict, "severity", None)
        if severity in ("critical", "medium", "minor"):
            return severity
        field = str(getattr(conflict, "field", "")).lower()

    critical_keywords = ["price", "total", "amount", "value", "quantity", "qty", "buyer", "supplier", "part_number", "item", "identity"]
    medium_keywords = ["date", "due_date", "payment_terms", "incoterms", "terms"]
    
    if any(k in field for k in critical_keywords):
        return "critical"
    elif any(k in field for k in medium_keywords):
        return "medium"
    else:
        return "minor"


def calculate_conflict_penalty(conflicts: List[Any]) -> int:
    """Apply existing severity penalties to data conflicts, never envelope metadata."""
    data_conflicts = [
        conflict for conflict in conflicts
        if classify_conflict_category(conflict) == DATA_CONFLICT
    ]
    critical_conflicts = sum(1 for conflict in data_conflicts if classify_conflict_severity(conflict) == "critical")
    medium_conflicts = sum(1 for conflict in data_conflicts if classify_conflict_severity(conflict) == "medium")
    minor_conflicts = sum(1 for conflict in data_conflicts if classify_conflict_severity(conflict) == "minor")
    return 10 * critical_conflicts + 5 * medium_conflicts + 2 * minor_conflicts

def evaluate_doc_for_type(data: dict, doc_type: str) -> dict:
    if data.get("extraction_status") == "failed":
        return {
            "score": 0,
            "status": "FAILED",
            "present": 0,
            "total": 7,
            "missing": ["extraction_failed"]
        }

    required_fields = get_required_fields(doc_type)

    # Compute completeness
    present_required_fields = 0
    missing_required_fields = []
    
    for f in required_fields:
        if check_field(data, f):
            present_required_fields += 1
        else:
            missing_required_fields.append(f)
            
    total_required_fields = len(required_fields)
    raw_score = (present_required_fields / total_required_fields) * 100 if total_required_fields > 0 else 100

    # Apply penalties
    conflicts = data.get("conflicts", []) or []
    conflict_penalty = calculate_conflict_penalty(conflicts)
    
    confidence_raw = data.get("llm_confidence_score") if data.get("llm_confidence_score") is not None else data.get("confidence_score")
    if confidence_raw is None:
        confidence_penalty = 20
    else:
        try:
            confidence = float(confidence_raw)
            if confidence >= 0.95:
                confidence_penalty = 0
            elif confidence >= 0.85:
                confidence_penalty = 5
            elif confidence >= 0.75:
                confidence_penalty = 10
            else:
                confidence_penalty = 15
        except Exception:
            confidence_penalty = 20

    final_score = max(0, min(100, int(round(raw_score - conflict_penalty - confidence_penalty))))

    if final_score >= 95:
        status = "COMPLETE"
    elif final_score >= 80:
        status = "MOSTLY_COMPLETE"
    elif final_score >= 60:
        status = "PARTIAL"
    else:
        status = "INCOMPLETE"

    return {
        "score": final_score,
        "status": status,
        "present": present_required_fields,
        "total": total_required_fields,
        "missing": missing_required_fields
    }

def audit_procurement_completeness(result_json: Dict[str, Any]) -> Dict[str, Any]:
    if result_json.get("extraction_status") == "failed":
        fail_reason = result_json.get("failure_reason") or "Extraction failed across all LLM models"
        result_json["procurement_status"] = {
            "status": "FAILED",
            "completeness_score": 0
        }
        result_json["validation"] = {
            "status": "FAILED",
            "reason": fail_reason
        }
        result_json["missing_procurement_information"] = [
            {"field": "all_fields", "reason": fail_reason}
        ]
        result_json["recommendation"] = f"Extraction failed due to API errors ({fail_reason}). Please retry later."
        result_json["buyer"] = None
        result_json["supplier"] = None
        result_json["items"] = None
        result_json["llm_confidence_score"] = None
        result_json["calculated_confidence_score"] = None
        result_json["confidence_discrepancy_flag"] = False
        result_json["completeness"] = {
            "score": 0,
            "status": "FAILED",
            "required_fields": 7,
            "present_fields": 0,
            "missing_fields": 7,
            "conflicts": 0
        }
        return result_json

    intent = result_json.get("intent", "other")
    doc_types = result_json.get("document_type", [])
    if isinstance(doc_types, str):
        doc_types = [doc_types]

    # STEP 1: Detect document type strictly into one of the 6 possible types
    if intent == "request_for_quotation" or any("rfq" in str(dt).lower() or "quotation" in str(dt).lower() for dt in doc_types):
        doc_type = "request_for_quotation"
    elif intent in ("purchase_order_issuance", "purchase_order") or any("po" in str(dt).lower() or "purchase" in str(dt).lower() for dt in doc_types):
        doc_type = "purchase_order"
    elif intent in ("invoice_only", "invoice") or any("invoice" in str(dt).lower() for dt in doc_types):
        doc_type = "invoice"
    elif intent in ("shipment_dispatch_notification", "delivery_note") or any("delivery" in str(dt).lower() or "shipment" in str(dt).lower() or "dispatch" in str(dt).lower() for dt in doc_types):
        doc_type = "delivery_note"
    elif intent == "quotation_response" or any("proposal" in str(dt).lower() or "offer" in str(dt).lower() for dt in doc_types):
        doc_type = "quotation_response"
    elif intent == "vendor_price_list" or any("catalog" in str(dt).lower() or "price_list" in str(dt).lower() for dt in doc_types):
        doc_type = "vendor_price_list"
    else:
        doc_type = "request_for_quotation"

    required_fields = get_required_fields(doc_type)
    
    present_required_fields = 0
    missing_required_fields = []
    
    for f in required_fields:
        if check_field(result_json, f):
            present_required_fields += 1
        else:
            missing_required_fields.append(f)

    # The model may report helpful-but-optional fields as missing.  The final
    # missing_fields list is reserved exclusively for objectively absent required
    # fields; optional gaps are deliberately separated for reviewer visibility.
    optional_fields_missing = [
        field for field in get_optional_fields(doc_type)
        if not check_field(result_json, field)
    ]
    result_json["missing_fields"] = missing_required_fields
    result_json["optional_fields_missing"] = optional_fields_missing
            
    total_required_fields = len(required_fields)
    raw_score = (present_required_fields / total_required_fields) * 100 if total_required_fields > 0 else 100

    conflicts = result_json.get("conflicts", []) or []
    for conflict in conflicts:
        if isinstance(conflict, dict):
            conflict["category"] = classify_conflict_category(conflict)
    conflict_penalty = calculate_conflict_penalty(conflicts)
    
    # Preserve the existing completeness confidence-penalty formula.  Only the
    # field name changed in the final output; legacy payloads remain supported.
    confidence_raw = result_json.get("llm_confidence_score")
    if confidence_raw is None:
        confidence_raw = result_json.get("confidence_score")
    if confidence_raw is None:
        confidence_penalty = 20
    else:
        try:
            confidence = float(confidence_raw)
            if confidence >= 0.95:
                confidence_penalty = 0
            elif confidence >= 0.85:
                confidence_penalty = 5
            elif confidence >= 0.75:
                confidence_penalty = 10
            else:
                confidence_penalty = 15
        except Exception:
            confidence_penalty = 20

    final_score = max(0, min(100, int(round(raw_score - conflict_penalty - confidence_penalty))))

    if final_score >= 95:
        status = "COMPLETE"
    elif final_score >= 80:
        status = "MOSTLY_COMPLETE"
    elif final_score >= 60:
        status = "PARTIAL"
    else:
        status = "INCOMPLETE"

    result_json["document_type"] = doc_type
    result_json["completeness"] = {
        "score": final_score,
        "status": status,
        "required_fields": total_required_fields,
        "present_fields": present_required_fields,
        "missing_fields": len(missing_required_fields),
        "conflicts": len(conflicts)
    }

    result_json["procurement_status"] = {
        "status": status,
        "completeness_score": final_score
    }
    result_json["validation"] = {
        "status": "PASSED" if status in ("COMPLETE", "MOSTLY_COMPLETE") else "FAILED",
        "reason": f"Missing required fields: {', '.join(missing_required_fields)}" if missing_required_fields else ""
    }
    result_json["missing_procurement_information"] = [
        {"field": f, "reason": f"Missing mandatory field {f}"} for f in missing_required_fields
    ]
    result_json["recommendation"] = (
        "The procurement document is complete and ready for further processing."
        if status in ("COMPLETE", "MOSTLY_COMPLETE") else
        "The procurement process is incomplete. Review the missing procurement information before approving the document."
    )

    # Compute calculated_confidence_score and discrepancy flag
    from .confidence_scorer import calculate_verified_confidence
    llm_conf = result_json.get("llm_confidence_score")
    if llm_conf is None:
        llm_conf = result_json.get("confidence_score")
    if llm_conf is not None:
        try:
            llm_conf = float(llm_conf)
        except (TypeError, ValueError):
            llm_conf = None

    calc_conf = calculate_verified_confidence(result_json)
    discrepancy = llm_conf is not None and abs(llm_conf - calc_conf) > 0.30

    result_json["llm_confidence_score"] = llm_conf
    result_json["calculated_confidence_score"] = calc_conf
    result_json["confidence_discrepancy_flag"] = discrepancy
    if "confidence_score" in result_json:
        result_json.pop("confidence_score", None)

    return result_json
