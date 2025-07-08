from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from core.db.base import Base

class Developer(Base):
    __tablename__ = "developers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)

    # Developer's own workspace (when registered)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)

    # 🔹 Client's workspace who invited the developer or shared feedback
    invited_by_workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)

    # Relationships
    workspace = relationship("Workspace", foreign_keys=[workspace_id])
    invited_by_workspace = relationship("Workspace", foreign_keys=[invited_by_workspace_id])

    feedback_developer_links = relationship(
        "FeedbackDeveloper",
        back_populates="developer",
        cascade="all, delete-orphan"
    )

