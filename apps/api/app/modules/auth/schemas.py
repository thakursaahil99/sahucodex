from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.modules.users.schemas import USERNAME_PATTERN, UserMe

PASSWORD_MIN = 10
PASSWORD_MAX = 128  # bounds Argon2 work an attacker can force per request


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(pattern=USERNAME_PATTERN, description="3-30 characters: letters, digits, _ or -")
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class RegisterResponse(BaseModel):
    user: UserMe


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320, description="Email address or username")
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserMe


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class MessageResponse(BaseModel):
    message: str


class SessionOut(BaseModel):
    id: uuid.UUID
    ip_address: str | None
    user_agent: str | None
    last_active_at: datetime
    current: bool
