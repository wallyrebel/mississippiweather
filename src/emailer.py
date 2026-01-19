"""
Email sender for Mississippi Weather Desk.

Sends weather briefings via SMTP (Gmail).
"""

import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
import html

import pytz

logger = logging.getLogger(__name__)

CT_TIMEZONE = pytz.timezone("America/Chicago")


def get_smtp_config() -> dict:
    """Get SMTP configuration from environment variables."""
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER"),
        "password": os.getenv("SMTP_PASS"),
        "from_addr": os.getenv("EMAIL_FROM"),
        "to_addr": os.getenv("EMAIL_TO"),
    }


def build_email_subject(time_of_day: str, date_str: str) -> str:
    """Build the email subject line."""
    return f"Mississippi Weather Briefing — {time_of_day} — {date_str}"


def markdown_to_html(markdown_text: str) -> str:
    """
    Simple markdown to HTML conversion.
    
    Handles headers, bold, italics, and paragraphs.
    """
    lines = markdown_text.split("\n")
    html_lines = []
    in_list = False
    
    for line in lines:
        line = line.rstrip()
        
        # Headers
        if line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2 style='color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;'>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1 style='color: #1a5276;'>{html.escape(line[2:])}</h1>")
        # Bold
        elif line.startswith("**") and line.endswith("**"):
            html_lines.append(f"<p><strong>{html.escape(line[2:-2])}</strong></p>")
        # List items
        elif line.startswith("- ") or line.startswith("• "):
            if not in_list:
                html_lines.append("<ul style='margin-left: 20px;'>")
                in_list = True
            html_lines.append(f"<li>{process_inline_formatting(line[2:])}</li>")
        # Empty line
        elif not line.strip():
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
        # Regular paragraph
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{process_inline_formatting(line)}</p>")
    
    if in_list:
        html_lines.append("</ul>")
    
    return "\n".join(html_lines)


def process_inline_formatting(text: str) -> str:
    """Process inline markdown formatting (bold, italic)."""
    # Escape HTML first
    text = html.escape(text)
    
    # Bold: **text**
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Italic: *text*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    
    return text


def build_html_email(
    headline: str,
    highlights: List[str],
    article_body: str,
    data_gaps: List[str],
    sources: List[str]
) -> str:
    """
    Build HTML email content.
    
    Args:
        headline: Article headline
        highlights: List of 5 bullet highlights
        article_body: Full article text (markdown)
        data_gaps: List of unavailable data sources
        sources: List of data sources used
        
    Returns:
        HTML string
    """
    now = datetime.now(CT_TIMEZONE)
    timestamp = now.strftime("%B %d, %Y at %I:%M %p CT")
    
    highlights_html = "\n".join([
        f"<li style='margin-bottom: 8px;'>{html.escape(h)}</li>" 
        for h in highlights
    ])
    
    article_html = markdown_to_html(article_body)
    
    sources_html = ", ".join([html.escape(s) for s in sources]) if sources else "NWS, SPC, WPC, NHC"
    
    data_gaps_section = ""
    if data_gaps:
        gaps_text = ", ".join([html.escape(g) for g in data_gaps])
        data_gaps_section = f"""
        <div style="background-color: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin: 15px 0; border-radius: 5px;">
            <strong>⚠️ Data Gaps:</strong> {gaps_text}
        </div>
        """
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: Georgia, 'Times New Roman', serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; color: #333;">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1a5276 0%, #2980b9 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h1 style="margin: 0; font-size: 24px;">🌤️ Mississippi Weather Desk</h1>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">{timestamp}</p>
        </div>
        
        <!-- Headline -->
        <h1 style="color: #1a5276; font-size: 28px; border-bottom: 3px solid #3498db; padding-bottom: 10px;">
            {html.escape(headline)}
        </h1>
        
        <!-- Key Highlights -->
        <div style="background-color: #e8f4f8; padding: 15px 20px; border-left: 4px solid #3498db; margin: 20px 0; border-radius: 0 8px 8px 0;">
            <h2 style="margin-top: 0; color: #2c3e50;">📌 Key Highlights</h2>
            <ul style="padding-left: 20px;">
                {highlights_html}
            </ul>
        </div>
        
        {data_gaps_section}
        
        <!-- Main Article -->
        <div style="margin: 20px 0;">
            {article_html}
        </div>
        
        <!-- Sources Footer -->
        <div style="background-color: #f5f5f5; padding: 15px; border-radius: 8px; margin-top: 30px; font-size: 14px;">
            <strong>Sources:</strong> {sources_html}
            <br><br>
            <em style="color: #666;">This briefing was automatically generated by Mississippi Weather Desk using official U.S. government weather data. 
            For life-threatening emergencies, always refer to official NWS warnings.</em>
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
            Mississippi Weather Desk • Automated Weather Intelligence
        </div>
        
    </body>
    </html>
    """
    
    return html_content


def build_plain_text_email(
    headline: str,
    highlights: List[str],
    article_body: str,
    data_gaps: List[str],
    sources: List[str]
) -> str:
    """
    Build plain text email content.
    
    Args:
        headline: Article headline
        highlights: List of 5 bullet highlights
        article_body: Full article text
        data_gaps: List of unavailable data sources
        sources: List of data sources used
        
    Returns:
        Plain text string
    """
    now = datetime.now(CT_TIMEZONE)
    timestamp = now.strftime("%B %d, %Y at %I:%M %p CT")
    
    highlights_text = "\n".join([f"  • {h}" for h in highlights])
    sources_text = ", ".join(sources) if sources else "NWS, SPC, WPC, NHC"
    
    text_content = f"""MISSISSIPPI WEATHER DESK
{timestamp}

{'=' * 60}

{headline}

{'=' * 60}

KEY HIGHLIGHTS:
{highlights_text}

"""

    if data_gaps:
        text_content += f"DATA GAPS: {', '.join(data_gaps)}\n\n"
    
    # Strip markdown formatting for plain text
    clean_body = article_body
    clean_body = clean_body.replace("## ", "\n").replace("# ", "\n")
    clean_body = clean_body.replace("**", "")
    
    text_content += f"""{'-' * 60}

{clean_body}

{'-' * 60}

SOURCES: {sources_text}

This briefing was automatically generated by Mississippi Weather Desk using 
official U.S. government weather data. For life-threatening emergencies, 
always refer to official NWS warnings.

{'=' * 60}
Mississippi Weather Desk • Automated Weather Intelligence
"""
    
    return text_content


def send_email(
    headline: str,
    highlights: List[str],
    article_body: str,
    time_of_day: str,
    date_str: str,
    data_gaps: List[str],
    sources: List[str]
) -> bool:
    """
    Send weather briefing email.
    
    Args:
        headline: Article headline
        highlights: List of 5 bullet highlights
        article_body: Full article text
        time_of_day: "Morning", "Afternoon", or "Evening"
        date_str: Date string (YYYY-MM-DD)
        data_gaps: List of unavailable data sources
        sources: List of data sources used
        
    Returns:
        True if email sent successfully, False otherwise
    """
    config = get_smtp_config()
    
    # Validate configuration
    if not config["user"] or not config["password"]:
        logger.error("SMTP credentials not configured")
        return False
    
    if not config["from_addr"] or not config["to_addr"]:
        logger.error("Email addresses not configured")
        return False
    
    # Build email
    subject = build_email_subject(time_of_day, date_str)
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from_addr"]
    msg["To"] = config["to_addr"]
    
    # Plain text version
    text_content = build_plain_text_email(headline, highlights, article_body, data_gaps, sources)
    part1 = MIMEText(text_content, "plain")
    
    # HTML version
    html_content = build_html_email(headline, highlights, article_body, data_gaps, sources)
    part2 = MIMEText(html_content, "html")
    
    msg.attach(part1)
    msg.attach(part2)
    
    # Send email
    try:
        logger.info(f"Connecting to SMTP server {config['host']}:{config['port']}...")
        
        with smtplib.SMTP(config["host"], config["port"]) as server:
            server.starttls()
            server.login(config["user"], config["password"])
            server.sendmail(config["from_addr"], [config["to_addr"]], msg.as_string())
        
        logger.info(f"Email sent successfully to {config['to_addr']}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
