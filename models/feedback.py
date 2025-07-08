from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from core.db.base import Base
import enum

class FeedbackStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    edited = "edited"

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)

    created_by = Column(Integer, ForeignKey("users.id"))
    status = Column(Enum(FeedbackStatus), default=FeedbackStatus.draft)
    url = Column(String(500))
    screenshot_url = Column(String(500))
    recording_url = Column(String(500))
    voice_recording_url = Column(String(500), nullable=True)
    message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 🔹 Feedback assigned via email (for pre-workspace developer)
    developer_email = Column(String(255), nullable=True)

    # 🔹 Linked workspace (if exists)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))

    feedback_developer_links = relationship(
        "FeedbackDeveloper",
        back_populates="feedback",
        cascade="all, delete-orphan"
    )
    
    collaborators = relationship(
        "Collaborator",
        back_populates="feedback",
        cascade="all, delete-orphan"
    )

    accesses = relationship(
        "FeedbackAccess",
        back_populates="feedback",
        cascade="all, delete-orphan"
    )

    workspace = relationship("Workspace")
