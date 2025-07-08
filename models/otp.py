from sqlalchemy import Column, Integer, String, DateTime, LargeBinary
from datetime import datetime, timedelta
from core.db.base import Base

class OTP_Tbl(Base):
    __tablename__ = "otp"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False)
    otp_code = Column(LargeBinary, nullable=False)  # ✅ store as bytes
    full_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    attempts = Column(Integer, default=0)
    resend_count = Column(Integer, default=1)
    locked_until = Column(DateTime, nullable=True)

    def is_expired(self) -> bool:
        return self.created_at < datetime.utcnow() - timedelta(minutes=5)

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > datetime.utcnow())
