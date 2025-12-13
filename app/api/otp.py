"""OTP authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user, create_access_token, create_refresh_token
from app.models.user import User
from app.services.email_service import email_service

router = APIRouter(prefix="/otp", tags=["otp"])


# Schemas
class OTPRequest(BaseModel):
    email: EmailStr
    purpose: str = "verification"  # verification, password_reset, 2fa


class OTPVerify(BaseModel):
    email: EmailStr
    otp: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


class OTPResponse(BaseModel):
    success: bool
    message: str


# Routes
@router.post("/request", response_model=OTPResponse)
async def request_otp(
    data: OTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Request an OTP to be sent to email."""
    # Verify user exists (for password reset and 2FA)
    if data.purpose in ["password_reset", "2fa"]:
        result = await db.execute(
            select(User).where(User.email == data.email)
        )
        user = result.scalar_one_or_none()
        if not user:
            # Don't reveal if email exists
            return OTPResponse(success=True, message="If the email exists, an OTP has been sent.")
    
    success, message = await email_service.send_otp_email(data.email, data.purpose)
    
    return OTPResponse(success=success, message=message)


@router.post("/verify", response_model=OTPResponse)
async def verify_otp(
    data: OTPVerify,
    db: AsyncSession = Depends(get_db)
):
    """Verify an OTP."""
    success, message = email_service.verify_otp(data.email, data.otp)
    
    if success:
        # Mark user as verified if this was email verification
        result = await db.execute(
            select(User).where(User.email == data.email)
        )
        user = result.scalar_one_or_none()
        if user and not user.is_verified:
            user.is_verified = True
            await db.flush()
    
    return OTPResponse(success=success, message=message)


@router.post("/password-reset/request", response_model=OTPResponse)
async def request_password_reset(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """Request password reset OTP."""
    # Always return success to not reveal if email exists
    await email_service.send_otp_email(data.email, "password_reset")
    return OTPResponse(
        success=True, 
        message="If the email exists, a password reset code has been sent."
    )


@router.post("/password-reset/confirm", response_model=OTPResponse)
async def confirm_password_reset(
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Confirm password reset with OTP and new password."""
    # Verify OTP first
    success, message = email_service.verify_otp(data.email, data.otp)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    # Find user
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    from app.core.security import get_password_hash
    user.hashed_password = get_password_hash(data.new_password)
    await db.flush()
    
    return OTPResponse(success=True, message="Password reset successfully.")


@router.post("/2fa/enable", response_model=OTPResponse)
async def enable_2fa(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Request OTP to enable 2FA."""
    success, message = await email_service.send_otp_email(current_user.email, "2fa")
    return OTPResponse(success=success, message=message)


@router.post("/2fa/confirm", response_model=OTPResponse)
async def confirm_2fa_enable(
    data: OTPVerify,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Confirm 2FA enable with OTP."""
    if data.email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email doesn't match current user"
        )
    
    success, message = email_service.verify_otp(data.email, data.otp)
    
    if success:
        current_user.totp_enabled = True
        await db.flush()
        return OTPResponse(success=True, message="2FA enabled successfully.")
    
    return OTPResponse(success=False, message=message)


@router.post("/2fa/disable", response_model=OTPResponse)
async def disable_2fa(
    data: OTPVerify,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Disable 2FA with OTP verification."""
    success, message = email_service.verify_otp(data.email, data.otp)
    
    if success:
        current_user.totp_enabled = False
        current_user.totp_secret = None
        await db.flush()
        return OTPResponse(success=True, message="2FA disabled.")
    
    return OTPResponse(success=False, message=message)
