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
│   ├── outputs/         # Generated summary.json and summary.txt
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

## Features Implemented

### 1. Email Sender (`sender/`)
* **Natural Language Command Parsing**: Extracts recipients, CC, BCC, attachments, subject context, and tone from text.
* **AI Content Generation**: Generates highly styled HTML templates (with inline CSS) and plain-text alternatives matching 12 different tones.
* **Attachment Verification**: Ensures files are available inside `sender/files/` before drafting.
* **MIME Construction & SMTP Transmission**: Builds standard compliant emails and transmits over TLS to Gmail SMTP.

### 2. Email Reader (`reader/`)
* **OAuth 2.0 Credentials Manager**: Seamlessly manages `token.json` authorization so browser login is only needed once.
* **Attachment Organizer**: Saves files into `reader/files/<sender_prefix>/DD-MM-YYYY-(HH_MM_SS_fff)/` based on who sent the email and the exact millisecond received time.
* **Structural Document Extractors**: Dedicated layout readers for PDFs, DOCX (Word), PPTX (Slides), XLSX (Excel matrices), CSV, archives (ZIP), and OCR image scanning.
* **Resource Extractor**: Pulls out OTPs, meeting dates, phone numbers, tracking IDs, invoice IDs, and Drive/GitHub links.
* **Deep Synthesizer**: Uses Groq Llama 3.3 70B to generate structured action summaries saved as JSON and TXT.

### 3. Unified Assistant (`assistant/`)
* **Namespace Isolation**: Uses a custom stack-trace routing module proxy in `sys.modules["config"]` to run both projects in one memory space without namespace collisions.
* **Intent Classifier**: Automatically maps prompts to send, read, download, extract, summarize, or search tasks.
* **Per-Sender Query Loop**: Loops queries independently per sender if multiple addresses are given.
* **Recursive Glob Search**: Searches directories recursively (`files/**/filename`) so that document extraction works no matter which subfolder a file is downloaded to.
* **Dynamic N Emails Parsing**: Extracts numeric parameters (e.g. "last 5", "latest 10") to cap queries.

### 4. AI Search Engine (`reader/tools/search_engine.py`)
* **Incremental File Indexing**: Scans all subfolders in `reader/files/` recursively. Uses size and mtime checks to skip unmodified files.
* **Semantic Query Processing**: Groq-based Llama parser that converts user prompts into structured filters (by file type, sender, and search terms).
* **Multi-Criteria Ranking**: Calculates a match score based on filename similarity, term frequency in extracted content, keyword tags, and semantic relevance snippets.

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

* **Find matching invoices**:
  `Find invoice`
* **Search for offer letters**:
  `Search offer letter`
* **Show all documents related to Python**:
  `Find documents about Python`
* **Show Amazon bills**:
  `Show Amazon bills`
* **Find files sent by Google**:
  `Find PDFs from Google`
