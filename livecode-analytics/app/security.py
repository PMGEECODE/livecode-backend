import hashlib
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import Settings, get_settings


bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def hash_ip(ip: str, settings: Settings) -> Optional[str]:
    if not ip:
        return None
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode("utf-8")).hexdigest()


def require_admin_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> dict:
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing analytics admin token.")
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid analytics admin token.")

    subject = str(payload.get("sub") or "")
    allowed_subjects = settings.admin_subjects
    if allowed_subjects and subject not in allowed_subjects:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Analytics access is not allowed.")
    return payload
