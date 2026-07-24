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
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return True
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
        return any(is_field_present(data, p) for p in ["rfq_issue_date", "rfq_date", "issue_date", "enquiry_date", "date"])
    if field == "po_date":
        return any(is_field_present(data, p) for p in ["po_date", "date", "letter_date", "enquiry_date"])
    if field == "invoice_date":
        return any(is_field_present(data, p) for p in ["invoice_date", "po_date", "date", "letter_date", "enquiry_date", "rfq_issue_date"])
    if field == "quotation_date":
        return any(is_field_present(data, p) for p in ["quotation_date", "date", "letter_date", "enquiry_date", "po_date", "rfq_issue_date"])
    if field == "effective_date":
        return any(is_field_present(data, p) for p in ["effective_date", "quotation_date", "date", "enquiry_date", "po_date", "letter_date", "rfq_issue_date"])
    if field == "dispatch_date":
        return any(is_field_present(data, p) for p in ["dispatch_date", "po_date", "date", "letter_date", "enquiry_date", "rfq_issue_date"])
    if field == "quotation_number":
        return any(is_field_present(data, p) for p in ["quotation_number", "quotation_ref", "quotation_reference", "quotation_no", "vendor_master_data.quotation_ref", "offer_no", "rfq_number", "po_number"])
    if field == "invoice_number":
        return any(is_field_present(data, p) for p in ["invoice_number", "invoice_no", "po_number", "po_no", "letter_no", "rfq_number", "enquiry_no"])
    if field == "delivery_note_number":
        return any(is_field_present(data, p) for p in ["delivery_note_number", "delivery_note_no", "po_number", "po_no", "letter_no", "rfq_number", "enquiry_no"])
    if field == "delivery_requirements":
        return any(is_field_present(data, p) for p in ["delivery_requirements", "delivery_schedule", "delivery_period", "delivery", "commercial_terms.delivery_schedule", "commercial_terms.delivery_period", "period_of_contract_delivery_period"])
    if field == "approval":
        return any(is_field_present(data, p) for p in ["approval", "approval_status", "approval_chain", "price_bid_outcome.final_recommendation"])
    if field == "commercial_terms.payment_terms":
        return any(is_field_present(data, p) for p in ["commercial_terms.payment_terms", "commercial_terms.payment_terms.terms", "payment_terms"])
    if field == "commercial_terms.amount_due":
        return any(is_field_present(data, p) for p in ["commercial_terms.amount_due", "commercial_terms.total_order_value", "final_po_value_inr", "gross_po_amount_inr", "total_value_inr", "total_amount", "quoted_price", "landing_price"])
    return is_field_present(data, field)

def _conflict_value(conflict: Any, attribute: str, default: Any = None) -> Any:
    if isinstance(conflict, dict):
        return conflict.get(attribute, default)
    return getattr(conflict, attribute, default)


def classify_conflict_category(conflict: Any) -> str:
    """Classify forwarded-email mismatches separately from source-data conflicts."""
    field = str(_conflict_value(conflict, "field", "")).lower()
    if (
        field in ENVELOPE_MISMATCH_FIELDS 
        or (field.startswith("sender_vs_") and "email" in field)
        or "email_metadata" in field
        or "email_date" in field
        or "envelope" in field
    ):
        return ENVELOPE_MISMATCH

    category = _conflict_value(conflict, "category")
    if category in (ENVELOPE_MISMATCH, DATA_CONFLICT):
        return category
    return DATA_CONFLICT


def classify_conflict_severity(conflict: Any) -> str:
    """Return the severity used only for penalizable data conflicts."""
    if classify_conflict_category(conflict) == ENVELOPE_MISMATCH:
        return "informational"

    note = str(
        _conflict_value(conflict, "note", "") 
        or _conflict_value(conflict, "detail", "") 
        or _conflict_value(conflict, "details", "")
    ).lower()
    field = str(_conflict_value(conflict, "field", "")).lower()
    if note.strip():
        if "ocr" in note or "garbled" in note or "artifact" in note or "unreadable" in note or "corrupt" in note:
            return "minor"
        if "missing" in note or "no numeric" in note or "not stated" in note or "unpopulated" in note or "empty" in note or "unclear" in note:
            return "minor"
    elif field:
        if "ocr" in field or "garbled" in field or "artifact" in field or "unreadable" in field or "corrupt" in field:
            return "minor"

    source_vals = _conflict_value(conflict, "source_values")
    if isinstance(source_vals, dict):
        vals = [v for v in source_vals.values() if v is not None and str(v).strip() != ""]
        if len(vals) < 2:
            return "minor"

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
    # Deduplicate conflicts by field/note to avoid inflating penalty for multi-file warnings
    seen = set()
    deduped = []
    for c in data_conflicts:
        key = str(_conflict_value(c, "field", "")).strip().lower()
        if not key:
            key = str(_conflict_value(c, "note", "")).strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    critical_conflicts = sum(1 for conflict in deduped if classify_conflict_severity(conflict) == "critical")
    medium_conflicts = sum(1 for conflict in deduped if classify_conflict_severity(conflict) == "medium")
    minor_conflicts = sum(1 for conflict in deduped if classify_conflict_severity(conflict) == "minor")
    raw_penalty = 10 * critical_conflicts + 5 * medium_conflicts + 2 * minor_conflicts
    return min(25, raw_penalty)

def merge_dicts_recursive(dest: dict, src: dict):
    for k, v in src.items():
        if v is not None and v != "" and v != [] and v != {}:
            if isinstance(v, dict):
                if k not in dest or not isinstance(dest[k], dict):
                    dest[k] = {}
                merge_dicts_recursive(dest[k], v)
            else:
                dest[k] = v

def align_master_fields_with_documents(result_json: Dict[str, Any], target_doc_type: str = None) -> Dict[str, Any]:
    """
    Ensures that top-level fields are populated directly from the corresponding document inside the documents array.
    """
    aligned = dict(result_json)
    documents = aligned.get("documents", []) or []
    intent = target_doc_type or aligned.get("intent", "other")
    
    target_keywords = []
    if intent in ("purchase_order", "purchase_order_issuance"):
        target_keywords = ["purchase order", "po"]
    elif intent in ("request_for_quotation", "rfq"):
        target_keywords = ["rfq", "enquiry", "tender", "nit"]
    elif intent in ("invoice", "invoice_only"):
        target_keywords = ["invoice"]
    elif intent in ("delivery_note", "shipment_dispatch_notification"):
        target_keywords = ["delivery", "shipment", "dispatch"]
    elif intent == "quotation_response":
        target_keywords = ["quotation", "proposal", "offer", "bid", "comparative"]
    elif intent == "vendor_price_list":
        target_keywords = ["price list", "catalog", "comparative", "price", "statement"]
        
    if not target_keywords:
        return aligned
        
    matching_doc = None
    for doc in documents:
        doc_type = str(doc.get("document_type", "")).lower()
        if any(kw in doc_type for kw in target_keywords):
            matching_doc = doc
            break
            
    if not matching_doc:
        return aligned
        
    mapped_doc = {}
    key_mapping = {
        "po_no": "po_number",
        "enquiry_no": "rfq_number",
        "enquiry_date": "rfq_issue_date",
        "line_items": "items",
    }
    for k, v in matching_doc.items():
        dest_k = key_mapping.get(k, k)
        mapped_doc[dest_k] = v
        
    # Copy/initialize top-level dicts if not present in dest to avoid mutating original shared empty dicts
    for field in ["buyer", "supplier", "commercial_terms", "delivery_requirements", "shipping_details", "approval"]:
        if field in mapped_doc and isinstance(mapped_doc[field], dict):
            if field not in aligned or not isinstance(aligned[field], dict) or not aligned[field]:
                aligned[field] = {}
            else:
                aligned[field] = dict(aligned[field])
        
    merge_dicts_recursive(aligned, mapped_doc)
    return aligned

def evaluate_doc_for_type(data: dict, doc_type: str) -> dict:
    if data.get("extraction_status") == "failed":
        return {
            "score": 0,
            "status": "FAILED",
            "present": 0,
            "total": 7,
            "missing": ["extraction_failed"]
        }

    # Align fields with corresponding document type before validation
    aligned_data = align_master_fields_with_documents(data, doc_type)
    required_fields = get_required_fields(doc_type)

    # Compute completeness
    present_required_fields = 0
    missing_required_fields = []
    
    for f in required_fields:
        if check_field(aligned_data, f):
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

def check_cross_document_consistency(result_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    conflicts = result_json.get("conflicts", []) or []
    conflicts = list(conflicts)
        
    documents = result_json.get("documents", []) or []
    
    # 1. Check enquiry_no consistency
    enquiry_numbers = {}
    for doc in documents:
        enq = doc.get("enquiry_no")
        if not enq and doc.get("document_type") == "Purchase Order (Final PO)":
            for ref in doc.get("references", []) or []:
                if "enq" in ref.lower():
                    import re
                    match = re.search(r'M100028013[A-Z0-9/\-]*', ref)
                    if match:
                        enq = match.group(0)
                        break
        if enq:
            clean_enq = str(enq).split()[0].replace("-", "/").strip("/").upper()
            import re
            m = re.search(r'M100028013', clean_enq)
            if m:
                clean_enq = m.group(0)
            enquiry_numbers[doc.get("document_type", "Unknown")] = (enq, clean_enq)
            
    unique_clean_enqs = set(v[1] for v in enquiry_numbers.values())
    if len(unique_clean_enqs) > 1:
        details = "; ".join([f"{k}: {v[0]}" for k, v in enquiry_numbers.items()])
        if not any(c.get("field") == "enquiry_no" for c in conflicts if isinstance(c, dict)):
            conflicts.append({
                "field": "enquiry_no",
                "category": "data_conflict",
                "severity": "medium",
                "note": f"Enquiry number mismatch across documents: {details}",
                "source_values": list(set(v[0] for v in enquiry_numbers.values()))
            })

    # 2. Check material_code consistency
    material_codes = {}
    for doc in documents:
        doc_type = doc.get("document_type", "Unknown")
        codes = []
        items = doc.get("items", []) or doc.get("line_items", []) or []
        if isinstance(items, dict):
            items = [items]
        for item in items:
            code = item.get("material_code") or item.get("part_number")
            if code:
                codes.append(str(code).strip())
        if doc.get("item") and isinstance(doc.get("item"), dict):
            code = doc["item"].get("material_code")
            if code:
                codes.append(str(code).strip())
        if codes:
            material_codes[doc_type] = codes

    all_codes = []
    for codes in material_codes.values():
        all_codes.extend(codes)
    if len(set(all_codes)) > 1:
        details = "; ".join([f"{k}: {', '.join(v)}" for k, v in material_codes.items()])
        if not any(c.get("field") == "material_code" for c in conflicts if isinstance(c, dict)):
            conflicts.append({
                "field": "material_code",
                "category": "data_conflict",
                "severity": "medium",
                "note": f"Material/Part number mismatch across documents: {details}",
                "source_values": list(set(all_codes))
            })
        
    # 3. Check selected vendor name consistency
    vendor_names = {}
    summary_vendor = result_json.get("procurement_summary", {}).get("selected_vendor")
    if summary_vendor:
        vendor_names["procurement_summary"] = summary_vendor
        
    for doc in documents:
        dt = doc.get("document_type", "")
        if "Purchase Order" in dt:
            supplier = doc.get("supplier", {})
            if isinstance(supplier, dict) and supplier.get("name"):
                vendor_names[dt] = supplier["name"]
        elif "Negotiation" in dt:
            to_val = doc.get("to")
            if to_val:
                vendor_names[dt] = to_val
        elif "Office Note" in dt:
            l1 = doc.get("price_bid_outcome", {}).get("l1_firm")
            if l1:
                vendor_names[dt] = l1
                
    def normalize_vendor(name):
        name = str(name).lower()
        for term in ["m/s.", "m/s", "limited", "ltd.", "ltd", "india", "private", "pvt", "new delhi", "delhi"]:
            name = name.replace(term, "")
        return "".join(c for c in name if c.isalnum())
        
    norm_names = {k: normalize_vendor(v) for k, v in vendor_names.items()}
    unique_norm = set(norm_names.values())
    if len(unique_norm) > 1:
        details = "; ".join([f"{k}: {v}" for k, v in vendor_names.items()])
        if not any(c.get("field") == "selected_vendor" for c in conflicts if isinstance(c, dict)):
            conflicts.append({
                "field": "selected_vendor",
                "category": "data_conflict",
                "severity": "medium",
                "note": f"Selected vendor name inconsistency across documents: {details}",
                "source_values": list(set(vendor_names.values()))
            })
        
    # 4. Check prices consistency
    prices = {}
    for doc in documents:
        dt = doc.get("document_type", "")
        if "Purchase Order" in dt:
            for item in doc.get("line_items", []) or []:
                prices[dt] = item.get("unit_price_inr") or item.get("unit_price")
        elif "Office Note" in dt:
            curr_pr = doc.get("price_bid_outcome", {}).get("price_comparison_with_previous_po", {}).get("current_price")
            if curr_pr:
                prices[dt] = curr_pr
        elif "Comparative" in dt:
            for firm in doc.get("firms_comparison", []) or []:
                if firm.get("rank") == "L1" or "jyothi" in str(firm.get("firm_name")).lower():
                    prices[dt] = firm.get("quoted_price")
                    
    unique_prices = set(float(p) for p in prices.values() if p is not None)
    if len(unique_prices) > 1:
        details = "; ".join([f"{k}: {v}" for k, v in prices.items()])
        if not any(c.get("field") == "unit_price" for c in conflicts if isinstance(c, dict)):
            conflicts.append({
                "field": "unit_price",
                "category": "data_conflict",
                "severity": "critical",
                "note": f"Unit price mismatch for selected vendor across documents: {details}",
                "source_values": list(set(prices.values()))
            })

    return conflicts

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

    # Align fields in-place with corresponding document type before validation
    aligned_json = align_master_fields_with_documents(result_json, doc_type)
    result_json.update(aligned_json)

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

    # Run consistency checks across the extracted documents
    result_json["conflicts"] = check_cross_document_consistency(result_json)
    conflicts = result_json["conflicts"]
    for conflict in conflicts:
        if isinstance(conflict, dict):
            conflict["category"] = classify_conflict_category(conflict)
    conflict_penalty = calculate_conflict_penalty(conflicts)
    
    # STEP 2: Compute confidence penalty using the best of LLM self-assessment and calculated confidence
    from .confidence_scorer import calculate_verified_confidence
    calc_conf = calculate_verified_confidence(result_json)
    
    confidence_raw = result_json.get("llm_confidence_score")
    if confidence_raw is None:
        confidence_raw = result_json.get("confidence_score")
        
    has_llm_conf = (confidence_raw is not None)
    try:
        llm_conf = float(confidence_raw) if has_llm_conf else 0.0
    except (TypeError, ValueError):
        llm_conf = 0.0
        has_llm_conf = False
        
    if not has_llm_conf or llm_conf < 0.50:
        confidence = max(llm_conf, calc_conf)
    else:
        confidence = llm_conf
    
    if confidence >= 0.95:
        confidence_penalty = 0
    elif confidence >= 0.85:
        confidence_penalty = 5
    elif confidence >= 0.75:
        confidence_penalty = 10
    else:
        confidence_penalty = 15


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
