import os
from dataclasses import dataclass

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN", "")

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class LocalUser:
    user_id: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
) -> LocalUser:
    if not API_TOKEN or credentials is None or credentials.credentials != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return LocalUser(user_id="local-dev-user")
