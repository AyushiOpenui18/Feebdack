# # models/folder.py
# from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
# from sqlalchemy.orm import relationship
# from datetime import datetime
# from core.db.base import Base

# class Folder(Base):
#     __tablename__ = "folders"

#     id = Column(Integer, primary_key=True)
#     name = Column(String(255), nullable=False)
#     type = Column(String(100))
#     created_by = Column(Integer, ForeignKey("users.id"))
#     workspace_id = Column(Integer, ForeignKey("workspaces.id"))
#     access_type = Column(String(50))
#     created_at = Column(DateTime, default=datetime.utcnow)

#     # feedbacks = relationship("Feedback", back_populates="folder", cascade="all, delete-orphan")

#     # collaborators = relationship("Collaborator", back_populates="folder", cascade="all, delete-orphan")
