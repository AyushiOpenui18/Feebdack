from sqlalchemy import Column, Integer, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from core.db.base import Base
import enum
from sqlalchemy import DateTime

class FeedbackDeveloperStatus(str, enum.Enum):
    pending = "pending"
    acknowledged = "acknowledged"
    unclear = "unclear"

class FeedbackDeveloper(Base):
    __tablename__ = "feedback_developer"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    feedback_id = Column(Integer, ForeignKey("feedback.id"))
    developer_id = Column(Integer, ForeignKey("developers.id"))
    status = Column(Enum(FeedbackDeveloperStatus), default=FeedbackDeveloperStatus.pending)
    action_time = Column(DateTime, nullable=True)

    feedback = relationship("Feedback", back_populates="feedback_developer_links")
    developer = relationship("Developer", back_populates="feedback_developer_links")

    __table_args__ = (
        UniqueConstraint('feedback_id', 'developer_id', name='uix_feedback_developer'),
    )