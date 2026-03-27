"""
JWT Authentication for API Gateway
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)

# JWT Configuration
JWT_SECRET: str = os.getenv("JWT_SECRET", "dev_secret")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRATION_MINUTES: int = 60


class AuthError(HTTPException):
    """Authentication error"""
    
    def __init__(self, detail: str = "Invalid or expired token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User identifier to encode in token
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    
    to_encode = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload dictionary
        
    Raises:
        AuthError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise AuthError(f"Token validation failed: {str(e)}")


def get_user_id_from_token(token: str) -> str:
    """
    Extract user_id from JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        User ID string
        
    Raises:
        AuthError: If token is invalid or missing user_id
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    
    if not user_id:
        raise AuthError("Token missing user_id (sub claim)")
    
    return user_id


async def verify_token(credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    """
    FastAPI dependency to verify JWT token from Authorization header.
    
    Args:
        credentials: HTTP Bearer credentials from request header
        
    Returns:
        User ID extracted from token
        
    Raises:
        AuthError: If credentials missing, invalid, or expired
    """
    if credentials is None:
        raise AuthError("Missing Authorization header")
    
    if credentials.scheme.lower() != "bearer":
        raise AuthError(f"Invalid authentication scheme: {credentials.scheme}")
    
    token = credentials.credentials
    return get_user_id_from_token(token)


def refresh_token(token: str) -> str:
    """
    Refresh an existing token by decoding and re-encoding with new expiration.
    Used for mid-stream token refresh in v2 streaming.
    
    Args:
        token: Existing JWT token
        
    Returns:
        New JWT token with extended expiration
        
    Raises:
        AuthError: If token is invalid
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    
    if not user_id:
        raise AuthError("Token missing user_id (sub claim)")
    
    return create_access_token(user_id)
