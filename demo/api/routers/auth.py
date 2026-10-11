from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from demo.api.auth import create_access_token, get_current_user
from demo.api.database import SEED_USERS
from demo.api.models import LoginRequest, LoginResponse, UserProfile

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    expected_password = SEED_USERS.get(req.email)
    if not expected_password or expected_password != req.password:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Invalid credentials",
                }
            },
        )
    token = create_access_token({"sub": req.email})
    return LoginResponse(access_token=token)


@router.get("/me", response_model=UserProfile)
async def get_me(user_email: str = Depends(get_current_user)):
    return UserProfile(email=user_email, role="user")
