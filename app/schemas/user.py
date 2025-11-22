from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi_users import schemas
from pydantic import Field, ConfigDict


class UserRead(schemas.BaseUser[UUID]):
    """Schema for reading user data."""

    username: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserCreate(schemas.BaseUserCreate):
    """Schema for user registration."""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: str
    password: str = Field(..., min_length=8)


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating user data."""

    username: Optional[str] = Field(None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)


class OAuthAccount(schemas.BaseOAuthAccount):
    """Schema for OAuth account data."""

    pass
