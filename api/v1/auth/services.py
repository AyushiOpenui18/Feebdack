import os
import uuid
import shutil
import random
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Tuple

from models.user import User
from models.otp import OTP_Tbl
from models.workspace import Workspace
from models.feedback import Feedback, FeedbackStatus
from models.feedback_access import FeedbackAccess, AccessLevel
from models.developer import Developer
from models.collaborators import Collaborator
from models.feedback_developer import FeedbackDeveloper, FeedbackDeveloperStatus

from .schemas import (
    FeedbackCreate,
    FeedbackUpdate,
    WorkspaceCreate,
    UserProfileUpdate
)

from .utils import send_email_otp, send_invite_email, send_feedback_email

logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_EXTENSIONS = ["png", "jpg", "jpeg"]
ALLOWED_VIDEO_EXTENSIONS = ["webm", "mp4"]
ALLOWED_AUDIO_EXTENSIONS = ["mp3", "wav", "ogg"]

### AUTHENTICATION SERVICES ###

def generate_otp() -> str:
    """Generate a 6-digit OTP code"""
    return str(random.randint(100000, 999999))

def request_signup_otp(email: str, full_name: str, db: Session) -> None:
    """Request OTP for user signup"""
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists"
        )

    record = db.query(OTP_Tbl).filter_by(email=email).first()
    if record:
        if record.resend_count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum OTP resend limit reached"
            )
        record.otp_code = generate_otp()
        record.created_at = datetime.utcnow()
        record.full_name = full_name
        record.resend_count += 1
    else:
        record = OTP_Tbl(
            email=email,
            otp_code=generate_otp(),
            full_name=full_name,
            created_at=datetime.utcnow(),
            attempts=0,
            resend_count=1
        )
        db.add(record)

    db.commit()
    send_email_otp(email, record.otp_code)

def verify_signup_otp(email: str, otp: str, db: Session) -> User:
    """Verify OTP for user signup"""
    record = db.query(OTP_Tbl).filter_by(email=email).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found. Please request a new one."
        )
    
    if record.locked_until and datetime.utcnow() < record.locked_until:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Too many failed attempts. Try again later."
        )
    
    if datetime.utcnow() > record.created_at + timedelta(minutes=5):
        db.delete(record)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired. Please request a new one."
        )
    
    if record.otp_code != otp:
        record.attempts += 1
        if record.attempts >= 5:
            record.locked_until = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP"
        )

    user = User(email=email, full_name=record.full_name, onboarded=False)
    db.add(user)
    db.delete(record)
    db.commit()
    return user


def request_signin_otp(email: str, db: Session) -> None:
    """Request OTP for user signin"""
    user = db.query(User).filter_by(email=email).first()

    if not user:
        # Check if invited collaborator
        collaborator = db.query(Collaborator).filter_by(user_email=email).first()
        if not collaborator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found or not invited"
            )

        # Create minimal user
        user = User(
            email=email,
            full_name="Invited User",
            onboarded=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Link collaborator
        collaborator.user_id = user.id
        db.commit()

    # Generate/update OTP
    otp_record = db.query(OTP_Tbl).filter_by(email=email).first()
    otp = generate_otp()

    if otp_record:
        if otp_record.resend_count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum OTP resend limit reached"
            )
        otp_record.otp_code = otp
        otp_record.created_at = datetime.utcnow()
        otp_record.resend_count += 1
    else:
        otp_record = OTP_Tbl(
            email=email,
            otp_code=otp,
            created_at=datetime.utcnow(),
            resend_count=1,
            attempts=0
        )
        db.add(otp_record)

    db.commit()
    send_email_otp(email, otp)

def verify_signin_otp(email: str, otp: str, db: Session) -> User:
    """Verify OTP for user signin"""
    record = db.query(OTP_Tbl).filter_by(email=email).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found. Please request a new one."
        )
    
    if record.locked_until and datetime.utcnow() < record.locked_until:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Too many failed attempts. Try again later."
        )
    
    if datetime.utcnow() > record.created_at + timedelta(minutes=5):
        db.delete(record)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired. Please request a new one."
        )
    
    if record.otp_code != otp:
        record.attempts += 1
        if record.attempts >= 5:
            record.locked_until = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP"
        )

    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not exist"
        )

    db.delete(record)
    db.commit()
    return user

### WORKSPACE SERVICES ###

def generate_subdomain(name: str, db: Session) -> str:
    """Generate a unique subdomain for a workspace"""
    base = name.lower().replace(" ", "")
    subdomain = f"{base}.feedback.com"
    counter = 1
    
    while db.query(Workspace).filter_by(subdomain=subdomain).first():
        subdomain = f"{base}{counter}.feedback.com"
        counter += 1
    
    return subdomain


### WORKSPACE SERVICES ###

import string

# List of friendly suffixes to suggest meaningful names
FRIENDLY_SUFFIXES = [
    "hub", "space", "team", "studio", "hq", "zone", "lab", "base", "deck", "works"
]

def suggest_alternate_names(name: str, db: Session, count: int = 5) -> List[str]:
    """Suggest multiple readable workspace name alternatives."""
    suggestions = []
    used_suffixes = set()

    # Try suffix-based suggestions
    for suffix in FRIENDLY_SUFFIXES:
        alt_name = f"{name}_{suffix}"
        if alt_name not in used_suffixes and not db.query(Workspace).filter_by(name=alt_name).first():
            suggestions.append(alt_name)
            used_suffixes.add(suffix)
        if len(suggestions) >= count:
            break

    # If not enough suggestions, fallback to random ones
    while len(suggestions) < count:
        rand_suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
        alt_name = f"{name}_{rand_suffix}"
        if alt_name not in suggestions and not db.query(Workspace).filter_by(name=alt_name).first():
            suggestions.append(alt_name)

    return suggestions

def create_workspace(
    data: WorkspaceCreate,
    user: User,
    db: Session
) -> Tuple[Workspace, str]:
    """Create a new workspace with the given details."""
    existing = db.query(Workspace).filter_by(name=data.workspace_name).first()
    if existing:
        suggestions = suggest_alternate_names(data.workspace_name, db)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Workspace name '{data.workspace_name}' already exists.",
                "suggestions": suggestions
            }
        )

    subdomain = generate_subdomain(data.workspace_name, db)
    workspace = Workspace(
        name=data.workspace_name,
        subdomain=subdomain,
        type=data.type,
        purpose=data.purpose,
        role=data.role,
        icon_url=data.icon_url,
        owner_id=user.id,
        invite_emails=",".join(data.collaborators) if data.collaborators else None
    )

    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    # Add collaborators
    for email in data.collaborators or []:
        existing_user = db.query(User).filter_by(email=email).first()
        collaborator = Collaborator(
            user_email=email,
            user_id=existing_user.id if existing_user else None,
            access_type="comment",
            workspace_id=workspace.id,
            invited_by_id=user.id
        )
        db.add(collaborator)
        send_invite_email(email, data.workspace_name, user.full_name, subdomain)

    db.commit()
    return workspace, subdomain


### FEEDBACK SERVICES ###
def get_all_feedbacks_by_workspace(
    db: Session,
    workspace_id: int,
    user_id: int = None  # 👈 Made optional
) -> List[Feedback]:

    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )

    feedbacks = db.query(Feedback).filter_by(workspace_id=workspace_id).all()

    if user_id is not None:
        if workspace.owner_id != user_id:
            collaborator = db.query(Collaborator).filter_by(
                workspace_id=workspace_id,
                user_id=user_id
            ).first()
            if not collaborator:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No access to workspace"
                )

            # Filter to only accessible feedbacks
            accessible_feedback_ids = [
                access.feedback_id
                for access in db.query(FeedbackAccess).filter_by(user_id=user_id).all()
            ]
            feedbacks = [f for f in feedbacks if f.id in accessible_feedback_ids]

    return feedbacks

def get_draft_feedbacks_by_workspace(
    db: Session,
    workspace_id: int,
    user_id: int = None  # 👈 Made optional
) -> List[Feedback]:

    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )

    feedbacks = db.query(Feedback).filter(
        Feedback.workspace_id == workspace_id,
        Feedback.status == FeedbackStatus.draft
    ).all()

    if user_id is not None:
        if workspace.owner_id != user_id:
            collaborator = db.query(Collaborator).filter_by(
                workspace_id=workspace_id,
                user_id=user_id
            ).first()
            if not collaborator:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No access to workspace"
                )

            # Show only drafts created by collaborator
            feedbacks = [f for f in feedbacks if f.created_by == user_id]

    return feedbacks


def create_feedback(
    db: Session,
    data: FeedbackCreate,
    user_id: int,
    workspace_id: int
) -> Feedback:
    """Create new feedback in the specified workspace"""

    # Validate workspace
    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )

    # Check permission (owner or collaborator)
    if workspace.owner_id != user_id:
        collaborator = db.query(Collaborator).filter_by(
            workspace_id=workspace_id,
            user_id=user_id
        ).first()
        if not collaborator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to workspace"
            )

    # Create Feedback
    feedback = Feedback(
        name=data.name.strip(),
        created_by=user_id,
        workspace_id=workspace_id,
        url=data.url,
        message=data.message,
        status=FeedbackStatus.draft,
        screenshot_url=data.screenshot_url,
        recording_url=data.recording_url
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    # Add collaborators to Collaborator + FeedbackAccess
    for collab in data.collaborators or []:
        # 1. Ensure they are added to Collaborator table
        existing_collab = db.query(Collaborator).filter_by(
            user_email=collab.email,
            workspace_id=workspace_id
        ).first()

        if not existing_collab:
            new_collaborator = Collaborator(
                user_email=collab.email,
                access_type=collab.access,
                workspace_id=workspace_id,
                invited_by_id=user_id
            )
            db.add(new_collaborator)

        # 2. Add access to FeedbackAccess table
        feedback_access = FeedbackAccess(
            feedback_id=feedback.id,
            user_email=collab.email,
            access_type=collab.access,
            user_id=collab.user_id
        )
        db.add(feedback_access)

    db.commit()
    return feedback


### FILE UPLOAD SERVICES ###

def upload_feedback_file(
    db: Session,
    feedback_id: int,
    file: UploadFile,
    user_id: int
) -> Dict[str, str]:
    """Upload and attach a file to feedback"""
    try:
        # Validate file extension
        ext = file.filename.split(".")[-1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS + ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: .{ext}"
            )

        # Verify feedback access
        feedback = db.query(Feedback).filter_by(id=feedback_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found"
            )
        
        if feedback.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission to upload files for this feedback"
            )

        # Save file
        os.makedirs("media/feedback", exist_ok=True)
        file_path = f"media/feedback/{uuid.uuid4()}.{ext}"
        
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Update feedback
        if ext in ALLOWED_IMAGE_EXTENSIONS:
            feedback.screenshot_url = f"/{file_path}"
        else:
            feedback.recording_url = f"/{file_path}"
        
        db.commit()
        return {
            "status": "uploaded",
            "file_url": f"/{file_path}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed"
        )


def update_feedback(
    feedback_id: int,
    data: FeedbackUpdate,
    db: Session,
    user_id: int
) -> Feedback:
    """Update existing feedback"""
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found"
        )

    # Verify user has access to this feedback's workspace
    workspace = db.query(Workspace).filter_by(id=feedback.workspace_id).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )
    
    if workspace.owner_id != user_id:
        collaborator = db.query(Collaborator).filter_by(
            workspace_id=feedback.workspace_id,
            user_id=user_id
        ).first()
        if not collaborator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to feedback"
            )

    # Prevent updating sent feedback
    if feedback.status == FeedbackStatus.sent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update sent feedback"
        )

    try:
        for attr, value in data.dict(exclude_unset=True).items():
            setattr(feedback, attr, value)
        db.commit()
        db.refresh(feedback)
        return feedback
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating feedback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update feedback"
        )
    

def delete_feedback(
    db: Session,
    feedback_id: int,
    user_id: int
) -> Dict[str, str]:
    """Delete feedback if user has permission"""
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found"
        )

    # Verify ownership
    if feedback.created_by != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only creator can delete feedback"
        )

    if feedback.status == FeedbackStatus.sent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete sent feedback"
        )

    db.delete(feedback)
    db.commit()
    return {"message": "Feedback deleted successfully"}

### FILE UPLOAD SERVICES ###

def upload_voice_file(
    db: Session,
    feedback_id: int,
    file: UploadFile,
    user_id: int
) -> Dict[str, str]:
    """Upload and attach a voice recording to feedback"""
    try:
        # Validate file extension
        ext = file.filename.split(".")[-1].lower()
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported audio format: .{ext}"
            )

        # Verify feedback access
        feedback = db.query(Feedback).filter_by(id=feedback_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found"
            )
        
        if feedback.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission to upload files for this feedback"
            )

        # Validate file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset pointer
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds 10MB limit"
            )

        # Save file
        os.makedirs("media/feedback/voice", exist_ok=True)
        file_path = f"media/feedback/voice/{uuid.uuid4()}.{ext}"
        
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Update feedback
        feedback.voice_recording_url = f"/{file_path}"
        db.commit()
        return {
            "status": "uploaded",
            "voice_url": f"/{file_path}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice upload failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Voice upload failed"
        )

### USER PROFILE SERVICES ###

def update_user_profile(
    db: Session,
    user_id: int,
    data: UserProfileUpdate
) -> User:
    """Update user profile information"""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if data.full_name:
        user.full_name = data.full_name
    if data.profile_url:
        user.profile_url = data.profile_url
    
    db.commit()
    db.refresh(user)
    return user

def reset_user_profile(db: Session, user_id: int):
    user = db.query(User).filter_by(id=user_id).first()
    user.profile_url = None
    db.commit()
    db.refresh(user)
    return user


#Access and members
def get_workspace_members(db: Session, workspace_id: int, user_id: int):
    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if not workspace:
        raise Exception("Workspace not found")

    if workspace.owner_id != user_id:
        raise Exception("Only the workspace owner can view members")

    members = []

    # 1. Admin (Owner)
    owner = db.query(User).filter_by(id=workspace.owner_id).first()
    if owner:
        members.append({
            "name": owner.full_name,
            "access_type": "admin",
            "status": "active"
        })

        # 2. Collaborators
    collaborators = (
       db.query(Collaborator)
       .filter_by(workspace_id=workspace_id)
       .all()
    ) 

    for collab in collaborators:
    # Get user by email to check if they've registered and onboarded
       user = db.query(User).filter_by(email=collab.user_email).first()

       members.append({
         "name": user.full_name if user else collab.user_email,
         "access_type": "collaborator",
         "status": "active" if user and user.onboarded else "inactive"
       })


    
    # 3. Developers invited by this workspace
    developers = (
        db.query(Developer)
        .filter_by(invited_by_workspace_id=workspace_id)
        .all()
    )
    for dev in developers:
        user = db.query(User).filter_by(email=dev.email).first()
        members.append({
            "name": user.full_name if user else dev.email,
            "access_type": "developer",
            "status": "active" if user and user.onboarded else "inactive"
        })

    return members


### DEVELOPER SERVICES ###
def share_feedback_with_developers(
    db: Session,
    feedback_id: int,
    emails: List[str],
    user_id: int
) -> Dict[str, Any]:
    """Share feedback with developers via email"""
    feedback = db.query(Feedback).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found"
        )

    if feedback.created_by != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only creator can share feedback"
        )

    # Mark feedback as sent
    feedback.status = FeedbackStatus.sent
    db.commit()

    developer_urls = []

    for idx, email in enumerate(emails):
        developer = db.query(Developer).filter_by(email=email).first()

        # ✅ Create developer if not exists
        if not developer:
            developer = Developer(
                email=email,
                invited_by_workspace_id=feedback.workspace_id  # Save who invited
            )
            db.add(developer)
            db.commit()
            db.refresh(developer)

        # ✅ If already exists but invited_by_workspace_id is empty, update it
        elif developer.invited_by_workspace_id is None:
            developer.invited_by_workspace_id = feedback.workspace_id
            db.commit()

        # ✅ Save developer email in feedback (only the first one or if not already set)
        if idx == 0 or feedback.developer_email is None:
            feedback.developer_email = email
            db.commit()

        # ✅ Create feedback-developer link if not exists
        link = db.query(FeedbackDeveloper).filter_by(
            feedback_id=feedback.id,
            developer_id=developer.id
        ).first()

        if not link:
            link = FeedbackDeveloper(
                feedback_id=feedback.id,
                developer_id=developer.id,
                status=FeedbackDeveloperStatus.pending
            )
            db.add(link)

        db.commit()

        # ✅ Send email notification
        feedback_url = send_feedback_email(
            to_email=email,
            feedback_id=feedback.id,
            feedback_name=feedback.name
        )

        developer_urls.append({
            "email": email,
            "url": feedback_url
        })

    return {
        "message": "Feedback shared successfully",
        "developer_feedback_urls": developer_urls
    }

def assign_pending_feedbacks_to_developer(db: Session, developer: Developer):
    """Link all feedbacks that were shared via developer's email before signup"""
    feedbacks = db.query(Feedback).filter_by(developer_email=developer.email).all()

    for feedback in feedbacks:
        # Create FeedbackDeveloper link
        existing_link = db.query(FeedbackDeveloper).filter_by(
            feedback_id=feedback.id,
            developer_id=developer.id
        ).first()

        if not existing_link:
            link = FeedbackDeveloper(
                feedback_id=feedback.id,
                developer_id=developer.id,
                status=FeedbackDeveloperStatus.pending
            )
            db.add(link)

        # Assign feedback to developer's workspace
        if developer.workspace_id:
            feedback.workspace_id = developer.workspace_id

        # Clear temp email field
        feedback.developer_email = None

    db.commit()

import pytz

def handle_developer_action(db: Session, feedback_id: int, email: str, action: str):
    from models.feedback_developer import FeedbackDeveloperStatus

    developer = db.query(Developer).filter_by(email=email).first()
    if not developer:
        raise HTTPException(status_code=404, detail="Developer not found")

    link = db.query(FeedbackDeveloper).filter_by(
        feedback_id=feedback_id,
        developer_id=developer.id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Developer not linked to this feedback")

    try:
        link.status = FeedbackDeveloperStatus(action)
        # ✅ Store time in IST
        ist = pytz.timezone('Asia/Kolkata')
        link.action_time = datetime.now(ist)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid action")

    db.commit()

    return {"message": f"Feedback marked as '{action}' by {email}"}

# def handle_developer_action(
#     db: Session,
#     feedback_id: int,
#     email: str,
#     action: str
# ) -> Dict[str, str]:
#     """Handle developer's action on feedback"""
#     developer = db.query(Developer).filter_by(email=email).first()
#     if not developer:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Developer not found"
#         )

#     link = db.query(FeedbackDeveloper).filter_by(
#         feedback_id=feedback_id,
#         developer_id=developer.id
#     ).first()

#     if not link:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Developer not linked to this feedback"
#         )

#     try:
#         link.status = FeedbackDeveloperStatus(action)
#         db.commit()
#         return {
#             "message": f"Feedback marked as '{action}' by {email}"
#         }
#     except ValueError:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid action"
#         )

### BILLING SERVICES ###

def get_billing_info() -> Dict[str, Any]:
    """Get billing information for the workspace"""
    return {
        "plan": "Free",
        "features": [
            "Unlimited Members", 
            "Workspace",
            "Basic Integrations"
        ],
        "price": "$0"
    }


def invite_collaborator(
    db: Session,
    workspace_id: int,
    email: str,
    access_type: str,
    invited_by_id: int
):
    #  Validate workspace
    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Only owner can invite
    if workspace.owner_id != invited_by_id:
        raise HTTPException(status_code=403, detail="Only workspace owner can invite collaborators")

    # Check if already invited
    existing = db.query(Collaborator).filter_by(
        workspace_id=workspace_id,
        user_email=email
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Collaborator already invited")

    # Create collaborator record
    collaborator = Collaborator(
        user_email=email,
        access_type=access_type,
        workspace_id=workspace_id,
        invited_by_id=invited_by_id
    )
    db.add(collaborator)
    db.commit()

    # Send invite email
    inviter = db.query(User).filter_by(id=invited_by_id).first()
    if inviter:
        dashboard_url = f"https://yourapp.com/workspace/{workspace_id}/dashboard"  # update if dynamic
        send_invite_email(
            to_email=email,
            workspace_name=workspace.name,
            inviter=inviter.full_name,
            dashboard_url=dashboard_url
        )

    return {"message": f"Collaborator {email} invited with {access_type} access and email sent."}


