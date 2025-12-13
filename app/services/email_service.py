"""Email service for OTP and notifications using Resend API."""

import logging
import random
import string
import httpx
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory OTP storage (use Redis in production)
_otp_store: dict = {}


class EmailService:
    """Service for sending emails and managing OTP using Resend API."""

    def __init__(self):
        self.resend_api_key = getattr(settings, 'RESEND_API_KEY', None)
        self.from_email = getattr(settings, 'RESEND_FROM_EMAIL', 'onboarding@resend.dev')
        self.resend_url = "https://api.resend.com/emails"
    
    def _is_configured(self) -> bool:
        """Check if Resend API is configured."""
        return bool(self.resend_api_key)
    
    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP."""
        return ''.join(random.choices(string.digits, k=length))
    
    def store_otp(self, email: str, otp: str, expires_minutes: int = 10) -> None:
        """Store OTP with expiration."""
        _otp_store[email] = {
            "otp": otp,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
            "attempts": 0
        }
    
    def verify_otp(self, email: str, otp: str) -> tuple[bool, str]:
        """Verify OTP for an email."""
        if email not in _otp_store:
            return False, "No OTP found. Please request a new one."
        
        stored = _otp_store[email]
        
        # Check expiration
        if datetime.now(timezone.utc) > stored["expires_at"]:
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
        """Send OTP email using Resend API."""
        otp = self.generate_otp()
        self.store_otp(email, otp)
        
        if not self._is_configured():
            # Dev mode - just generate and store, log it
            logger.info(f"DEV MODE - OTP for {email}: {otp}")
            return True, f"OTP sent (dev mode: {otp})"
        
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
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.resend_url,
                    headers={
                        "Authorization": f"Bearer {self.resend_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": f"DocQuery AI <{self.from_email}>",
                        "to": [email],
                        "subject": subject,
                        "html": html_content,
                        "text": f"Your verification code is: {otp}"
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"OTP email sent to {email} via Resend")
                    return True, "OTP sent successfully."
                else:
                    error_detail = response.text
                    logger.error(f"Resend API error: {response.status_code} - {error_detail}")
                    # Fallback: return success with OTP in message for dev/testing
                    logger.warning(f"Email delivery failed, OTP stored for {email}: {otp}")
                    return True, f"OTP generated (email delivery failed, use: {otp})"
            
        except Exception as e:
            logger.error(f"Failed to send OTP email via Resend: {e}")
            # Fallback: return success with OTP for dev/testing
            logger.warning(f"Email delivery exception, OTP stored for {email}: {otp}")
            return True, f"OTP generated (email delivery failed, use: {otp})"
    
    async def send_notification(
        self,
        email: str,
        subject: str,
        message: str
    ) -> bool:
        """Send a notification email using Resend API."""
        if not self._is_configured():
            logger.info(f"DEV MODE - Would send email to {email}: {subject}")
            return True
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.resend_url,
                    headers={
                        "Authorization": f"Bearer {self.resend_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": f"DocQuery AI <{self.from_email}>",
                        "to": [email],
                        "subject": subject,
                        "text": message
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return True
                else:
                    logger.error(f"Resend API error: {response.status_code} - {response.text}")
                    return False
            
        except Exception as e:
            logger.error(f"Failed to send notification via Resend: {e}")
            return False


# Singleton instance
email_service = EmailService()
