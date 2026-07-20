"""
Multi-Stage Procurement Process Validator for EMAIL_AI.
Detects individual procurement stages (RFQ, Quotation, Purchase Order, Delivery Challan, GRN, Invoice, etc.),
audits each stage independently against its mandatory/optional schema rules, and computes overall process validation.
"""

from typing import Dict, Any, List, Tuple


ALL_LIFECYCLE_STAGES = [
    "RFQ",
    "Quotation",
    "Purchase Order",
    "Delivery Challan",
    "GRN",
    "Invoice"
]


def detect_stages(result_json: Dict[str, Any], email_body: str, attachments: List[Dict[str, str]]) -> List[str]:
    """
    Detects all procurement stages present in the email thread and attachments.
    """
    detected = set()
    intent = result_json.get("intent", "").lower()
    doc_types = [dt.lower() for dt in result_json.get("document_type", [])]
    
    # Check intent & document_type
    if "rfq" in intent or "request_for_quotation" in intent or any("rfq" in dt for dt in doc_types):
        detected.add("RFQ")
    if "quotation" in intent or "quote" in intent or any("quotation" in dt or "quote" in dt for dt in doc_types):
        detected.add("Quotation")
    if "purchase_order" in intent or "po" in intent or any("purchase" in dt or "po" in dt for dt in doc_types):
        detected.add("Purchase Order")
    if "invoice" in intent or any("invoice" in dt for dt in doc_types):
        detected.add("Invoice")
    if "delivery" in intent or "shipment" in intent or any("delivery" in dt or "challan" in dt for dt in doc_types):
        detected.add("Delivery Challan")
    if "grn" in intent or "receipt" in intent or any("grn" in dt for dt in doc_types):
        detected.add("GRN")

    # Inspect attachment filenames and raw text
    full_text = email_body.lower() + " " + " ".join(att.get("filename", "").lower() + " " + att.get("raw_text", "").lower() for att in attachments)

    if any(k in full_text for k in ["rfq", "request for quotation", "enquiry", "enq no"]):
        detected.add("RFQ")
    if any(k in full_text for k in ["quotation", "quote", "price list", "proposal", "offer"]):
        detected.add("Quotation")
    if any(k in full_text for k in ["purchase order", "po-", "po_number", "p.o.", "order confirmation"]):
        detected.add("Purchase Order")
    if any(k in full_text for k in ["delivery challan", "dispatch note", "packing list", "consignment"]):
        detected.add("Delivery Challan")
    if any(k in full_text for k in ["goods receipt", "grn", "material receipt", "inspection note"]):
        detected.add("GRN")
    if any(k in full_text for k in ["tax invoice", "invoice no", "bill no", "bill of supply"]):
        detected.add("Invoice")

    # Default fallback: if nothing detected, treat intent as primary stage
    if not detected:
        if "purchase" in intent:
            detected.add("Purchase Order")
        elif "invoice" in intent:
            detected.add("Invoice")
        else:
            detected.add("RFQ")

    # Order stages logically
    ordered_stages = [stage for stage in ALL_LIFECYCLE_STAGES if stage in detected]
    for s in detected:
        if s not in ordered_stages:
            ordered_stages.append(s)
            
    return ordered_stages


def audit_rfq_stage(result_json: Dict[str, Any]) -> Dict[str, Any]:
    buyer = result_json.get("buyer") or {}
    supplier = result_json.get("supplier") or {}
    items = result_json.get("items") or []
    comm = result_json.get("commercial_terms") or {}
    deliv = result_json.get("delivery_requirements") or {}

    mandatory = [
        ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Buyer details missing"),
        ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier details missing"),
        ("RFQ Number", bool(result_json.get("rfq_number")), "RFQ reference number missing"),
        ("RFQ Issue Date", bool(result_json.get("rfq_issue_date")), "RFQ issue date missing"),
        ("Quotation Due Date", bool(result_json.get("quotation_due_date")), "Quotation due date missing"),
        ("Item List", len(items) > 0, "No line items listed in RFQ"),
        ("Part Number", any(i.get("part_number") for i in items) if items else False, "Part numbers missing"),
        ("Description", any(i.get("description") for i in items) if items else False, "Item descriptions missing"),
        ("Quantity", any(i.get("quantity") is not None for i in items) if items else False, "Item quantities missing"),
        ("Unit", any(i.get("unit") for i in items) if items else False, "Unit of measurement missing"),
        ("Material Grade", any(i.get("material_grade") for i in items) if items else False, "Material grade missing"),
        ("Payment Terms", bool(comm.get("payment_terms")), "Payment terms missing"),
        ("Incoterms", bool(comm.get("incoterms")), "Incoterms missing"),
        ("Currency", bool(comm.get("currency")), "Currency missing"),
        ("Delivery Location", bool(deliv.get("delivery_location")), "Delivery location missing"),
        ("Required Delivery Date", bool(deliv.get("required_delivery_date")), "Required delivery date missing"),
    ]

    optional = [
        ("Warranty", bool(comm.get("warranty"))),
        ("Delivery Split", bool(deliv.get("delivery_split"))),
        ("Partial Shipments Allowed", deliv.get("partial_shipments_allowed") is not None)
    ]

    return _evaluate_stage_checks("RFQ", buyer, supplier, mandatory, optional, result_json)


def audit_quotation_stage(result_json: Dict[str, Any]) -> Dict[str, Any]:
    buyer = result_json.get("buyer") or {}
    supplier = result_json.get("supplier") or {}
    items = result_json.get("items") or []
    comm = result_json.get("commercial_terms") or {}
    deliv = result_json.get("delivery_requirements") or {}

    mandatory = [
        ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Buyer details missing"),
        ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier details missing"),
        ("Quotation Number", bool(result_json.get("rfq_number") or comm.get("quotation_number")), "Quotation reference number missing"),
        ("Quotation Date", bool(result_json.get("rfq_issue_date")), "Quotation date missing"),
        ("Quotation Validity", bool(comm.get("quotation_validity")), "Quotation validity period missing"),
        ("Item List", len(items) > 0, "No quoted items listed"),
        ("Unit Price", any(i.get("unit_price") or i.get("price") for i in items) if items else False, "Quoted unit prices missing"),
        ("Total Price", any(i.get("total_price") or i.get("line_total") for i in items) or bool(comm.get("total_value")), "Total quoted price missing"),
        ("Currency", bool(comm.get("currency")), "Quotation currency missing"),
        ("Payment Terms", bool(comm.get("payment_terms")), "Quoted payment terms missing"),
        ("Incoterms", bool(comm.get("incoterms")), "Quoted delivery Incoterms missing"),
    ]

    optional = [
        ("Warranty", bool(comm.get("warranty"))),
        ("Taxes / GST", bool(supplier.get("gstin") or comm.get("taxes_gst"))),
        ("Delivery Schedule", bool(deliv.get("required_delivery_date")))
    ]

    return _evaluate_stage_checks("Quotation", buyer, supplier, mandatory, optional, result_json)


def audit_po_stage(result_json: Dict[str, Any]) -> Dict[str, Any]:
    buyer = result_json.get("buyer") or {}
    supplier = result_json.get("supplier") or {}
    items = result_json.get("items") or []
    comm = result_json.get("commercial_terms") or {}
    deliv = result_json.get("delivery_requirements") or {}
    appr = result_json.get("approval") or {}

    mandatory = [
        ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Buyer company details missing"),
        ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier company details missing"),
        ("PO Number", bool(result_json.get("po_number")), "PO reference number missing"),
        ("PO Date", bool(result_json.get("rfq_issue_date")), "PO date missing"),
        ("Currency", bool(comm.get("currency")), "PO currency missing"),
        ("Item List", len(items) > 0, "PO line items missing"),
        ("Quantity", any(i.get("quantity") is not None for i in items) if items else False, "Item quantities missing"),
        ("Unit", any(i.get("unit") for i in items) if items else False, "Unit of measurement missing"),
        ("Unit Price", any(i.get("unit_price") or i.get("price") for i in items) if items else False, "Unit prices missing"),
        ("Total Value", any(i.get("total_price") or i.get("line_total") for i in items) or bool(comm.get("total_value")), "Total PO value missing"),
        ("Delivery Address", bool(deliv.get("delivery_location") or buyer.get("address")), "Delivery address missing"),
        ("Delivery Schedule", bool(deliv.get("required_delivery_date") or deliv.get("delivery_split")), "Delivery schedule missing"),
        ("Payment Terms", bool(comm.get("payment_terms")), "Payment terms missing"),
        ("Taxes / GST", bool(buyer.get("gstin") or supplier.get("gstin") or comm.get("taxes_gst")), "Taxes or GSTIN missing"),
        ("Technical Specifications", any(i.get("material_grade") or i.get("description") for i in items) if items else False, "Technical specifications missing"),
        ("Warranty", bool(comm.get("warranty")), "Warranty terms missing"),
        ("Inspection Requirements", bool(comm.get("inspection_requirements") or appr.get("inspection")), "Inspection requirements missing"),
        ("Commercial Terms", bool(comm.get("incoterms") or comm.get("payment_terms")), "Commercial terms missing"),
        ("Authorized Signatory", bool(appr.get("approved_by") or buyer.get("contact_name")), "Authorized signatory missing"),
        ("Terms & Conditions", bool(comm.get("terms_and_conditions") or comm.get("payment_terms")), "Terms & conditions missing"),
    ]

    optional = [
        ("Insurance Terms", bool(comm.get("insurance_terms"))),
        ("Freight Cost", bool(comm.get("freight_cost"))),
        ("Bank Account Details", bool(supplier.get("bank_account")))
    ]

    return _evaluate_stage_checks("Purchase Order", buyer, supplier, mandatory, optional, result_json)


def audit_invoice_stage(result_json: Dict[str, Any]) -> Dict[str, Any]:
    buyer = result_json.get("buyer") or {}
    supplier = result_json.get("supplier") or {}
    items = result_json.get("items") or []
    comm = result_json.get("commercial_terms") or {}

    mandatory = [
        ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Buyer details missing"),
        ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier details missing"),
        ("Invoice Number", bool(result_json.get("invoice_number")), "Invoice number missing"),
        ("Invoice Date", bool(result_json.get("rfq_issue_date")), "Invoice date missing"),
        ("Item List", len(items) > 0, "Invoiced line items missing"),
        ("Quantity", any(i.get("quantity") is not None for i in items) if items else False, "Invoiced quantities missing"),
        ("Unit Price", any(i.get("unit_price") or i.get("price") for i in items) if items else False, "Unit prices missing"),
        ("Total Value", any(i.get("total_price") or i.get("line_total") for i in items) or bool(comm.get("total_value")), "Total invoice amount missing"),
        ("Payment Terms", bool(comm.get("payment_terms")), "Payment terms missing"),
        ("Taxes / GST", bool(buyer.get("gstin") or supplier.get("gstin") or comm.get("taxes_gst")), "Taxes or GSTIN missing"),
    ]

    optional = [
        ("PO Reference", bool(result_json.get("po_number"))),
        ("Bank Account Details", bool(supplier.get("bank_account")))
    ]

    return _evaluate_stage_checks("Invoice", buyer, supplier, mandatory, optional, result_json)


def audit_delivery_stage(result_json: Dict[str, Any]) -> Dict[str, Any]:
    buyer = result_json.get("buyer") or {}
    supplier = result_json.get("supplier") or {}
    items = result_json.get("items") or []
    deliv = result_json.get("delivery_requirements") or {}

    mandatory = [
        ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Buyer details missing"),
        ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier details missing"),
        ("Challan / Shipment ID", bool(result_json.get("shipment_id")), "Delivery challan number missing"),
        ("Dispatch Date", bool(deliv.get("required_delivery_date") or result_json.get("rfq_issue_date")), "Dispatch date missing"),
        ("Item List", len(items) > 0, "Delivered line items missing"),
        ("Quantity", any(i.get("quantity") is not None for i in items) if items else False, "Delivered quantities missing"),
        ("Delivery Location", bool(deliv.get("delivery_location") or buyer.get("address")), "Delivery destination address missing"),
    ]

    optional = [
        ("Transporter Name", bool(result_json.get("shipping_details", {}).get("carrier"))),
        ("Vehicle Number", bool(result_json.get("shipping_details", {}).get("vehicle_no")))
    ]

    return _evaluate_stage_checks("Delivery Challan", buyer, supplier, mandatory, optional, result_json)


def audit_grn_stage(result_json: Dict[str, Any]) -> Dict[str, Any]:
    buyer = result_json.get("buyer") or {}
    supplier = result_json.get("supplier") or {}
    items = result_json.get("items") or []

    mandatory = [
        ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Receiving buyer details missing"),
        ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier details missing"),
        ("GRN Number", bool(result_json.get("shipment_id")), "GRN reference number missing"),
        ("Receipt Date", bool(result_json.get("rfq_issue_date")), "Goods receipt date missing"),
        ("PO Reference", bool(result_json.get("po_number")), "PO reference number missing"),
        ("Item List", len(items) > 0, "Received line items missing"),
        ("Received Quantity", any(i.get("quantity") is not None for i in items) if items else False, "Received quantity missing"),
    ]

    optional = [
        ("Accepted Quantity", any(i.get("quantity") is not None for i in items) if items else False),
        ("Inspector Remarks", bool(result_json.get("approval", {}).get("inspection")))
    ]

    return _evaluate_stage_checks("GRN", buyer, supplier, mandatory, optional, result_json)


def _evaluate_stage_checks(
    stage_name: str,
    buyer: Dict[str, Any],
    supplier: Dict[str, Any],
    mandatory_checks: List[Tuple[str, bool, str]],
    optional_checks: List[Tuple[str, bool]],
    result_json: Dict[str, Any]
) -> Dict[str, Any]:
    
    mandatory_found = []
    missing_mandatory = []
    missing_optional = []
    
    passed_count = 0
    for field_name, is_present, reason in mandatory_checks:
        if is_present:
            passed_count += 1
            mandatory_found.append(field_name)
        else:
            missing_mandatory.append(field_name)

    optional_passed = 0
    for field_name, is_present in optional_checks:
        if is_present:
            optional_passed += 1
        else:
            missing_optional.append(field_name)

    total_mandatory = len(mandatory_checks)
    raw_score = (passed_count / total_mandatory) * 100 if total_mandatory > 0 else 100
    
    # Slight bonus for optional fields (up to +5%)
    opt_bonus = (optional_passed / len(optional_checks)) * 5 if optional_checks else 0
    
    conflicts = result_json.get("conflicts", [])
    conflict_penalty = len(conflicts) * 5
    
    score = max(0, min(100, int(round(raw_score + opt_bonus - conflict_penalty))))

    is_passed = (len(missing_mandatory) == 0) and (len(conflicts) == 0)
    validation_status = "PASSED" if is_passed else "FAILED"

    if is_passed:
        recommendation = f"The {stage_name} document is complete and ready for processing."
    else:
        missing_str = ", ".join(missing_mandatory[:3])
        recommendation = f"Complete the missing {stage_name} details ({missing_str}) before proceeding."

    buyer_display = buyer.get("company_name") or buyer.get("contact_name") or "Not Specified"
    supplier_display = supplier.get("company_name") or supplier.get("contact_name") or "Not Specified"

    return {
        "stage": stage_name,
        "document_detected": True,
        "buyer": buyer_display,
        "supplier": supplier_display,
        "completeness_score": score,
        "validation": validation_status,
        "mandatory_fields_found": mandatory_found,
        "missing_mandatory_fields": missing_mandatory,
        "missing_optional_fields": missing_optional,
        "conflicts": [c.get("note", str(c)) if isinstance(c, dict) else str(c) for c in conflicts],
        "warnings": [],
        "recommendation": recommendation
    }


def validate_multi_stage_procurement(
    result_json: Dict[str, Any],
    email_body: str = "",
    attachments: List[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Main entrypoint for multi-stage procurement process validation.
    Performs stage-wise auditing and generates overall procurement process summary.
    """
    if attachments is None:
        attachments = []

    detected_stage_names = detect_stages(result_json, email_body, attachments)
    
    stage_results: List[Dict[str, Any]] = []

    for name in detected_stage_names:
        if name == "RFQ":
            stage_results.append(audit_rfq_stage(result_json))
        elif name == "Quotation":
            stage_results.append(audit_quotation_stage(result_json))
        elif name == "Purchase Order":
            stage_results.append(audit_po_stage(result_json))
        elif name == "Invoice":
            stage_results.append(audit_invoice_stage(result_json))
        elif name == "Delivery Challan":
            stage_results.append(audit_delivery_stage(result_json))
        elif name == "GRN":
            stage_results.append(audit_grn_stage(result_json))

    # Determine missing lifecycle stages
    detected_set = set(detected_stage_names)
    missing_stages = [s for s in ALL_LIFECYCLE_STAGES if s not in detected_set]

    # Calculate overall completeness & validation
    if stage_results:
        avg_score = sum(s["completeness_score"] for s in stage_results) / len(stage_results)
    else:
        avg_score = 0.0

    missing_penalty = len(missing_stages) * 8
    overall_completeness = max(0, min(100, int(round(avg_score - missing_penalty))))

    all_stages_passed = all(s["validation"] == "PASSED" for s in stage_results) and len(missing_stages) == 0
    overall_validation = "PASSED" if all_stages_passed else "FAILED"

    reason_lines = []
    if missing_stages:
        for ms in missing_stages:
            reason_lines.append(f"{ms} stage missing.")
    if not all(s["validation"] == "PASSED" for s in stage_results):
        failed_names = [s["stage"] for s in stage_results if s["validation"] == "FAILED"]
        reason_lines.append(f"Validation failed for stage(s): {', '.join(failed_names)}.")

    procurement_process = {
        "overall_completeness": overall_completeness,
        "overall_validation": overall_validation,
        "missing_stages": missing_stages,
        "reason": " ".join(reason_lines) if reason_lines else "All procurement lifecycle stages completed successfully."
    }

    # Extend result_json with multi-stage audit structure
    result_json["procurement_process"] = procurement_process
    result_json["stages"] = stage_results
    
    # Also maintain top-level backwards compatibility
    result_json["procurement_status"] = {
        "status": "COMPLETE" if overall_validation == "PASSED" else "INCOMPLETE",
        "completeness_score": overall_completeness
    }
    result_json["validation"] = {
        "status": overall_validation,
        "reason": procurement_process["reason"]
    }
    
    all_missing_info = []
    for s in stage_results:
        for mmf in s.get("missing_mandatory_fields", []):
            all_missing_info.append({"field": f"[{s['stage']}] {mmf}", "reason": f"Missing in {s['stage']} stage"})
            
    result_json["missing_procurement_information"] = all_missing_info
    result_json["recommendation"] = f"Overall Procurement Completeness is {overall_completeness}%. {procurement_process['reason']}"

    return result_json
