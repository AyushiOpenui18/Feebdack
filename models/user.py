from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from core.db.base import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    profile_image = Column(String(1000), nullable=True)
    onboarded = Column(Boolean, default=False)

    workspace = relationship("Workspace", back_populates="owner", uselist=False)
    