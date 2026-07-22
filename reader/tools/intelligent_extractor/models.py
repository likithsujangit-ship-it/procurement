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
    gst_rate: str = ""
    tds_rate: str = ""
    security_deposit: str = ""
    performance_bank_guarantee: str = ""
    liquidated_damages: str = ""
    landed_price_methodology: str = ""

class Attachment(BaseModel):
    filename: str = ""
    type: str = ""
    contains: List[str] = Field(default_factory=list)

class Conflict(BaseModel):
    field: str = ""
    email_value: Any = ""
    attachment_value: Any = ""

