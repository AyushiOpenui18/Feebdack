import os, smtplib
from email.message import EmailMessage
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from datetime import datetime, timedelta
from core.db.dependencies import get_db
from sqlalchemy.orm import Session
from models.user import User


def send_email_otp(to_email: str, otp: str):
    try:
        _send_email(
            to_email,
            subject="Your OTP Code",
            body=f"Your OTP is: {otp}"
        )
        print(f"[INFO] OTP sent to {to_email}")
    except Exception as e:
        print(f"[ERROR] Failed to send email to {to_email}: {e}")
        raise


def send_invite_email(to_email: str, workspace_name: str, inviter: str, dashboard_url: str):
    _send_email(
        to_email,
        subject="You're Invited to Join a Workspace",
        body=(
            f"Hi,\n\n{inviter} has invited you to join the workspace '{workspace_name}'."
            f"\nClick here to join the dashboard: {dashboard_url}"
        )
    )


def _send_email(to_email: str, subject: str, body: str):
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port_str = os.getenv("SMTP_PORT")

    # Check before converting
    if not all([smtp_email, smtp_password, smtp_server, smtp_port_str]):
        raise RuntimeError("Missing SMTP environment variables")

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        raise RuntimeError("SMTP_PORT must be an integer")

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = smtp_email
    msg["To"] = to_email

    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(smtp_email, smtp_password)
        smtp.send_message(msg)

SECRET_KEY = "ayushisahu112203"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 360

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/signin/verify")


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)



def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter_by(id=int(user_id)).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user.id
    except JWTError:
        raise HTTPException(status_code=401, detail="Token error")
    

from datetime import timedelta

def send_feedback_email(to_email: str, feedback_id: int, feedback_name: str) -> str:
    import urllib.parse
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8000")

    # ✅ Create token for developer
    access_token = create_access_token(
        data={"sub": to_email},  # or use developer_id if preferred
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # ✅ Include token in feedback link
    encoded_email = urllib.parse.quote(to_email)
    feedback_url = f"{frontend_url}/view-feedback/{feedback_id}?token={access_token}&developer={encoded_email}"

    msg = EmailMessage()
    msg.set_content(f"You've received new feedback: {feedback_name}\n\nView it here:\n{feedback_url}")
    msg["Subject"] = f"📢 Feedback: {feedback_name}"
    msg["From"] = smtp_email
    msg["To"] = to_email

    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(smtp_email, smtp_password)
        smtp.send_message(msg)

    return feedback_url

from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from models import Developer

def get_current_developer(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token or developer not found",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")

        print("Decoded token sub:", sub)

        if not sub:
            raise credentials_exception

        # Try to cast to int (means it's likely an ID)
        try:
            dev_id = int(sub)
            developer = db.query(Developer).filter_by(id=dev_id).first()
        except ValueError:
            # Otherwise, treat it as an email
            developer = db.query(Developer).filter_by(email=sub).first()

        if not developer:
            print("Developer not found with sub:", sub)
            raise credentials_exception

        print("✅ Developer authenticated:", developer.email)
        return developer

    except JWTError as e:
        print("JWT decoding error:", e)
        raise credentials_exception


def resolve_logged_in_user_as_developer(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Uses the logged-in user token to resolve their email and match with Developer table.
    Returns the developer object if match found.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token or sub")

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    developer = db.query(Developer).filter_by(email=user.email).first()
    if not developer:
        raise HTTPException(status_code=403, detail="You are not a developer with shared feedback")

    return developer



