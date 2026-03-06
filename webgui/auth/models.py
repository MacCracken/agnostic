"""Auth data models — enums and dataclasses."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class UserRole(Enum):
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    TEAM_LEAD = "team_lead"
    QA_ENGINEER = "qa_engineer"
    VIEWER = "viewer"
    API_USER = "api_user"


class Permission(Enum):
    SESSIONS_READ = "sessions:read"
    SESSIONS_WRITE = "sessions:write"
    SESSIONS_DELETE = "sessions:delete"
    AGENTS_CONTROL = "agents:control"
    REPORTS_GENERATE = "reports:generate"
    REPORTS_EXPORT = "reports:export"
    USERS_MANAGE = "users:manage"
    SYSTEM_CONFIGURE = "system:configure"
    API_ACCESS = "api:access"


class AuthProvider(Enum):
    LOCAL = "local"
    GOOGLE = "google"
    GITHUB = "github"
    AZURE_AD = "azure_ad"
    SAML = "saml"


@dataclass
class User:
    user_id: str
    email: str
    name: str
    role: UserRole
    auth_provider: AuthProvider
    organization_id: str | None
    team_id: str | None
    created_at: datetime
    last_login: datetime | None
    is_active: bool
    permissions: set[Permission]
    metadata: dict[str, Any]


@dataclass
class AuthToken:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes
    scope: str = "read write"
