# AI Email Sender

An independent Python tool to draft and send emails using natural language prompts. Powered by **Groq Llama 3.3 70B** and **SMTP**.

## Features

- **Natural Language Command Processing**: Extracts recipient, CC, BCC, attachments, tone, and subject hints.
- **AI Content Generator**: Writes professional or casual emails with matching HTML and plain text alternatives using Llama-3.3.
- **Dynamic File Attachments**: Automatically validates file existences under the `files/` folder before drafting.
- **Tones Supported**: Professional, Casual, Formal, Follow-up, Thank You, Meeting Request, Leave Request, Internship Request, Complaint, Support, Application, Reminder.

---

## Environment Configuration (`.env`)

Create a `.env` file in the `sender/` directory with the following contents:

```env
# Groq API Configuration
GROQ_API_KEY=gsk_your_groq_api_key_here

# SMTP Configuration (Default is Gmail)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password_here

# Application Configuration
LOG_LEVEL=INFO
DRY_RUN=False
```

### Gmail SMTP App Password Setup
1. Go to your **Google Account settings**.
2. Enable **2-Step Verification** (required for app passwords).
3. Search or navigate to **App Passwords**.
4. Generate a new password, selecting "Mail" and "Other (Custom name)".
5. Copy the 16-character code and paste it into the `SMTP_PASSWORD` field inside `sender/.env`.

---

## Installation & Running

Ensure you have Python 3.13 installed.

```bash
# Navigate to sender directory
cd sender

# Install dependencies
pip install -r requirements.txt

# Run interactive CLI
python main.py
```

Place files to be sent as attachments inside the `sender/files/` directory before referencing them in your CLI commands.
