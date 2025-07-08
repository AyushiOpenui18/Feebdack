from pydantic import BaseModel, EmailStr, HttpUrl, Field, validator
from typing import List, Optional, Literal
from datetime import datetime
from enum import Enum
import re

# -----------------------------
#  Auth / OTP / Onboarding
# -----------------------------

class SignupRequest(BaseModel):
    full_name: str
    email: EmailStr

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

class SigninRequest(BaseModel):
    email: EmailStr

class WorkspaceCreate(BaseModel):
    workspace_name: str
    type: Literal["Company", "Individual"]
    purpose: Literal["Work", "Personal"]
    role: Literal["Engineer", "Designer", "Developer", "Other"]
    icon_url: Optional[str] = None
    collaborators: Optional[List[EmailStr]] = None

# -----------------------------
#  Feedback Schemas
# -----------------------------

class FeedbackStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    edited = "edited"

class AccessLevel(str, Enum):
    comment = "comment"
    edit = "edit"

class FeedbackCollaborator(BaseModel):
    email: EmailStr
    access: AccessLevel = AccessLevel.comment
    user_id: Optional[int] = None

class FeedbackCreate(BaseModel):
    name: str
    workspace_id: int
    url: Optional[HttpUrl] = None
    message: Optional[str] = None
    collaborators: List[FeedbackCollaborator] = Field(default_factory=list)
    screenshot_url: Optional[str] = None
    recording_url: Optional[str] = None

    @validator("name")
    def name_must_be_valid(cls, value):
        if not value.strip():
            raise ValueError("Feedback name is required")
        if len(value) > 100:
            raise ValueError("Name must be under 100 characters")
        if not re.match(r"^[\w\s\-.,!?()]+$", value):
            raise ValueError("Invalid characters in name")
        return value

class FeedbackUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    message: Optional[str] = None
    status: Optional[FeedbackStatus] = None
    voice_recording_url: Optional[str] = None
    screenshot_url: Optional[str] = None
    recording_url: Optional[str] = None

    class Config:
        extra = "forbid"

class FeedbackOut(BaseModel):
    id: int
    name: str
    workspace_id: int
    created_by: int
    url: Optional[HttpUrl]
    screenshot_url: Optional[str]
    recording_url: Optional[str]
    voice_recording_url: Optional[str]
    message: Optional[str]
    status: FeedbackStatus
    created_at: datetime
    collaborators: List[FeedbackCollaborator] = []

    class Config:
        orm_mode = True

# -----------------------------
#  Developer Sharing
# -----------------------------

class DeveloperShareRequest(BaseModel):
    """Schema for sharing feedback with multiple developers via email"""
    developer_emails: List[EmailStr]

class DeveloperActionRequest(BaseModel):
    """Schema for developer to take action on assigned feedback"""
    action: Literal["acknowledged", "unclear"]

# class DeveloperShareRequest(BaseModel):
#     developer_emails: List[EmailStr]

# class DeveloperActionRequest(BaseModel):
#     action: Literal["acknowledged", "unclear"]

# -----------------------------
#  Workspace & User Management
# -----------------------------

class WorkspaceOut(BaseModel):
    id: int
    name: str
    subdomain: str
    type: str
    purpose: str
    role: str
    icon_url: Optional[str]
    owner_id: int

    class Config:
        orm_mode = True

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    profile_url: Optional[str] = None

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str

    class Config:
        orm_mode = True

class MemberRole(str, Enum):
    admin = "admin"
    collaborator = "collaborator"

class MemberStatus(str, Enum):
    active = "active"
    pending = "pending"

class MemberOut(BaseModel):
    id: Optional[int]
    email: EmailStr
    name: str
    role: MemberRole
    status: MemberStatus
    joined_at: Optional[datetime]

    class Config:
        orm_mode = True

# -----------------------------
#  File Upload
# -----------------------------

class FileUploadResponse(BaseModel):
    status: str
    file_url: str

class VoiceUploadResponse(BaseModel):
    status: str
    voice_url: str


class CollaboratorInvite(BaseModel):
    email: EmailStr
    access_type: Literal["comment", "edit"]