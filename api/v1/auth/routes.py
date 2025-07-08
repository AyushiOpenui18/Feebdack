from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Path, Body, status, Query
from sqlalchemy.orm import Session
from core.db.dependencies import get_db
from .schemas import *
from .services import *
from models.user import User
from models.otp import OTP_Tbl
from datetime import datetime, timedelta
import bcrypt
import os
import logging
from .utils import *
from typing import List
from models.developer import Developer
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from fastapi import Request
from models.feedback import Feedback
from models.feedback_developer import FeedbackDeveloper
from .schemas import DeveloperShareRequest


# Initialize routers
router = APIRouter(prefix="/auth", tags=["Auth"])
feedback_router = APIRouter(prefix="/feedback", tags=["Feedback"])
google_router = APIRouter(tags=["Google"])

logger = logging.getLogger(__name__)

# Constants
MAX_OTP_RESEND = 3
MAX_OTP_ATTEMPTS = 5
OTP_VALIDITY_MINUTES = 5
LOCK_DURATION_MINUTES = 30
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

### AUTHENTICATION ROUTES ###

@router.post("/signup/request")
def signup_request(data: SignupRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter_by(email=data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    otp = generate_otp()
    hashed_otp = bcrypt.hashpw(otp.encode(), bcrypt.gensalt())

    db.query(OTP_Tbl).filter_by(email=data.email).delete()

    db.add(OTP_Tbl(
        email=data.email,
        otp_code=hashed_otp,
        full_name=data.full_name,
        created_at=datetime.utcnow(),
        attempts=0,
        resend_count=1
    ))
    db.commit()

    send_email_otp(data.email, otp)
    return {"message": "OTP sent to your email"}

@router.post("/signup/verify")
def signup_verify(data: OTPVerifyRequest, db: Session = Depends(get_db)):
    otp_record = db.query(OTP_Tbl).filter_by(email=data.email).first()
    if not otp_record:
        raise HTTPException(status_code=400, detail="No OTP request found for this email")

    if otp_record.locked_until and otp_record.locked_until > datetime.utcnow():
        raise HTTPException(status_code=403, detail="Too many incorrect attempts. Try again later.")

    if datetime.utcnow() > otp_record.created_at + timedelta(minutes=OTP_VALIDITY_MINUTES):
        db.delete(otp_record)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired. Please request again.")

    if not bcrypt.checkpw(data.otp.encode(), otp_record.otp_code):
        otp_record.attempts += 1
        if otp_record.attempts >= MAX_OTP_ATTEMPTS:
            otp_record.locked_until = datetime.utcnow() + timedelta(minutes=LOCK_DURATION_MINUTES)
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP.")

    existing_user = db.query(User).filter_by(email=data.email).first()
    if existing_user:
        db.delete(otp_record)
        db.commit()
        access_token = create_access_token(data={"sub": str(existing_user.id)})
        return {
            "message": "User already registered",
            "access_token": access_token,
            "token_type": "bearer"
        }

    user = User(email=data.email, full_name=otp_record.full_name)
    db.add(user)
    db.delete(otp_record)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})
    return {
        "message": "Signup successful",
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/signin/request")
def signin_request(data: SigninRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email).first()

    if not user:
        collaborator = db.query(Collaborator).filter_by(user_email=data.email).first()
        if not collaborator:
            raise HTTPException(status_code=404, detail="User not found or not invited.")

        user = User(
            email=data.email,
            full_name="Invited User",
            onboarded=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        collaborator.user_id = user.id
        db.commit()

    otp_record = db.query(OTP_Tbl).filter_by(email=data.email).first()
    otp = generate_otp()
    hashed_otp = bcrypt.hashpw(otp.encode(), bcrypt.gensalt())

    if otp_record:
        if otp_record.resend_count >= MAX_OTP_RESEND:
            raise HTTPException(status_code=429, detail="OTP resend limit reached.")
        otp_record.otp_code = hashed_otp
        otp_record.resend_count += 1
        otp_record.created_at = datetime.utcnow()
    else:
        otp_record = OTP_Tbl(
            email=data.email,
            otp_code=hashed_otp,
            created_at=datetime.utcnow(),
            resend_count=1,
            attempts=0
        )
        db.add(otp_record)

    db.commit()
    send_email_otp(data.email, otp)

    return {"message": "OTP sent to your email"}

@router.post("/signin/verify")
def signin_verify(data: OTPVerifyRequest, db: Session = Depends(get_db)):
    record = db.query(OTP_Tbl).filter_by(email=data.email).first()
    if not record:
        raise HTTPException(status_code=400, detail="No OTP request found for this email")

    if record.locked_until and record.locked_until > datetime.utcnow():
        raise HTTPException(status_code=403, detail="Too many incorrect attempts. Try again later.")

    if datetime.utcnow() > record.created_at + timedelta(minutes=OTP_VALIDITY_MINUTES):
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired")

    if not bcrypt.checkpw(data.otp.encode(), record.otp_code):
        record.attempts += 1
        if record.attempts >= MAX_OTP_ATTEMPTS:
            record.locked_until = datetime.utcnow() + timedelta(minutes=LOCK_DURATION_MINUTES)
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    user = db.query(User).filter_by(email=data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User does not exist")

    db.delete(record)
    db.commit()

    access_token = create_access_token(data={"sub": str(user.id)})

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer"
    }

### WORKSPACE ROUTES ###

@router.post("/onboarding")
def onboard_user(
    data: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user)
):
    user = db.query(User).filter_by(id=current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.onboarded:
        raise HTTPException(status_code=400, detail="User already onboarded")

    # ✅ Create the workspace
    workspace, subdomain = create_workspace(data, user, db)

    # ✅ Mark user as onboarded
    user.onboarded = True
    db.commit()

    return {
        "message": "User onboarded and workspace created successfully",
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "subdomain": subdomain
        }
    }

@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    # ✅ Extract subdomain from request.state (set by middleware)
    subdomain = request.state.subdomain
    if not subdomain:
        raise HTTPException(status_code=400, detail="Subdomain not found in request")

    full_subdomain = f"{subdomain}.feedback.com"

    # ✅ Lookup workspace by subdomain
    workspace = db.query(Workspace).filter_by(subdomain=full_subdomain).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return {
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "subdomain": subdomain
        }
    }


### GOOGLE AUTH ROUTES ###

class TokenVerifyRequest(BaseModel):
    id_token: str

@google_router.post("/auth/google/verify_token")
def verify_google_id_token(
    payload: TokenVerifyRequest, 
    db: Session = Depends(get_db)
):
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.id_token,
            grequests.Request(),
            GOOGLE_CLIENT_ID
        )

        email = idinfo.get("email")
        full_name = idinfo.get("name") or email.split("@")[0]
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in token")

        user = db.query(User).filter_by(email=email).first()
        if not user:
            new_user = User(email=email, full_name=full_name, onboarded=False)
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            return {"redirect_to": "/auth/onboarding"}

        if not user.onboarded:
            return {"redirect_to": "/auth/onboarding"}

        workspace = db.query(Workspace).filter_by(owner_id=user.id).first()
        if workspace:
            return {"redirect_to": f"https://{workspace.subdomain}"}
        return {"redirect_to": "/dashboard"}

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid ID token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token verification failed: {str(e)}")

### FEEDBACK ROUTES ###
@feedback_router.post("/create", response_model=FeedbackOut)
def create_feedback_route(
    data: FeedbackCreate, 
    db: Session = Depends(get_db), 
    current_user: int = Depends(get_current_user)  # 👈 expecting int
):
    # Verify workspace access
    workspace = db.query(Workspace).filter_by(id=data.workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    if workspace.owner_id != current_user:
        collaborator = db.query(Collaborator).filter_by(
            workspace_id=data.workspace_id,
            user_id=current_user
        ).first()
        if not collaborator:
            raise HTTPException(status_code=403, detail="No access to workspace")
    return create_feedback(db, data, current_user, data.workspace_id)


@feedback_router.put("/update/{feedback_id}", response_model=FeedbackOut)
def update_feedback_route(
    feedback_id: int,
    data: FeedbackUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    # Verify workspace access
    if feedback.created_by != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to update this feedback")

    return update_feedback(feedback_id, data, db, current_user)

@feedback_router.delete("/{feedback_id}")
def delete_feedback_route(
    feedback_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if feedback.created_by != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to delete this feedback")

    return delete_feedback(db, feedback_id, current_user)


@feedback_router.post("/upload", status_code=status.HTTP_200_OK)
def upload_file(
    feedback_id: int = Form(...), 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if feedback.created_by != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to upload files for this feedback")

    return upload_feedback_file(db, feedback_id, file, current_user)

@feedback_router.post("/upload/voice", status_code=status.HTTP_200_OK)
def upload_voice_recording(
    feedback_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: int = Depends(get_current_user)  # Assuming it's an int (user_id)
):
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if feedback.created_by != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to upload files for this feedback")

    return upload_voice_file(db, feedback_id, file, current_user)


from sqlalchemy import func
from fastapi import Query
from typing import List

@feedback_router.get("/search", response_model=List[FeedbackOut])
def search_feedbacks(
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db)
):
    search_term = f"%{query.lower()}%"

    feedbacks = (
        db.query(Feedback)
        .filter(func.lower(Feedback.name).like(search_term))  # ✅ works for all DBs
        .all()
    )

    return feedbacks


# ✅ SHARE FEEDBACK WITH DEVELOPERS BY EMAIL
@feedback_router.post("/share/{feedback_id}")
def share_feedback(
    feedback_id: int,
    request: DeveloperShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if feedback.created_by != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to share this feedback")

    return share_feedback_with_developers(db, feedback_id, request.developer_emails, current_user)


# ✅ DEVELOPER TAKES ACTION ON FEEDBACK
@feedback_router.post("/developer_action/{feedback_id}")
def developer_action(
    feedback_id: int,
    action: str = Body(..., embed=True),
    developer_email: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    return handle_developer_action(db, feedback_id, developer_email, action)


# ✅ GET STATUS OF DEVELOPERS FOR A FEEDBACK

from datetime import datetime

@feedback_router.get("/developer_status/{feedback_id}")
def get_feedback_developer_status(feedback_id: int, db: Session = Depends(get_db)):
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return {
        "feedback_name": feedback.name,
        "developer_statuses": [
            {
                "email": link.developer.email,
                "status": link.status.value,
                "action_time": link.action_time.strftime("%d-%m-%Y %I:%M %p") if link.action_time else None
            } for link in feedback.feedback_developer_links
        ]
    }


# ✅ GET ALL FEEDBACKS ASSIGNED TO A DEVELOPER (AFTER ONBOARDING)
@feedback_router.get("/developer/feedbacks", response_model=List[FeedbackOut])
def get_assigned_feedbacks(
    db: Session = Depends(get_db),
    current_developer: Developer = Depends(get_current_developer),
):
    feedback_links = db.query(FeedbackDeveloper).filter_by(developer_id=current_developer.id).all()
    return [link.feedback for link in feedback_links if link.feedback is not None]

    return assigned_feedbacks

@feedback_router.get("/all", response_model=List[FeedbackOut])
def list_all_feedbacks_by_workspace(
    workspace_id: int = Query(..., description="ID of the workspace"),
    db: Session = Depends(get_db)
):
    # Optional: verify workspace exists
    if not db.query(Workspace).filter_by(id=workspace_id).first():
        raise HTTPException(status_code=404, detail="Workspace not found")
    return get_all_feedbacks_by_workspace(db, workspace_id)


@feedback_router.get("/drafts", response_model=List[FeedbackOut])
def list_workspace_draft_feedbacks(
    workspace_id: int = Query(..., description="ID of the workspace"),
    db: Session = Depends(get_db)
):
    if not db.query(Workspace).filter_by(id=workspace_id).first():
        raise HTTPException(status_code=404, detail="Workspace not found")
    return get_draft_feedbacks_by_workspace(db, workspace_id)

### SETTINGS ROUTES ###

@feedback_router.put("/user/update", response_model=UserOut)
def update_user(
    data: UserProfileUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    return update_user_profile(db, current_user, data)

@feedback_router.post("/user/reset_profile", response_model=UserOut)
def reset_profile(db: Session = Depends(get_db), user_id: int = Depends(get_current_user)):
    return reset_user_profile(db, user_id)

from fastapi import UploadFile, File, Form, HTTPException
import os
from uuid import uuid4

@feedback_router.post("/upload_profile_image")
def upload_profile_image(
    user_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Validate user
    user = db.query(User).filter_by(id=user_id).first()  # or Developer if that’s the model
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Save file to local/media directory
    extension = file.filename.split('.')[-1]
    filename = f"{uuid4().hex}.{extension}"
    save_path = os.path.join("uploads/profile_images", filename)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(file.file.read())

    # Save image path to DB
    user.profile_image = save_path
    db.commit()

    return {"message": "Profile image uploaded", "image_path": save_path}


@feedback_router.get("/members/{workspace_id}")
def list_workspace_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user)  # int returned from your token logic
):
    try:
        members = get_workspace_members(db, workspace_id, current_user_id)
        return {"members": members}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@feedback_router.get("/billing")
def billing_info():
    return get_billing_info()


@feedback_router.post("/invite_collaborator/{workspace_id}")
def invite_collaborator_api(
    workspace_id: int,
    data: CollaboratorInvite,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user)
):
    return invite_collaborator(
        db=db,
        workspace_id=workspace_id,
        email=data.email,
        access_type=data.access_type,
        invited_by_id=current_user_id
    )


