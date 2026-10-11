from typing import Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class UserProfile(BaseModel):
    email: str
    role: str = "user"


class AppointmentCreate(BaseModel):
    patient_name: str = Field(min_length=1)
    starts_at: str
    reason: Optional[str] = None


class Appointment(BaseModel):
    id: str
    patient_name: str
    starts_at: str
    status: str = "confirmed"
    reason: Optional[str] = None
