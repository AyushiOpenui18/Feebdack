from sqlalchemy.orm import Session
from core.db.session import SessionLocal

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
