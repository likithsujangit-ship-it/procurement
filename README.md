# EMAIL_AI: Complete Production-Ready AI Email Assistant

EMAIL_AI is an enterprise-grade, scalable AI-powered email and document analysis suite. It separates email transmission, inbox querying/document extraction, and natural language command orchestration into three independent, runnable packages:
1. **Sender (`sender/`)**: Parses natural language instructions, drafts emails using Llama 3.3 70B, compiles attachments, and sends messages over Gmail SMTP.
2. **Reader (`reader/`)**: Connects to Gmail API, fetches inbox messages, downloads attachments, parses multiple file types (PDF, Word, Excel, CSV, PPTX, Image OCR), and summarizes them into structured reports.
3. **Assistant (`assistant/`)**: Orchestrates unified requests by routing commands dynamically to the respective packages.

---

## Folder Structure

```text
EMAIL_AI/
├── README.md
├── run_tests.py         # Verification unit & integration test suite
├── venv/                # Local Python virtual environment
├── sender/
│   ├── .env
│   ├── config.py
│   ├── main.py
│   ├── requirements.txt
│   ├── README.md
│   ├── files/           # Attachment source files (e.g. resume.pdf)
│   ├── outputs/         # Outbox/temporary processing outputs
│   └── tools/
│       ├── __init__.py
│       ├── email_sender.py
│       ├── email_generator.py
│       ├── validator.py
│       ├── parser.py
│       ├── contacts.py
│       └── utils.py
├── reader/
│   ├── .env
│   ├── config.py
│   ├── credentials.json
│   ├── token.json
│   ├── main.py
│   ├── requirements.txt
│   ├── README.md
│   ├── files/           # Organized subfolders of downloaded attachments
│   │   └── <sender_prefix>/
│   │       └── <DD-MM-YYYY-(HH_MM_SS_fff)>/
│   │           └── downloaded_file.pdf
│   ├── outputs/         # Extracted JSON & summary files mirroring files layout
│   │   └── <sender_prefix>/
│   │       └── <DD-MM-YYYY-(HH_MM_SS_fff)>/
│   │           ├── <sender_prefix>_extracted_data.json
│   │           └── <sender_prefix>_summary.txt
│   ├── schemas/         # Dynamic Multi-Intent JSON Schemas & Master Schema
│   │   ├── master_procurement_schema.json
│   │   ├── request_for_quotation_schema.json
│   │   ├── purchase_order_schema.json
│   │   ├── invoice_schema.json
│   │   ├── delivery_note_schema.json
│   │   ├── quotation_response_schema.json
│   │   └── vendor_price_list_schema.json
│   └── tools/
│       ├── __init__.py
│       ├── gmail_auth.py
│       ├── gmail_reader.py
│       ├── attachment_downloader.py
│       ├── extractor.py
│       ├── pdf_reader.py
│       ├── docx_reader.py
│       ├── ppt_reader.py
│       ├── image_reader.py
│       ├── excel_reader.py
│       ├── csv_reader.py
│       ├── zip_reader.py
│       ├── tika_reader.py
│       ├── email_reader.py
│       ├── link_extractor.py
│       ├── summarizer.py
│       ├── groq_client.py
│       ├── search_engine.py
│       └── intelligent_extractor/
│           ├── __init__.py
│           ├── orchestrator.py
│           ├── classifier.py
│           ├── entity_extractor.py
│           ├── merger.py
│           ├── prompts.py
│           ├── exceptions.py
│           └── validate_extraction.py
└── assistant/
    ├── __init__.py
    ├── config.py         # Dynamic Namespace Call-Stack Import Loader
    ├── router.py
    ├── assistant.py      # Unified natural language CLI
    └── README.md
```

---

## Features Implemented & Explained

### 1. Unified Assistant (`assistant/`)
* **Namespace Isolation**: Uses a custom stack-trace routing module proxy in `sys.modules["config"]` to run both projects in one memory space without namespace collisions.
* **Central Intent Classifier**: Routes user prompts into actions: send, read, download, extract, summarize, or search.
* **Smart Natural Language Mail Extraction**: Routes instructions like `extract from this mail`, `extract latest from <email>`, or `extract from mail` directly to the full LLM document extraction pipeline.
* **Recursive Glob Search**: Searches directories recursively (`files/**/filename`) so that document extraction works no matter which subfolder a file is downloaded to.
* **Dynamic N Emails Parsing**: Extracts numeric parameters (e.g. "last 5", "latest 10") to cap inbox queries.

### 2. Email Sender (`sender/`)
* **Natural Language Command Parsing**: Extracts recipients, CC, BCC, attachments, subject context, and tone from text.
* **AI Content Generation**: Generates highly styled HTML templates (with inline CSS) and plain-text alternatives matching 12 different tones using Llama 3.3 70B.
* **Attachment Verification**: Ensures files are available inside `sender/files/` before drafting.
* **MIME Construction & SMTP Transmission**: Builds standard compliant emails and transmits over TLS to Gmail SMTP.

### 3. Email Reader & Downloader (`reader/`)
* **OAuth 2.0 Credentials Manager**: Seamlessly manages `token.json` authorization so browser login is only needed once.
* **Attachment Organizer**: Saves files into `reader/files/<sender_prefix>/DD-MM-YYYY-(HH_MM_SS_fff)/` based on who sent the email and the exact millisecond received time.
* **Universal Document & Email Extractors**: 
  - **Modern Formats**: Natively reads `.pdf` (text and scanned), `.docx` (Word), `.pptx`/`.ppt` (PowerPoint), `.xlsx` (Excel), and `.csv`.
  - **Legacy Formats**: Reads `.xls` (legacy Excel via `xlrd`), and `.doc`, `.rtf`, `.odt`, `.ods` (legacy Word, rich text, and OpenOffice formats via **Apache Tika**).
  - **Email Parsing**: Natively extracts subject, headers, and bodies from `.eml` and Outlook `.msg` files.
* **Robust Local OCR Pipeline**: Uses `ocrmypdf`, `Ghostscript`, and `Tesseract-OCR` for deep pre-processing of scanned PDFs and complex tables, seamlessly falling back to `pytesseract` and `PyMuPDF` for embedded images to ensure 100% text extraction without heavy cloud API dependencies.
* **Resource Extractor**: Pulls out OTPs, meeting dates, phone numbers, tracking IDs, invoice IDs, and Drive/GitHub links.

### 4. Enterprise Document-Intelligence Extraction Engine (`reader/tools/intelligent_extractor/`)
* **Master Procurement Schema**: Standardized top-level extraction payload covering `intent`, `document_type`, `buyer`, `supplier`, `rfq_number`, `po_number`, `invoice_number`, `shipment_id`, `items`, `commercial_terms`, `delivery_requirements`, `shipping_details`, `approval`, `attachments`, `missing_fields`, `conflicts`, and `confidence_score`.
* **Strict 8-Rule Document Intelligence Policy**:
  1. **Document Identity Authority**: `buyer` and `supplier` company names, addresses, tax IDs (GSTIN), and contact emails are extracted directly from attachment text (`RFQ.pdf`, PO, Invoice), overriding forwarding envelope senders.
  2. **Envelope Discrepancy Auditing**: Disagreements between email envelope senders and document contact emails are surfaced in `conflicts` (e.g. `sender_vs_buyer_email`).
  3. **ISO 8601 Date Normalization**: Standardizes all dates to `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS+HH:MM` and records date discrepancies.
  4. **Multi-Item Line Extraction (`items[]`)**: Cross-checks part numbers, descriptions, quantities, units, and material grades across `BOM.xlsx`, `RFQ.pdf`, and `Technical_Specification.docx`.
  5. **Scoped Commercial & Delivery Terms**: Captures payment terms, Incoterms 2020, quotation validity, warranty, partial shipment flags, and specifically **GST Rate, TDS Rate, Security Deposit (SD), Performance Bank Guarantee (PBG), Liquidated Damages (LD), and precise Delivery Requirements**.
  6. **Attachment MIME Classification**: Automatically infers MIME types and flags `extracted: true/false`.
  7. **Missing Fields Audit**: Tracks expected schema fields missing from source documents.
  8. **Dynamic Confidence Score**: Computes a Float (0.0–1.0) adjusted for conflicts, missing fields, or OCR artifacts.
* **Directory Layout Parity**: Output files are written to `reader/outputs/<sender_prefix>/<DD-MM-YYYY-(HH_MM_SS_fff)>/`:
  * `<sender_prefix>_extracted_data.json` (Flat structured JSON object matching master schema)
  * `<sender_prefix>_summary.txt` (Human-readable executive text report)
* **Zero Extra File Clutter**: Ensures no secondary dynamic JSON files or root outputs are created.

### 5. Advanced Groq Client & Resilient Rate Limit Protection (`reader/tools/groq_client.py`)
* **Primary LPU Engine**: Powered by Meta's `llama-3.3-70b-versatile` running at 300+ tokens/sec on Groq LPUs.
* **Context Truncation (`merger.py`)**: Caps prompt context size to 4,000 max tokens (~16,000 characters) preserving beginning and end context, ensuring total tokens stay well within Groq TPM limits.
* **Multi-Tiered Fallback Chain**: On HTTP 429 (rate limit) or 413 (token limit), automatically performs a 2-second backoff delay and falls back smoothly through `llama-3.1-8b-instant` $\rightarrow$ `mixtral-8x7b-32768` $\rightarrow$ `llama3-70b-8192` with prompt context safety.

### 6. AI Search Engine (`reader/tools/search_engine.py`)
* **Incremental File Indexing**: Scans all subfolders in `reader/files/` recursively. Uses size and mtime checks to skip unmodified files.
* **Typo-Tolerance (Fuzzy Similarity)**: Uses character bigram Jaccard similarity to match senders or filenames even with spelling typos (e.g., matching `mitta.venakata` to `mitta.venkata2024`).
* **Word Boundary Precision**: Employs regex word boundaries (`\bword\b`) for content searches.
* **Exact Filename Restrict**: Restricts candidates strictly to exact matches when a query matches a filename or stem exactly.
* **Multi-Extension Support**: Filters by multiple extensions (e.g. `find mitta with .pdf and .pptx`).

---

## Setup & API Integration

### 1. Google Cloud OAuth Setup (Reader API)
* Enable the **Gmail API** in Google Cloud Console.
* Set Publishing status to **Testing** and add your testing email address under **Test Users**.
* Download your Desktop Client ID JSON, rename it to `credentials.json`, and place it in the `reader/` directory.

### 2. SMTP App Password Setup (Sender SMTP)
* Enable **2-Step Verification** on your Google Account.
* Generate an **App Password** for "Mail".
* Copy the 16-character code and paste it as `SMTP_PASSWORD` in `sender/.env`. Set `SMTP_EMAIL` to your Gmail address.

### 3. Groq API Setup (AI Completions)
* Create an API Key in the [Groq Console](https://console.groq.com/).
* Set this key as `GROQ_API_KEY` in both `sender/.env` and `reader/.env`.

---

## Terminal Commands & Examples

To start the assistant, navigate to the root directory, activate the virtual environment, and run:
```bash
source venv/bin/activate
python -m assistant.assistant
```

Inside the **`ASSISTANT >`** CLI prompt, you can run these commands:

### 1. Sending Emails
* **Single recipient, no attachments**:
  `Send mail to friend@example.com regarding project sync saying let's meet at 2pm.`
* **Multiple recipients, no attachments**:
  `Send email to hr@gmail.com and manager@gmail.com regarding leave request saying I am sick today.`
* **Single recipient with attachment**:
  *(Put `resume.pdf` in `sender/files/` first)*
  `Send resume.pdf to recruiter@example.com regarding job application saying please review my resume.`
* **Multiple recipients with multiple attachments**:
  *(Put `report.xlsx` and `slides.pptx` in `sender/files/` first)*
  `Send report.xlsx and slides.pptx to director@corp.com and supervisor@corp.com regarding quarterly status saying here are the files.`

### 2. Reading and Summarizing Inbox Emails
* **Summarize the single latest email**:
  `Summarize latest email from manager@gmail.com`
* **Summarize last N emails from a sender**:
  `Summarize last 3 emails from client@domain.com`
* **Summarize emails from multiple distinct senders**:
  `Summarize emails from likithtech2006@gmail.com and antigravitysubtemp@gmail.com`

### 3. Downloading Attachments
* **Download attachments from the single latest email**:
  `Download latest attachments from antigravitysubtemp@gmail.com`
* **Download last N attachments from a sender**:
  `Download last 5 attachments from likithtech2006@gmail.com`
* **Download attachments from multiple distinct senders**:
  `Download attachments from likithtech2006@gmail.com and antigravitysubtemp@gmail.com`

### 4. Intelligent Data Extraction (Multi-Intent & Attachments)
* **Extract structured JSON data from email & attachments**:
  * `Extract from this mail`
  * `Extract latest from pratap.veera2024@vitstudent.ac.in`
  * `Extract the structured JSON for the latest email from vendor@supplier.com`
* **Extract from multiple senders concurrently**:
  * `Extract the structured JSON for the latest email from vendor1@supplier.com and vendor2@supplier.com`
  
  *(The assistant downloads attachments to `reader/files/<sender>/<timestamp>/`, parses all documents, runs Llama 3.3 70B entity extraction, and writes `<sender>_extracted_data.json` and `<sender>_summary.txt` inside `reader/outputs/<sender>/<timestamp>/`)*

### 5. Natural Language AI Search Engine
* **Search by Exact/Partial Filename**:
  * `Find construction.pdf` (Strictly returns only files named `construction.pdf` across all folders)
  * `Find resume` (Returns any file name containing "resume")
* **Search by Mail/Sender Folder**:
  * `Search mittavenkatasaisujan` (Lists all folders and files sent by `mittavenkatasaisujan`)
  * `Search google` (Lists all folders and files sent by `google`)
* **Search by Typo-Tolerant Names**:
  * `Find mitta.venakata` (Fuzzily matches the folder `mitta.venkata2024` despite spelling typos)
* **Search with Multiple File Type Extensions**:
  * `Find mitta with .pdf and .pptx` (Filters to return only PDF and PPTX attachments received from folders containing "mitta")
  * `Find .pptx` (Lists all PowerPoint files across all sender folders)
* **Search by Document Context**:
  * `Find documents about Python` (Searches within parsed document text contexts for keywords)
  * `Show Amazon bills` (Filters for files sent by "Amazon" containing billing text)

---

## Quick Reference: All Commands Explained

Below is the condensed list of all core functionalities, a single example command, and how it works in 3-4 words.

| Functionality | Example Command | How it works (3-4 words) |
|---|---|---|
| **Send Email** | `Send resume.pdf to hr@gmail.com` | Parses NLP to SMTP |
| **Summarize Emails** | `Summarize latest from boss@company.com` | Groq LPU text summarization |
| **Download Attachments** | `Download last 3 from vendor@company.com` | Gmail API file extraction |
| **Extract JSON (Intelligent)** | `Extract latest from supplier@company.com` | Multi-stage document intelligence |
| **Search Files/Folders** | `Find .pdf from vendor` | Fuzzy glob regex matching |

