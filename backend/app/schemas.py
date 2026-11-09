from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Role(StrEnum):
    employee = "employee"
    responsible = "responsible"
    coordinator = "coordinator"


class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Укажите имя или название")
        return value


class EmailInput(BaseModel):
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value


class LoginInput(EmailInput):
    password: str = Field(min_length=1, max_length=128)


class TokenInput(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class AcceptInput(TokenInput):
    password: str = Field(min_length=12, max_length=128)


class InviteInput(NameInput, EmailInput):
    company_id: UUID
    department_id: UUID
    roles: list[Role] = Field(default_factory=lambda: [Role.employee], max_length=3)
    expires_in_days: int = Field(default=7, ge=1, le=30)


class UserUpdate(BaseModel):
    roles: list[Role] = Field(max_length=3)
    is_active: bool


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: str
    company_id: UUID
    department_id: UUID
    roles: list[Role]
    is_active: bool
    created_at: datetime


class CompanyPublic(NameInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class DepartmentInput(NameInput):
    company_id: UUID


class DepartmentPublic(DepartmentInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class InvitePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: str
    company_id: UUID
    department_id: UUID
    roles: list[Role]
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None


class InviteCreated(InvitePublic):
    activation_path: str


class InvitePreview(BaseModel):
    name: str
    email: str
    company: str
    department: str
    roles: list[Role]
    expires_at: datetime
