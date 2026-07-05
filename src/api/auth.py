"""Basic-auth check for API access.

Caddy already enforces basic auth at the proxy layer for the public tunnel;
this adds a second layer for direct API access.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(realm="SSWA Demo")


def check_credentials(credentials: HTTPBasicCredentials) -> bool:
    username = os.environ.get("API_USERNAME", "reviewer")
    password = os.environ.get("API_PASSWORD", "change_me_in_prod")
    user_ok = secrets.compare_digest(credentials.username.encode(), username.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), password.encode())
    return user_ok and pass_ok


def require_auth(credentials: HTTPBasicCredentials) -> str:
    if not check_credentials(credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
