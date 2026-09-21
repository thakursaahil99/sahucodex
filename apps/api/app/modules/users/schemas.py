from __future__ import annotations

import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.users.models import User

USERNAME_PATTERN = r"^[A-Za-z0-9_-]{3,30}$"
_GITHUB_HOSTS = {"github.com", "www.github.com"}
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")


def _clean_http_url(value: str | None, *, hosts: set[str] | None = None) -> str | None:
    """Only absolute http(s) URLs are accepted — this blocks `javascript:` and `data:` links that
    would otherwise become stored XSS when rendered as an <a href>."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 300:
        raise ValueError("URL is too long")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    if hosts is not None and parsed.hostname.lower() not in hosts:
        raise ValueError("URL host is not allowed for this field")
    return value


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    avatar_url: str | None
    bio: str | None
    country: str | None
    website: str | None
    github_url: str | None


class UserMe(BaseModel):
    """The signed-in user's own view of their account."""

    id: uuid.UUID
    email: str
    username: str
    roles: list[str]
    email_verified: bool
    created_at: datetime
    profile: ProfileOut


class PublicProfile(BaseModel):
    """What anyone may see. No email, no roles, no internal ids."""

    username: str
    avatar_url: str | None
    bio: str | None
    country: str | None
    website: str | None
    github_url: str | None
    joined_at: datetime


class ProfileUpdate(BaseModel):
    """Only these fields can be changed through the self-service API. Anything else — role,
    email, is_active — is rejected (extra="forbid") rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")

    bio: str | None = Field(default=None, max_length=500)
    country: str | None = None
    website: str | None = None
    github_url: str | None = None
    avatar_url: str | None = None

    @field_validator("bio")
    @classmethod
    def _bio(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("country")
    @classmethod
    def _country(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if not _COUNTRY_RE.match(value.strip()):
            raise ValueError("must be a two-letter ISO country code")
        return value.strip().upper()

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        return _clean_http_url(value)

    @field_validator("github_url")
    @classmethod
    def _github(cls, value: str | None) -> str | None:
        return _clean_http_url(value, hosts=_GITHUB_HOSTS)

    @field_validator("avatar_url")
    @classmethod
    def _avatar(cls, value: str | None) -> str | None:
        # No upload/storage yet (see docs/security.md); a plain http(s) URL, same XSS-blocking rule as website.
        return _clean_http_url(value)


class AdminUser(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    roles: list[str]
    is_active: bool
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None


def to_user_me(user: User) -> UserMe:
    return UserMe(
        id=user.id,
        email=user.email,
        username=user.username,
        roles=user.roles,
        email_verified=user.is_email_verified,
        created_at=user.created_at,
        profile=ProfileOut.model_validate(user.profile),
    )


def to_public_profile(user: User) -> PublicProfile:
    return PublicProfile(
        username=user.username,
        avatar_url=user.profile.avatar_url,
        bio=user.profile.bio,
        country=user.profile.country,
        website=user.profile.website,
        github_url=user.profile.github_url,
        joined_at=user.created_at,
    )


def to_admin_user(user: User) -> AdminUser:
    return AdminUser(
        id=user.id,
        email=user.email,
        username=user.username,
        roles=user.roles,
        is_active=user.is_active,
        email_verified=user.is_email_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
