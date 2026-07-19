# Unified AI Assistant

This package coordinates both the **EMAIL SENDER** and **EMAIL READER** components under a unified natural language interface. It can router user prompts to draft emails, query the inbox, summarize attachments, download files, and run OCR on images.

## Architecture

The assistant leverages a central Router module (`assistant/router.py`) that uses **Groq (Llama 3.3 70B)** or regular expressions to classify user prompts into one of the following operations:
1. `SEND_EMAIL` (Routes to `sender/` tools)
2. `READ_EMAIL` (Routes to `reader/` tools)
3. `SUMMARIZE_EMAIL` (Routes to `reader/` tools and summaries)
4. `DOWNLOAD_ATTACHMENTS` (Downloads files)
5. `EXTRACT_FILE` (Extracts text using specialized document readers)
6. `SUMMARIZE_FILE` (Analyzes individual documents/invoices on disk)

---

## Configuration

The assistant automatically maps python search paths to find package dependencies in sibling folders (`sender/` and `reader/`).

Ensure the environment files are set up in:
- `sender/.env`
- `reader/.env`

---

## Running the Unified Assistant

Launch the interactive CLI from the root `EMAIL_AI/` directory:

```bash
# Verify your python path and run
python assistant/assistant.py
```

### Examples of Valid Input Commands
* **Drafting mail**: `Send mail to hr regarding internship saying I want to apply.`
* **Reading inbox**: `Read latest 5 emails from boss@corp.com.`
* **Summarization**: `Summarize latest email from admin.`
* **Attachment management**: `Download latest attachments from manager.`
* **Local file extraction**: `Extract pdfs invoice_102.pdf`
* **Local file summary**: `Summarize resume.docx`
