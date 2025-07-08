from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from core.db.base import Base

class Workspace(Base):
    __tablename__ = "workspaces"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    subdomain = Column(String(255), unique=True)
    type = Column(String(100))
    purpose = Column(String(100))
    role = Column(String(100))
    icon_url = Column(String(255), nullable=True)

    # 🆕 Optional field to store comma-separated invited emails
    invite_emails = Column(String(1000), nullable=True)  # e.g., "a@example.com,b@example.com"

    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="workspace")

