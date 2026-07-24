"""Objective confidence signals for extracted procurement documents.

This module deliberately does not use the model's self-assessment.  Each signal
is worth 20% and is either verified (1.0) or not (0.0); absent evidence is not
credited as a pass.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional


GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
SIGNAL_WEIGHT = 0.20


def check_gstin_validity(data: Dict[str, Any]) -> float:
    """Return 1.0 only when every supplied buyer/supplier GSTIN is valid."""
    gstins = []
    for party_name in ("buyer", "supplier"):
        party = data.get(party_name)
        if isinstance(party, dict) and party.get("gstin") is not None:
            value = str(party["gstin"]).strip()
            if value:
                gstins.append(value)

    if not gstins:
        return 0.0
    return 1.0 if all(GSTIN_REGEX.fullmatch(gstin) for gstin in gstins) else 0.0


def check_email_validity(data: Dict[str, Any]) -> float:
    """Return 1.0 only when both buyer and supplier have valid email addresses."""
    emails = []
    for party_name in ("buyer", "supplier"):
        party = data.get(party_name)
        if not isinstance(party, dict) or not party.get("email"):
            return 0.0
        emails.append(str(party["email"]).strip())

    return 1.0 if all(EMAIL_REGEX.fullmatch(email) for email in emails) else 0.0


def _line_total(item: Dict[str, Any]) -> Any:
    """Use document-specific total names while preferring the canonical line_total."""
    for key in ("line_total", "total_price", "total"):
        if item.get(key) is not None:
            return item[key]
    return None


def check_arithmetic_reconciliation(data: Dict[str, Any], tolerance: float = 0.01) -> float:
    """Return 1.0 only when every item with numerical data has reconcilable quantity, price, and total."""
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return 0.0

    checked_any = False
    for item in items:
        if not isinstance(item, dict):
            return 0.0
        quantity = item.get("quantity")
        unit_price = item.get("unit_price")
        line_total = _line_total(item)
        
        # Skip completely empty/unpopulated item rows
        if quantity is None and unit_price is None and line_total is None:
            continue
            
        # If any of the parts are missing, it's not reconciled
        if quantity is None or unit_price is None or line_total is None:
            return 0.0
            
        try:
            if abs(float(quantity) * float(unit_price) - float(line_total)) > tolerance:
                return 0.0
            checked_any = True
        except (TypeError, ValueError):
            return 0.0
            
    return 1.0 if checked_any else 0.0



def parse_iso8601_date(value: Any) -> Optional[date]:
    """Parse an ISO-8601 date or datetime; return None for all other formats."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        # Compare calendar dates, avoiding a naive/aware datetime comparison when
        # one extracted value includes a timezone and the other does not.
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def _first_populated(data: Dict[str, Any], fields: Iterable[str]) -> tuple[Optional[str], Any]:
    for field in fields:
        value = data.get(field)
        if value is not None and str(value).strip():
            return field, value
    return None, None


def check_date_validity(data: Dict[str, Any]) -> float:
    """Verify ISO-8601 dates and any applicable issue/due date ordering."""
    date_fields = (
        "rfq_issue_date", "rfq_date", "issue_date", "quotation_due_date",
        "po_date", "invoice_date", "due_date", "dispatch_date", "delivery_date",
        "quotation_date", "valid_until", "effective_date", "date_extended_from",
    )
    populated_dates = {
        field: data[field]
        for field in date_fields
        if data.get(field) is not None and str(data[field]).strip()
    }
    if not populated_dates:
        return 0.0

    parsed_dates = {field: parse_iso8601_date(value) for field, value in populated_dates.items()}
    if any(value is None for value in parsed_dates.values()):
        return 0.0

    date_pairs = (
        (("rfq_issue_date", "rfq_date", "issue_date"), ("quotation_due_date",)),
        (("quotation_date",), ("valid_until",)),
        (("invoice_date",), ("due_date",)),
        (("po_date",), ("delivery_date",)),
        (("effective_date",), ("valid_until",)),
    )
    for start_fields, end_fields in date_pairs:
        start_field, _ = _first_populated(data, start_fields)
        end_field, _ = _first_populated(data, end_fields)
        if start_field and end_field and parsed_dates[start_field] > parsed_dates[end_field]:
            return 0.0
    return 1.0


def check_required_field_presence(data: Dict[str, Any]) -> float:
    """Reuse the completeness audit's required-field counts when available."""
    completeness = data.get("completeness")
    if isinstance(completeness, dict):
        required = completeness.get("required_fields")
        present = completeness.get("present_fields")
        try:
            required_number = int(required)
            present_number = int(present)
            if required_number > 0:
                return max(0.0, min(1.0, present_number / required_number))
        except (TypeError, ValueError):
            pass

    # The standalone scorer is also useful in tests and callers before audit.
    from .validate_procurement import evaluate_doc_for_type

    evaluation = evaluate_doc_for_type(data, data.get("intent", "request_for_quotation"))
    required = evaluation.get("total", 0)
    present = evaluation.get("present", 0)
    return present / required if required else 0.0


def calculate_verified_confidence(data: Dict[str, Any]) -> float:
    """Calculate the 0.0-1.0 confidence score from five verified signals."""
    if data.get("extraction_status") == "failed" or data.get("extraction_failed"):
        return 0.0

    signals = (
        check_gstin_validity(data),
        check_email_validity(data),
        check_arithmetic_reconciliation(data),
        check_date_validity(data),
        check_required_field_presence(data),
    )
    return round(sum(SIGNAL_WEIGHT * signal for signal in signals), 2)
