import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _get_smtp_credentials():
    sender = os.getenv("EMAIL")
    password = os.getenv("EMAIL_PASSWORD")
    if not sender or not password:
        raise RuntimeError("EMAIL and EMAIL_PASSWORD environment variables are not set")
    return sender, password


def send_verification_email(recipient_email: str, code: str) -> None:
    EMAIL_SENDER, EMAIL_PASSWORD = _get_smtp_credentials()
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1f2937; padding: 20px;">
        <h2 style="color: #667eea;">Verify your CropMonitor account</h2>
        <p>Hi there,</p>
        <p>Use the code below to verify your account. It expires in <strong>10 minutes</strong>.</p>
        <div style="display:inline-block;padding:16px 32px;background:#f3f4f6;border-radius:8px;
                    font-size:2rem;font-weight:bold;letter-spacing:8px;margin:16px 0;color:#667eea;">
            {code}
        </div>
        <p style="color:#6b7280;font-size:12px;">If you did not sign up, you can ignore this email.</p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your CropMonitor verification code"
    msg["From"] = EMAIL_SENDER
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)


def send_delete_confirmation_email(recipient_email: str, confirm_link: str) -> None:
    EMAIL_SENDER, EMAIL_PASSWORD = _get_smtp_credentials()
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1f2937; padding: 20px;">
        <h2 style="color: #d32f2f;">Delete your FarmSense account</h2>
        <p>Hi there,</p>
        <p>We received a request to permanently delete your FarmSense account associated with
           <strong>{recipient_email}</strong>.</p>
        <p>If you made this request, tap the button below to confirm. This link expires in
           <strong>30 minutes</strong>.</p>
        <div style="margin: 24px 0;">
            <a href="{confirm_link}"
               style="background:#d32f2f;color:#ffffff;padding:14px 28px;border-radius:6px;
                      text-decoration:none;font-weight:bold;font-size:15px;">
                Confirm Account Deletion
            </a>
        </div>
        <p style="color:#6b7280;font-size:12px;">
            If you did NOT request this, please ignore this email. Your account will remain active.
        </p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Confirm your FarmSense account deletion"
    msg["From"] = EMAIL_SENDER
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)


def send_password_reset_email(recipient_email: str, code: str) -> None:
    EMAIL_SENDER, EMAIL_PASSWORD = _get_smtp_credentials()
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1f2937; padding: 20px;">
        <h2 style="color: #667eea;">Reset your FarmSense password</h2>
        <p>Hi there,</p>
        <p>Use the code below to reset the password for <strong>{recipient_email}</strong>.
           It expires in <strong>15 minutes</strong>.</p>
        <div style="display:inline-block;padding:16px 32px;background:#f3f4f6;border-radius:8px;
                    font-size:2rem;font-weight:bold;letter-spacing:8px;margin:16px 0;color:#667eea;">
            {code}
        </div>
        <p style="color:#6b7280;font-size:12px;">
            If you did not request a password reset, you can safely ignore this email.
        </p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your FarmSense password reset code"
    msg["From"] = EMAIL_SENDER
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
