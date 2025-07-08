from sqlalchemy import Column, Integer, String, Enum, ForeignKey
from sqlalchemy.orm import relationship
from core.db.base import Base
import enum

class AccessLevel(str, enum.Enum):
    comment = "comment"
    edit = "edit"

class FeedbackAccess(Base):
    __tablename__ = "feedback_access"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("feedback.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String(255), nullable=False)
    access_type = Column(Enum(AccessLevel), default=AccessLevel.comment)

    feedback = relationship("Feedback", back_populates="accesses")
    user = relationship("User")
