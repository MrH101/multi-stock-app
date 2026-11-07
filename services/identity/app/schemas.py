from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from multistock_common.auth import OrgType, Role


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: OrgType
    license_number: str | None
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    verified: bool
    is_active: bool
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    org_id: int
    email: str
    full_name: str
    phone: str | None
    role: Role
    is_active: bool
    created_at: datetime


class RegisterRequest(BaseModel):
    org_type: OrgType = Field(description="PHARMACY or SUPPLIER")
    org_name: str = Field(min_length=2, max_length=200)
    license_number: str = Field(min_length=3, max_length=100, description="MCAZ licence number")
    org_phone: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionOut(TokenPair):
    user: UserOut
    organization: OrganizationOut


class MeOut(BaseModel):
    user: UserOut
    organization: OrganizationOut


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = None
    role: Role = Role.STAFF
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    phone: str | None = None
    role: Role | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AdminOrganizationUpdate(BaseModel):
    verified: bool | None = None
    is_active: bool | None = None
