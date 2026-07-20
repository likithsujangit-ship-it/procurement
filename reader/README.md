# AI Email Reader & Attachment Extractor

An independent Python tool to query Gmail inbox, download attachments, read contents of documents (PDF, DOCX, PPTX, XLSX, CSV, ZIP, Image OCR), and synthesize the information using **Groq Llama 3.3 70B**.

## Features

- **Advanced Search Filters**: Retrieve emails by unread status, starred status, sender lists, date intervals, and presence of attachments.
- **Auto-Attachment Downloader**: Automatically downloads and saves attachments into `reader/files/`.
- **Structural File Parsers**:
  - **PDF**: Full text layout parsing (`pypdf`).
  - **DOCX**: Paragraphs and cell table reading (`python-docx`).
  - **PPTX**: Slide-by-slide text extraction (`python-pptx`).
  - **XLSX**: Iterative sheet cell matrix rendering (`openpyxl`).
  - **CSV**: Text parsing row-by-row (`csv`).
  - **ZIP**: Archive file list parsing (`zipfile`).
  - **OCR**: Converts images to text using pytesseract.
- **Resource Classifier**: Pulls out OTPs, meeting dates, links (OneDrive, Google Drive, GitHub, URLs), email addresses, invoice numbers, reference numbers, and tracking codes.
- **AI Summary & Extraction Reports**: Generates prioritized summaries, pending actions, task matrices, and master procurement JSON extractions saved directly under `outputs/<sender_prefix>/<timestamp>/` as `<prefix>_extracted_data.json` and `<prefix>_summary.txt`.

---

## Google Cloud Console Setup (OAuth Credentials)

To access the Gmail API, you need to set up credentials in Google Cloud:
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project called **EmailAI**.
3. Go to the **API Library** and search for **Gmail API**. Enable it.
4. Set up the **OAuth Consent Screen**:
   - User Type: **External**
   - Fill in app name (e.g. EmailAI) and support email.
   - Under **Test Users**, add your Gmail email address that you wish to read.
5. Create Credentials:
   - Click **Create Credentials** -> select **OAuth client ID**.
   - Application Type: **Desktop app**.
   - Download the generated JSON credentials file.
   - Rename this file to `credentials.json` and save it directly in the `reader/` directory.

On your first run, a browser tab will open asking you to authenticate. After granting access, `token.json` will be saved, caching your authentication credentials.

---

## Dependencies & External Tools

This package requires Python 3.13 and some external document-reading packages.

### Tesseract OCR Installation (For Images)
- **macOS**: Install Tesseract using Homebrew:
  ```bash
  brew install tesseract
  ```
- **Windows**: Download the UB Mannheim installer from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki) and add `C:\Program Files\Tesseract-OCR` to your System Env Path.

---

## Installation & Running

```bash
# Navigate to reader directory
cd reader

# Install dependencies
pip install -r requirements.txt

# Place your downloaded credentials.json in the reader/ folder
# Run main.py to authenticate and launch the interactive loop
python main.py
```
