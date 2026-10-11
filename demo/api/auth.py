import time
from typing import Optional
from fastapi import Header, HTTPException
from jose import jwt

SECRET_KEY = "specnetra-demo-secret-key-for-test-target"
ALGORITHM = "HS256"


def create_access_token(data: dict, expires_delta_seconds: int = 3600) -> str:
    to_encode = data.copy()
    expire = time.time() + expires_delta_seconds
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None


def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split("Bearer ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload["sub"]
