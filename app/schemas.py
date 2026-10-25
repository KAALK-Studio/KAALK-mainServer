# app/schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional, List

class RegisterRequest(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    phone: str
    password: str
    newsletter: bool = False

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class AuthResponse(BaseModel):
    success: bool
    accessToken: str
    refreshToken: str
    expiresIn: int
    userName: str
    email: str
    phone: str
    isPro: bool

class CommentCreateRequest(BaseModel):
    author: Optional[str] = "You"
    text: str

class RatingCreateRequest(BaseModel):
    rating: int