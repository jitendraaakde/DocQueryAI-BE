"""Email service for OTP and notifications."""

import logging
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory OTP storage (use Redis in production)
_otp_store: dict = {}


class EmailService:
    """Service for sending emails and managing OTP."""

    def __init__(self):
        self.smtp_host = getattr(settings, 'SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_user = getattr(settings, 'SMTP_USER', None)
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
        self.from_email = getattr(settings, 'FROM_EMAIL', self.smtp_user)
    
    def _is_configured(self) -> bool:
        """Check if email service is configured."""
        return bool(self.smtp_user and self.smtp_password)
    
    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP."""
        return ''.join(random.choices(string.digits, k=length))
    
    def store_otp(self, email: str, otp: str, expires_minutes: int = 10) -> None:
        """Store OTP with expiration."""
        _otp_store[email] = {
            "otp": otp,
            "expires_at": datetime.utcnow() + timedelta(minutes=expires_minutes),
            "attempts": 0
        }
    
    def verify_otp(self, email: str, otp: str) -> tuple[bool, str]:
        """Verify OTP for an email."""
        if email not in _otp_store:
            return False, "No OTP found. Please request a new one."
        
        stored = _otp_store[email]
        
        # Check expiration
        if datetime.utcnow() > stored["expires_at"]:
            del _otp_store[email]
            return False, "OTP has expired. Please request a new one."
        
        # Check attempts
        if stored["attempts"] >= 5:
            del _otp_store[email]
            return False, "Too many attempts. Please request a new OTP."
        
        # Increment attempts
        stored["attempts"] += 1
        
        # Verify
        if stored["otp"] == otp:
            del _otp_store[email]
            return True, "OTP verified successfully."
        
        return False, f"Invalid OTP. {5 - stored['attempts']} attempts remaining."
    
    async def send_otp_email(self, email: str, purpose: str = "verification") -> tuple[bool, str]:
        """Send OTP email."""
        if not self._is_configured():
            # Dev mode - just generate and store, log it
            otp = self.generate_otp()
            self.store_otp(email, otp)
            logger.info(f"DEV MODE - OTP for {email}: {otp}")
            return True, f"OTP sent (dev mode: {otp})"
        
        otp = self.generate_otp()
        self.store_otp(email, otp)
        
        subject_map = {
            "verification": "Verify your DocQuery AI account",
            "password_reset": "Reset your DocQuery AI password",
            "2fa": "Your DocQuery AI 2FA code"
        }
        
        subject = subject_map.get(purpose, "Your DocQuery AI verification code")
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                <h1 style="color: white; margin: 0;">DocQuery AI</h1>
            </div>
            
            <div style="background: #1e293b; padding: 30px; border-radius: 10px; color: #e2e8f0;">
                <h2 style="color: #f1f5f9; margin-top: 0;">Your Verification Code</h2>
                <p>Use the following code to complete your {purpose.replace('_', ' ')}:</p>
                
                <div style="background: #0f172a; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #a78bfa;">{otp}</span>
                </div>
                
                <p style="color: #94a3b8; font-size: 14px;">This code expires in 10 minutes.</p>
                <p style="color: #94a3b8; font-size: 14px;">If you didn't request this code, please ignore this email.</p>
            </div>
            
            <p style="color: #64748b; font-size: 12px; text-align: center; margin-top: 20px;">
                © 2024 DocQuery AI. All rights reserved.
            </p>
        </body>
        </html>
        """
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = email
            
            msg.attach(MIMEText(f"Your verification code is: {otp}", 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"OTP email sent to {email}")
            return True, "OTP sent successfully."
            
        except Exception as e:
            logger.error(f"Failed to send OTP email: {e}")
            return False, f"Failed to send email: {str(e)}"
    
    async def send_notification(
        self,
        email: str,
        subject: str,
        message: str
    ) -> bool:
        """Send a notification email."""
        if not self._is_configured():
            logger.info(f"DEV MODE - Would send email to {email}: {subject}")
            return True
        
        try:
            msg = MIMEText(message)
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = email
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False


# Singleton instance
email_service = EmailService()
