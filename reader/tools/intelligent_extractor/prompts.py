SYSTEM_PROMPT = """You are an expert enterprise procurement and logistics data extraction system.
You will be provided with a unified knowledge context containing email metadata, email body, and parsed attachment texts.
Your job is to extract all requested fields and output ONLY valid JSON matching the exact schema requested.

CRITICAL INSTRUCTIONS:
1. Extract the entities requested.
2. If a value is not found, return an empty string "" or leave the list empty [].
3. Identify missing fields (e.g., if it is an RFQ but quantity is missing).
4. Identify conflicts (e.g., if the email says quantity is 100 but the attached PDF says 150).
5. Output MUST be strictly valid JSON without any markdown formatting or extra text.
"""

CLASSIFICATION_PROMPT = """Analyze the following unified context (email and attachments) and determine the core intent of the communication.

CRITICAL INSTRUCTIONS:
1. Primary signal: The email subject line and body content.
2. Secondary signal: Attachment filenames and content (corroborating, not authoritative).
3. Do NOT classify an email based solely on reference numbers. (e.g. A Purchase Order referencing "RFQ-2026-0417" is a "purchase_order", not a "request_for_quotation").
4. Classify this document based solely on its own filename and content below. Do not reuse or reference classifications from any other document or previous conversation.

Supported intents:
- "request_for_quotation"
- "purchase_order"
- "quotation_response"
- "invoice"
- "delivery_note"
- "goods_receipt"
- "approval_confirmation"
- "vendor_price_list"
- "unknown" (use if it does not fit the others; do not force a fit)

Return ONLY a valid JSON object in this format:
{{
    "file": "primary_document_name_or_email",
    "intent": "type_from_list",
    "confidence": 0.95
}}

Unified Context:
{context}
"""

EXTRACTION_PROMPT = """Analyze the following unified context (email and attachments) and extract all relevant data into a structured JSON format according to the provided schema.

CRITICAL INSTRUCTIONS FOR EXTRACTION:
1. Return ONLY valid JSON matching the exact schema provided below.
2. The `intent` field MUST exactly match the value specified in the schema.
3. The `document_type` array MUST only contain values from the enum defined in the schema.
4. Populate all required fields as strictly defined by the schema.
5. **DATE FORMATTING**: ALL extracted dates MUST be converted strictly to ISO 8601 format: "YYYY-MM-DD".
6. In `items`, `quantity` MUST be an integer, not a string or float (e.g. 40, not 40.0).
7. Map attachments into the `attachments` array. 
   - `type` MUST use only the enum values defined in the schema for attachments.
   - Classify each attachment strictly per-document, using ONLY that document's filename and extracted content. Do not reuse classifications from previous examples.
   - `contains` MUST be highly granular, listing specific data categories found in the file.
8. `missing_fields` MUST only contain actual schema field names that were expected but genuinely missing from the documents. Do not list inapplicable fields.
9. NEVER invent or fabricate values if they are not found in the documents.

Unified Context:
{context}

Return exactly the following JSON structure filled with the extracted data:
{schema}
"""
