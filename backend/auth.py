from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


LOCAL_DEV_TOKEN = "local-dev-token"

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class LocalUser:
    user_id: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> LocalUser:
    if credentials is None or credentials.credentials != LOCAL_DEV_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return LocalUser(user_id="local-dev-user")
