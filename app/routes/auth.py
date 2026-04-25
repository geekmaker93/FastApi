import logging
import random
import re
import secrets
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.dependencies import get_current_user, get_db
from app.models.db_models import User, UserPreferences
from app.services.email_service import (
    send_delete_confirmation_email,
    send_password_reset_email,
    send_verification_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: Optional[str] = Field(default=None, max_length=100)
    wants_updates: bool = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


def _validate_password(password: str) -> None:
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number")
    if not re.search(r"[!@#$%^&*()_\-+=\[\]{};':\"\\|,.<>/?`~]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one special character")


def _send_email_bg(email: str, code: str) -> None:
    try:
        send_verification_email(email, code)
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", email, exc)


@router.post("/signup")
def signup(body: SignupRequest, background_tasks: BackgroundTasks, db: Annotated[Session, Depends(get_db)]):
    _validate_password(body.password)
    email = body.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    code = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    new_user = User(
        name=(body.name or email.split("@")[0]).strip(),
        email=email,
        password=hash_password(body.password),
        is_verified=False,
        verification_code=code,
        code_expires_at=expires_at,
    )
    db.add(new_user)
    db.flush()

    preference = UserPreferences(
        user_id=new_user.id,
        wants_updates=body.wants_updates,
    )
    db.add(preference)
    db.commit()
    db.refresh(new_user)

    background_tasks.add_task(_send_email_bg, email, code)

    return {
        "message": "Verification code sent to your email. It expires in 10 minutes.",
        "user_id": new_user.id,
        "email": new_user.email,
        "is_verified": False,
        "wants_updates": body.wants_updates,
    }


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class ResendCodeRequest(BaseModel):
    email: EmailStr


@router.post("/verify-code")
def verify_code(body: VerifyCodeRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or code")
    if user.is_verified:
        return {"message": "Account already verified"}
    if user.verification_code != body.code:
        raise HTTPException(status_code=400, detail="Invalid code")
    if datetime.utcnow() > user.code_expires_at:
        raise HTTPException(status_code=400, detail="Code expired. Request a new one.")
    user.is_verified = True
    user.verification_code = None
    user.code_expires_at = None
    db.commit()
    return {"message": "Account verified. You can now log in."}


@router.post("/resend-code")
def resend_code(body: ResendCodeRequest, background_tasks: BackgroundTasks, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user:
        raise HTTPException(status_code=400, detail="No account found with that email")
    if user.is_verified:
        return {"message": "Account already verified"}
    code = str(random.randint(100000, 999999))
    user.verification_code = code
    user.code_expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    background_tasks.add_task(_send_email_bg, body.email.strip().lower(), code)
    return {"message": "New verification code sent to your email."}


@router.post("/login")
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
):
    email = form_data.username.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your account first.",
        )
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login/json")
def login_json(body: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your account first.",
        )
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    preferences = (
        db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()
    )
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "is_verified": current_user.is_verified,
        "wants_updates": preferences.wants_updates if preferences else True,
    }


@router.delete("/delete-account")
def delete_account(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    from app.models.db_models import Farm, NDVISnapshot, YieldResult, FarmerYieldReport, SoilProfile

    farm_ids = [f.id for f in db.query(Farm).filter(Farm.user_id == current_user.id).all()]

    if farm_ids:
        yield_ids = [
            y.id for y in db.query(YieldResult).filter(YieldResult.farm_id.in_(farm_ids)).all()
        ]
        if yield_ids:
            db.query(FarmerYieldReport).filter(
                FarmerYieldReport.yield_result_id.in_(yield_ids)
            ).delete(synchronize_session=False)
        db.query(YieldResult).filter(
            YieldResult.farm_id.in_(farm_ids)
        ).delete(synchronize_session=False)
        db.query(NDVISnapshot).filter(
            NDVISnapshot.farm_id.in_(farm_ids)
        ).delete(synchronize_session=False)
        db.query(SoilProfile).filter(
            SoilProfile.farm_id.in_(farm_ids)
        ).delete(synchronize_session=False)
        db.query(Farm).filter(
            Farm.user_id == current_user.id
        ).delete(synchronize_session=False)

    db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).delete(synchronize_session=False)
    db.delete(current_user)
    db.commit()
    return {"message": "Account deleted successfully"}


@router.post("/request-delete")
def request_delete(
    current_user: Annotated[User, Depends(get_current_user)],
):
    import os
    from urllib.parse import quote
    token = create_access_token(
        {"sub": str(current_user.id), "email": current_user.email, "purpose": "delete_account"},
        expires_delta=timedelta(minutes=30),
    )
    confirm_link = f"farmsense://confirm-delete?token={quote(token)}"
    try:
        send_delete_confirmation_email(current_user.email, confirm_link)
    except Exception as exc:
        logger.error("Failed to send delete confirmation email to %s: %s", current_user.email, exc)
        raise HTTPException(status_code=500, detail="Failed to send confirmation email. Try again.")
    return {"message": "Confirmation email sent. Check your inbox to complete deletion."}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/forgot-password")
def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    # Always return the same response to avoid email enumeration
    if user and user.is_verified:
        code = str(random.randint(100000, 999999))
        user.reset_token = code
        user.reset_token_expires = datetime.utcnow() + timedelta(minutes=15)
        db.commit()
        background_tasks.add_task(send_password_reset_email, user.email, code)
    return {"message": "If that email is registered, a reset code has been sent."}


@router.get("/reset-password-form")
def reset_password_form(token: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        <title>Reset Password - CropMonitor</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: linear-gradient(135deg,#667eea,#764ba2);
                   min-height:100vh; display:flex; align-items:center; justify-content:center; margin:0; }}
            .card {{ background:#fff; border-radius:12px; padding:32px; width:100%; max-width:400px;
                     box-shadow:0 10px 24px rgba(0,0,0,0.2); }}
            h2 {{ color:#667eea; margin:0 0 8px; }}
            p {{ color:#6b7280; font-size:14px; margin:0 0 24px; }}
            label {{ display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px; }}
            input {{ width:100%; padding:10px 12px; border:1px solid #d1d5db; border-radius:6px;
                     font-size:15px; box-sizing:border-box; margin-bottom:16px; }}
            button {{ width:100%; padding:12px; background:#667eea; color:#fff; border:none;
                      border-radius:6px; font-size:16px; font-weight:bold; cursor:pointer; }}
            button:hover {{ background:#5a6fd6; }}
            #msg {{ margin-top:16px; font-size:14px; text-align:center; }}
            .error {{ color:#dc2626; }} .success {{ color:#16a34a; }}
        </style>
    </head>
    <body>
    <div class="card">
        <h2>Reset your password</h2>
        <p>Enter a new password for your CropMonitor account.</p>
        <label>New Password</label>
        <input type="password" id="pw" placeholder="Min 8 chars, 1 number, 1 special"/>
        <label>Confirm Password</label>
        <input type="password" id="pw2" placeholder="Repeat password"/>
        <button onclick="submit()">Set New Password</button>
        <div id="msg"></div>
    </div>
    <script>
        async function submit() {{
            const pw = document.getElementById('pw').value;
            const pw2 = document.getElementById('pw2').value;
            const msg = document.getElementById('msg');
            if (pw !== pw2) {{ msg.className='error'; msg.textContent='Passwords do not match.'; return; }}
            if (pw.length < 8) {{ msg.className='error'; msg.textContent='Password must be at least 8 characters.'; return; }}
            const resp = await fetch('/auth/reset-password', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{token: '{token}', new_password: pw}})
            }});
            const data = await resp.json();
            if (resp.ok) {{
                msg.className='success';
                msg.textContent = data.message + ' You can close this page.';
                document.querySelector('button').disabled = true;
            }} else {{
                msg.className='error';
                msg.textContent = data.detail || 'Something went wrong.';
            }}
        }}
    </script>
    </body>
    </html>
    """)


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Annotated[Session, Depends(get_db)]):
    _validate_password(body.new_password)
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or user.reset_token is None:
        raise HTTPException(status_code=400, detail="Invalid code.")
    if user.reset_token != body.code:
        raise HTTPException(status_code=400, detail="Invalid code.")
    if datetime.utcnow() > user.reset_token_expires:
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")
    user.password = hash_password(body.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return {"message": "Password updated successfully. You can now log in."}


class ConfirmDeleteRequest(BaseModel):
    token: str


@router.post("/confirm-delete")
def confirm_delete(body: ConfirmDeleteRequest, db: Annotated[Session, Depends(get_db)]):
    from app.models.db_models import Farm, NDVISnapshot, YieldResult, FarmerYieldReport, SoilProfile
    try:
        payload = decode_access_token(body.token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation link.")
    if payload.get("purpose") != "delete_account":
        raise HTTPException(status_code=400, detail="Invalid token purpose.")
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found or already deleted.")

    farm_ids = [f.id for f in db.query(Farm).filter(Farm.user_id == user.id).all()]
    if farm_ids:
        yield_ids = [
            y.id for y in db.query(YieldResult).filter(YieldResult.farm_id.in_(farm_ids)).all()
        ]
        if yield_ids:
            db.query(FarmerYieldReport).filter(
                FarmerYieldReport.yield_result_id.in_(yield_ids)
            ).delete(synchronize_session=False)
        db.query(YieldResult).filter(YieldResult.farm_id.in_(farm_ids)).delete(synchronize_session=False)
        db.query(NDVISnapshot).filter(NDVISnapshot.farm_id.in_(farm_ids)).delete(synchronize_session=False)
        db.query(SoilProfile).filter(SoilProfile.farm_id.in_(farm_ids)).delete(synchronize_session=False)
        db.query(Farm).filter(Farm.user_id == user.id).delete(synchronize_session=False)

    db.query(UserPreferences).filter(UserPreferences.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    return {"message": "Account permanently deleted."}
