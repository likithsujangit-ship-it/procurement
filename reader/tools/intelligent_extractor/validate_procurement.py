"""
Procurement Completeness Validation Engine for EMAIL_AI.
Audits extracted document JSON against mandatory procurement process requirements,
calculates completeness score, detects missing procurement fields, and sets validation status.
"""

from typing import Dict, Any, List, Tuple

def audit_procurement_completeness(result_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs a thorough procurement completeness audit on the extracted result_json.
    Updates result_json in-place with:
      - 'procurement_status'
      - 'validation'
      - 'missing_procurement_information'
      - 'recommendation'
    Returns the updated result_json.
    """
    intent = result_json.get("intent", "other")
    doc_types = result_json.get("document_type", [])
    primary_doc_type = doc_types[0] if doc_types else "Procurement Document"
    
    buyer = result_json.get("buyer") or {}
    supplier = result_json.get("supplier") or {}
    items = result_json.get("items") or []
    comm_terms = result_json.get("commercial_terms") or {}
    deliv_req = result_json.get("delivery_requirements") or {}
    approval = result_json.get("approval") or {}
    conflicts = result_json.get("conflicts") or []

    missing_procurement_info: List[Dict[str, str]] = []
    
    # 1. Define mandatory fields based on intent / document_type
    is_po = intent == "purchase_order_issuance" or any("po" in dt.lower() or "purchase" in dt.lower() for dt in doc_types)
    is_rfq = intent == "request_for_quotation" or any("rfq" in dt.lower() or "quotation" in dt.lower() for dt in doc_types)
    is_invoice = intent == "invoice_only" or any("invoice" in dt.lower() for dt in doc_types)
    is_shipment = intent == "shipment_dispatch_notification" or any("delivery" in dt.lower() or "shipment" in dt.lower() for dt in doc_types)

    mandatory_checks: List[Tuple[str, bool, str]] = []

    if is_po:
        # Mandatory fields for Purchase Order
        mandatory_checks = [
            ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name") or buyer.get("email")), "Buyer company or contact details are missing"),
            ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name") or supplier.get("email")), "Supplier company or contact details are missing"),
            ("PO Number", bool(result_json.get("po_number")), "PO reference number is absent"),
            ("PO Date", bool(result_json.get("rfq_issue_date") or result_json.get("date")), "PO issuance date is missing"),
            ("Currency", bool(comm_terms.get("currency")), "Currency (e.g. INR, USD) is not specified"),
            ("Item List", len(items) > 0, "No line items are listed in the order"),
            ("Quantity", any(item.get("quantity") is not None for item in items) if items else False, "Item quantities are missing"),
            ("Unit", any(item.get("unit") for item in items) if items else False, "Unit of measurement (UOM) is missing"),
            ("Unit Price", any(item.get("unit_price") or item.get("price") for item in items) if items else False, "Item unit prices are missing"),
            ("Total Value", any(item.get("total_price") or item.get("line_total") for item in items) or bool(comm_terms.get("total_value")), "Total order value or line item totals are missing"),
            ("Delivery Address", bool(deliv_req.get("delivery_location") or buyer.get("address")), "Delivery shipping address is missing"),
            ("Delivery Schedule", bool(deliv_req.get("required_delivery_date") or deliv_req.get("delivery_split")), "Delivery schedule or required delivery date is missing"),
            ("Payment Terms", bool(comm_terms.get("payment_terms")), "Payment terms (e.g., Net 30, 100% advance) are missing"),
            ("Taxes / GST", bool(buyer.get("gstin") or supplier.get("gstin") or comm_terms.get("taxes_gst") or comm_terms.get("tax")), "Taxes or GSTIN details are missing"),
            ("Technical Specifications", any(item.get("material_grade") or item.get("description") for item in items) if items else False, "Technical specifications or material grades are missing"),
            ("Warranty", bool(comm_terms.get("warranty")), "Warranty terms are missing"),
            ("Inspection Requirements", bool(comm_terms.get("inspection_requirements") or approval.get("inspection")), "Inspection requirements are missing"),
            ("Commercial Terms", bool(comm_terms.get("incoterms") or comm_terms.get("payment_terms")), "Commercial terms (Incoterms or payment conditions) are missing"),
            ("Authorized Signatory", bool(approval.get("approved_by") or buyer.get("contact_name")), "Authorized signatory details are missing"),
            ("Terms & Conditions", bool(comm_terms.get("terms_and_conditions") or comm_terms.get("payment_terms")), "Standard procurement terms and conditions are missing"),
        ]

    elif is_rfq:
        # Mandatory fields for RFQ
        mandatory_checks = [
            ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name") or buyer.get("email")), "Buyer company or procurement manager details missing"),
            ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name") or supplier.get("email")), "Supplier company or contact details missing"),
            ("RFQ Number", bool(result_json.get("rfq_number")), "RFQ reference number missing"),
            ("RFQ Issue Date", bool(result_json.get("rfq_issue_date")), "RFQ issue date missing"),
            ("Quotation Due Date", bool(result_json.get("quotation_due_date")), "Quotation submission deadline date missing"),
            ("Item List", len(items) > 0, "No line items found in RFQ"),
            ("Part Number", any(item.get("part_number") for item in items) if items else False, "Part numbers missing for requested items"),
            ("Description", any(item.get("description") for item in items) if items else False, "Item descriptions missing"),
            ("Quantity", any(item.get("quantity") is not None for item in items) if items else False, "Requested quantities missing"),
            ("Unit", any(item.get("unit") for item in items) if items else False, "Unit of measure missing"),
            ("Material Grade", any(item.get("material_grade") for item in items) if items else False, "Material grade or technical specification missing"),
            ("Payment Terms", bool(comm_terms.get("payment_terms")), "Payment terms missing"),
            ("Incoterms", bool(comm_terms.get("incoterms")), "Incoterms delivery condition missing"),
            ("Currency", bool(comm_terms.get("currency")), "Currency missing"),
            ("Delivery Location", bool(deliv_req.get("delivery_location")), "Destination delivery location missing"),
            ("Required Delivery Date", bool(deliv_req.get("required_delivery_date")), "Required delivery date missing"),
            ("Warranty", bool(comm_terms.get("warranty")), "Warranty requirements missing"),
        ]

    elif is_invoice:
        # Mandatory fields for Invoice
        mandatory_checks = [
            ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Buyer billing details missing"),
            ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier billing details missing"),
            ("Invoice Number", bool(result_json.get("invoice_number")), "Invoice number missing"),
            ("Invoice Date", bool(result_json.get("rfq_issue_date")), "Invoice date missing"),
            ("Item List", len(items) > 0, "No invoiced line items listed"),
            ("Quantity", any(item.get("quantity") is not None for item in items) if items else False, "Invoiced quantities missing"),
            ("Unit Price", any(item.get("unit_price") or item.get("price") for item in items) if items else False, "Unit prices missing"),
            ("Total Value", any(item.get("total_price") or item.get("line_total") for item in items) or bool(comm_terms.get("total_value")), "Total invoice amount missing"),
            ("Payment Terms", bool(comm_terms.get("payment_terms")), "Invoice payment terms missing"),
            ("Taxes / GST", bool(buyer.get("gstin") or supplier.get("gstin") or comm_terms.get("taxes_gst")), "Taxes or GSTIN missing"),
        ]

    else:
        # Default mandatory checks for general procurement documents
        mandatory_checks = [
            ("Buyer", bool(buyer.get("company_name") or buyer.get("contact_name")), "Buyer contact details missing"),
            ("Supplier", bool(supplier.get("company_name") or supplier.get("contact_name")), "Supplier contact details missing"),
            ("Item List", len(items) > 0, "Line items missing"),
            ("Quantity", any(item.get("quantity") is not None for item in items) if items else False, "Item quantities missing"),
            ("Commercial Terms", bool(comm_terms.get("payment_terms") or comm_terms.get("incoterms")), "Commercial terms missing"),
        ]

    # Evaluate checks
    total_checks = len(mandatory_checks)
    passed_checks = 0

    for field_name, is_present, reason in mandatory_checks:
        if is_present:
            passed_checks += 1
        else:
            missing_procurement_info.append({
                "field": field_name,
                "reason": reason
            })

    # Calculate Completeness Score (0 - 100)
    raw_score = (passed_checks / total_checks) * 100 if total_checks > 0 else 100
    conflict_penalty = len(conflicts) * 5
    completeness_score = max(0, min(100, int(round(raw_score - conflict_penalty))))

    # Determine status & validation
    is_complete = (len(missing_procurement_info) == 0) and (len(conflicts) == 0) and (completeness_score == 100)
    
    procurement_status = {
        "status": "COMPLETE" if is_complete else "INCOMPLETE",
        "completeness_score": completeness_score
    }

    if is_complete:
        validation = {
            "status": "PASSED",
            "reason": ""
        }
        recommendation = "The procurement document is complete and ready for further processing."
    else:
        missing_names = [item["field"] for item in missing_procurement_info[:3]]
        reason_msg = f"Missing {', '.join(missing_names)}" if missing_names else "Document contains critical procurement conflicts or incomplete data"
        validation = {
            "status": "FAILED",
            "reason": reason_msg
        }
        recommendation = "The procurement process is incomplete. Review the missing procurement information before approving the document."

    # Update result_json
    result_json["procurement_status"] = procurement_status
    result_json["validation"] = validation
    result_json["missing_procurement_information"] = missing_procurement_info
    result_json["recommendation"] = recommendation

    return result_json
