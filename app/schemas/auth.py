from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class GoogleIn(BaseModel):
    id_token: str


class UserOut(BaseModel):
    id: str
    email: EmailStr | None
