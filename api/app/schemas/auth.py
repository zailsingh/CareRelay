from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserRead


class DevLoginRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(str_strip_whitespace=True)


class AppleLoginRequest(BaseModel):
    identity_token: str = Field(min_length=1)
    nonce: str = Field(min_length=32, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)

    model_config = ConfigDict(str_strip_whitespace=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead

    model_config = ConfigDict(from_attributes=True)


class AppleNotificationRequest(BaseModel):
    payload: str = Field(min_length=1)
