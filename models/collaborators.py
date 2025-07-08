from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from core.db.base import Base

class Collaborator(Base):
    __tablename__ = "collaborator"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String(255), nullable=False)
    access_type = Column(String(10), default="comment")
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)  # Made non-nullable
    
    # Remove folder-related fields
    feedback_id = Column(Integer, ForeignKey("feedback.id", ondelete="CASCADE"), nullable=True)
    
    feedback = relationship("Feedback", back_populates="collaborators", foreign_keys=[feedback_id])
    user = relationship("User", foreign_keys=[user_id])
    workspace = relationship("Workspace")
    
    invited_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    invited_by = relationship("User", foreign_keys=[invited_by_id], backref="invited_collaborators")