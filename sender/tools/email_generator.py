"""
Email Generator Module for EMAIL SENDER.
Generates professional plain text and HTML emails using Groq LLM (Llama 3.3 70B) 
with customizable tones and templates.
"""

import json
from typing import Dict, Any, Optional
from groq import Groq
from config import Config
from tools.utils import setup_logger

logger = setup_logger("email_generator")


def generate_email_content(
    subject_hint: str,
    body_hint: str,
    tone: str,
    sender_name: Optional[str] = None
) -> Dict[str, str]:
    """
    Generates subject, plain text body, and HTML body for an email.
    Uses Groq API for generation, with a robust fallback.
    
    Args:
        subject_hint: Description or context of the subject.
        body_hint: Core message or instructions for the body.
        tone: The target style (e.g., 'casual', 'formal', 'meeting-request').
        sender_name: Optional name to sign the email.
        
    Returns:
        A dict containing 'subject', 'text_body', and 'html_body'.
    """
    logger.info(f"Generating email content with tone '{tone}' using Groq.")
    
    if Config.GROQ_API_KEY and Config.GROQ_API_KEY != "gsk_your_groq_api_key_here":
        try:
            return _generate_with_groq(subject_hint, body_hint, tone, sender_name)
        except Exception as e:
            logger.error(f"Groq email generation failed: {e}. Falling back to template generation.")
            
    return _generate_with_template(subject_hint, body_hint, tone, sender_name)


def _generate_with_groq(
    subject_hint: str,
    body_hint: str,
    tone: str,
    sender_name: Optional[str] = None
) -> Dict[str, str]:
    """Uses Groq Llama 3.3 70B to generate structured plain-text and HTML email."""
    client = Groq(api_key=Config.GROQ_API_KEY)
    
    sender_sig = sender_name or "AI Assistant"
    
    system_prompt = (
        "You are an expert copywriter and email assistant. "
        "Your task is to write a highly professional, well-formatted email based on user inputs.\n\n"
        "You must respond ONLY with a JSON object. Do not write any markdown (like ```json), introduction, or follow-up text. "
        "The JSON object must have three string fields:\n"
        "- 'subject': A clear, professional, and engaging subject line.\n"
        "- 'text_body': A clean plain-text representation of the email body, properly formatted with line breaks.\n"
        "- 'html_body': A complete, styled, premium HTML email. Use inline CSS. Include a nice professional header, "
        "  clean margins, Inter/Helvetica typography, and a modern footer with signature. Use warm professional colors "
        "  (like navy #0A2540, light grey background #F8F9FA, dark text #2D3142).\n\n"
        f"Apply the following tone: {tone}\n"
        f"Sign the email as: {sender_sig}\n"
    )
    
    user_prompt = (
        f"Subject context/hint: {subject_hint}\n"
        f"Body context/hint: {body_hint}\n"
    )
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        response_format={"type": "json_object"}
    )
    
    raw_content = response.choices[0].message.content.strip()
    logger.debug(f"Raw LLM Email Output: {raw_content}")
    
    return json.loads(raw_content)


def _generate_with_template(
    subject_hint: str,
    body_hint: str,
    tone: str,
    sender_name: Optional[str] = None
) -> Dict[str, str]:
    """Fallback email generator using static templates and placeholders."""
    logger.debug("Generating email content with standard template fallback.")
    
    sender_sig = sender_name or "AI Assistant"
    subject = subject_hint or f"Notification: {tone.replace('-', ' ').title()}"
    
    # Simple formatting of the body hint
    paragraphs = [p.strip() for p in body_hint.split("\n") if p.strip()]
    formatted_paragraphs = "\n\n".join(paragraphs)
    
    # Build text body
    text_body = (
        f"Hello,\n\n"
        f"{formatted_paragraphs}\n\n"
        f"Best regards,\n"
        f"{sender_sig}"
    )
    
    # Build premium styled HTML body
    html_paragraphs = "".join(f"<p style='margin: 0 0 16px 0;'>{p}</p>" for p in paragraphs)
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8f9fa; padding: 20px;">
    <tr>
      <td align="center">
        <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e9ecef;">
          <!-- Header -->
          <tr>
            <td style="background-color: #0A2540; padding: 30px 40px; text-align: left;">
              <h1 style="color: #ffffff; font-size: 22px; margin: 0; font-weight: 600;">{subject}</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 40px; color: #2D3142; font-size: 16px; line-height: 1.6; text-align: left;">
              {html_paragraphs}
              <hr style="border: 0; border-top: 1px solid #e9ecef; margin: 30px 0 20px 0;" />
              <p style="margin: 0; color: #6c757d; font-size: 14px;">
                Warm regards,<br />
                <strong style="color: #0A2540;">{sender_sig}</strong>
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color: #f1f3f5; padding: 20px 40px; text-align: center; font-size: 12px; color: #868e96;">
              This email was generated and sent by EMAIL_AI.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    return {
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body
    }
