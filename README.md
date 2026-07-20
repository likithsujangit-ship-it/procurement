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
├── venv/                # Local Python 3.13 virtual environment
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
│   ├── outputs/         # Generated summary.json, summary.txt, and search_index.json
│   ├── schemas/         # Dynamic Multi-Intent JSON Schemas
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
│       ├── link_extractor.py
│       ├── summarizer.py
│       ├── groq_client.py
│       ├── search_engine.py
│       └── utils.py
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
* **Per-Sender Query Loop**: Loops queries independently per sender if multiple addresses are listed.
* **Recursive Glob Search**: Searches directories recursively (`files/**/filename`) so that document extraction works no matter which subfolder a file is downloaded to.
* **Dynamic N Emails Parsing**: Extracts numeric parameters (e.g. "last 5", "latest 10") to cap inbox queries.

### 2. Email Sender (`sender/`)
* **Natural Language Command Parsing**: Extracts recipients, CC, BCC, attachments, subject context, and tone from text.
* **AI Content Generation**: Generates highly styled HTML templates (with inline CSS) and plain-text alternatives matching 12 different tones.
* **Attachment Verification**: Ensures files are available inside `sender/files/` before drafting.
* **MIME Construction & SMTP Transmission**: Builds standard compliant emails and transmits over TLS to Gmail SMTP.

### 3. Email Reader & Downloader (`reader/`)
* **OAuth 2.0 Credentials Manager**: Seamlessly manages `token.json` authorization so browser login is only needed once.
* **Attachment Organizer**: Saves files into `reader/files/<sender_prefix>/DD-MM-YYYY-(HH_MM_SS_fff)/` based on who sent the email and the exact millisecond received time.
* **Structural Document Extractors**: Dedicated layout readers for PDFs, DOCX (Word), PPTX (Slides), XLSX (Excel matrices), CSV, archives (ZIP), and OCR image scanning.
* **Resource Extractor**: Pulls out OTPs, meeting dates, phone numbers, tracking IDs, invoice IDs, and Drive/GitHub links.

### 4. AI Search Engine (`reader/tools/search_engine.py`)
* **Incremental File Indexing**: Scans all subfolders in `reader/files/` recursively. Uses size and mtime checks to skip unmodified files. Automatically indexes new downloads without manual re-indexing.
* **Typo-Tolerance (Fuzzy Similarity)**: Implements character bigram Jaccard similarity. Matches sender names or filenames even if the user makes spelling typos (e.g., matching `mitta.venakata` to `mitta.venkata2024` with a high similarity threshold).
* **Word Boundary Precision**: Uses regular expression word boundaries (`\bword\b`) for content searches.
* **Exact Filename Restrict**: If the search query matches any filename or stem exactly, the search engine restricts results to only those files.

### 5. Multi-Intent Intelligent Extraction (`reader/tools/intelligent_extractor/`)
* **Dynamic Intent Routing**: The `DocumentClassifier` analyzes the unified context of an email and its attachments to determine intent (e.g. `request_for_quotation`, `purchase_order`, `invoice`).
* **Schema-Agnostic LLM Extraction**: Based on the classified intent, `EntityExtractor` dynamically loads a standalone JSON Schema (e.g. `purchase_order_schema.json`) and passes it to the LLM to enforce strict structure and data types.
* **Granular Validation Rules**: `validate_extraction.py` verifies the LLM output against the dynamic schema, checks ISO 8601 date formats, ensures integers are formatted correctly (e.g., 40, not 40.0), and prevents context bleed. Console output displays concise 2-3 word explanations for any validation warnings.
* **Structured Context Storage**: Automatically saves the extraction output into a nested hierarchy: `outputs/intelligent_extraction/<username>/<timestamp>/`. Alongside the JSON, it generates a `summary.txt` file containing a brief AI-generated summary of the email's context.

---

## Setup & API Integration

### 1. Google Cloud OAuth Setup (Reader API)
* Enable the **Gmail API** in Google Cloud Console.
* Set the Publishing status to **Testing** and add your testing email address under **Test Users**.
* Download your Desktop Client ID JSON, rename it to `credentials.json`, and place it in the `reader/` directory.

### 2. SMTP app Password Setup (Sender SMTP)
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

### 4. File Content Extraction and AI Analysis
* **Extract text from a downloaded document**:
  `Extract document resume.pdf`
* **Extract text from a downloaded spreadsheet**:
  `Extract document report.xlsx`
* **Generate AI summary report for a local file**:
  `Summarize document invoice.pdf`

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

### 6. Intelligent Data Extraction (Multi-Intent)

* **Extract structured JSON data (e.g. POs, RFQs, Invoices) from an email**:
  * `Extract the structured JSON for the latest email from vendor@supplier.com`
  * `Extract the structured JSON for the last 1 email from procurement@corp.com`
* **Extract from multiple senders concurrently**:
  * `Extract the structured JSON for the latest email from vendor1@supplier.com and vendor2@supplier.com`
  
  *(The assistant will classify the email intent, extract commercial data, validate it against the corresponding JSON schema, and save the resulting JSON and AI `summary.txt` to `reader/outputs/intelligent_extraction/<username>/<date_time>/`)*
