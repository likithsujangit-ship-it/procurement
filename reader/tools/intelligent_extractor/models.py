from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class Buyer(BaseModel):
    company_name: str = ""
    contact_name: str = ""
    contact_title: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    gstin: str = ""

class Supplier(BaseModel):
    company_name: str = ""
    contact_name: str = ""
    contact_title: str = ""
    email: str = ""
    address: str = ""

class Item(BaseModel):
    part_number: str = ""
    description: str = ""
    quantity: int = 0
    unit: str = ""
    material_spec: str = ""

class CommercialTerms(BaseModel):
    payment_terms: str = ""
    incoterms: str = ""
    currency: str = ""
    warranty: str = ""
    delivery_requirement: str = ""

class Attachment(BaseModel):
    filename: str = ""
    type: str = ""
    contains: List[str] = Field(default_factory=list)

class Conflict(BaseModel):
    field: str = ""
    email_value: Any = ""
    attachment_value: Any = ""

class FinalResponse(BaseModel):
    intent: str = ""
    document_type: List[str] = Field(default_factory=list)
    buyer: Buyer = Field(default_factory=Buyer)
    supplier: Supplier = Field(default_factory=Supplier)
    rfq_number: str = ""
    rfq_date: str = ""
    quotation_due_date: str = ""
    po_number: str = ""
    po_date: str = ""
    reference_rfq_number: str = ""
    approval_status: str = ""
    items: List[Item] = Field(default_factory=list)
    commercial_terms: CommercialTerms = Field(default_factory=CommercialTerms)
    shipping_details: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[Attachment] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    confidence_score: float = 0.0
