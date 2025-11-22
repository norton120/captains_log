"""User model for authentication and authorization."""

from datetime import datetime
from uuid import UUID, uuid4

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Column, String, DateTime, Boolean, or_
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import relationship

from app.models.log_entry import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model for the application with FastAPI Users integration."""

    __tablename__ = "users"

    username = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    authored_logs = relationship("LogEntry", back_populates="user", lazy="select", foreign_keys="LogEntry.user_id")

    @property
    def logs(self):
        """
        All logs visible to this user.

        This includes:
        - All logs authored by this user (PERSONAL and SHIP)
        - All SHIP logs from other users
        """
        from app.models.log_entry import LogEntry, LogType
        from sqlalchemy.orm import object_session

        session = object_session(self)
        if session is None:
            # If not attached to a session, return authored logs
            return self.authored_logs

        # Return all SHIP logs OR logs authored by this user
        return session.query(LogEntry).filter(or_(LogEntry.log_type == LogType.SHIP, LogEntry.user_id == self.id)).all()

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"
