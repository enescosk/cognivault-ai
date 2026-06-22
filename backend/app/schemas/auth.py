from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=6, max_length=128)
    locale: str = Field(default="tr", max_length=10)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class UserLocaleUpdateRequest(BaseModel):
    locale: str = Field(pattern="^(tr|en)$")


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    locale: str
    department: str | None = None
    title: str | None = None
    is_active: bool
    role: RoleResponse


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
