"""JWT authentication and tenant authorization.

Security: Validates Keycloak JWT tokens and extracts tenant claims.
All API endpoints should use these dependencies for proper multi-tenant isolation.
"""

import os
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

# =============================================================================
# Configuration
# =============================================================================


@lru_cache
def get_keycloak_config() -> dict:
    """Get Keycloak configuration from environment.

    Prefers backend-specific env vars (KEYCLOAK_URL, KEYCLOAK_REALM),
    falls back to VITE_* for local development compatibility.
    """
    # Backend-preferred env vars (fall back to VITE_* for dev convenience)
    keycloak_url = os.getenv("KEYCLOAK_URL") or os.getenv("VITE_KEYCLOAK_URL")
    keycloak_realm = os.getenv("KEYCLOAK_REALM") or os.getenv("VITE_KEYCLOAK_REALM")

    # Fail fast in production if not configured
    environment = os.getenv("ENVIRONMENT", "development")
    if environment == "production" and (not keycloak_url or not keycloak_realm):
        raise RuntimeError(
            "KEYCLOAK_URL and KEYCLOAK_REALM must be set in production. "
            "See .env.example for configuration."
        )

    # Defaults for local development
    keycloak_url = keycloak_url or "http://localhost:8080"
    keycloak_realm = keycloak_realm or "vartalaap"

    return {
        "issuer": os.getenv(
            "KEYCLOAK_ISSUER",
            f"{keycloak_url}/realms/{keycloak_realm}",
        ),
        "audience": os.getenv("KEYCLOAK_AUDIENCE", "account"),
        # In production, fetch JWKS from Keycloak. For MVP, use symmetric key.
        "secret": os.getenv("JWT_SECRET"),
        "algorithms": ["RS256", "HS256"],
        "verify": os.getenv("JWT_VERIFY", "true").lower() == "true",
    }


# =============================================================================
# Token Models
# =============================================================================


class TokenPayload(BaseModel):
    """Validated JWT token payload."""

    sub: str  # Subject (user ID)
    email: str | None = None
    preferred_username: str | None = None
    realm_access: dict | None = None
    resource_access: dict | None = None
    business_ids: list[str] | None = None  # Custom claim for multi-tenant
    exp: int | None = None
    iat: int | None = None

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        roles = self.realm_access.get("roles", []) if self.realm_access else []
        return "admin" in roles or "realm-admin" in roles

    def can_access_business(self, business_id: str) -> bool:
        """Check if user can access a specific business.

        Access is granted if:
        1. User has admin role (can access all businesses)
        2. business_ids claim includes the requested business
        3. resource_access has the business as a resource
        """
        if self.is_admin:
            return True

        # Check custom business_ids claim
        if self.business_ids and business_id in self.business_ids:
            return True

        # Check resource_access (Keycloak standard for client roles)
        return bool(self.resource_access and business_id in self.resource_access)


# =============================================================================
# Token Validation
# =============================================================================


def decode_token(token: str) -> TokenPayload:
    """Decode and validate JWT token.

    In production with Keycloak RS256, this fetches the JWKS and validates.
    For development/MVP, can use symmetric key or skip verification.
    """
    config = get_keycloak_config()

    try:
        # Remove "Bearer " prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        options = {}
        if not config["verify"]:
            # Development mode: skip signature verification
            options = {
                "verify_signature": False,
                "verify_exp": True,
                "verify_aud": False,
            }
            payload = jwt.decode(token, options=options, algorithms=config["algorithms"])  # type: ignore[arg-type]
        elif config["secret"]:
            # Symmetric key verification (for testing)
            payload = jwt.decode(
                token,
                config["secret"],
                algorithms=["HS256"],
                audience=config["audience"],
            )
        else:
            # RS256 with JWKS (production Keycloak)
            # Fetch JWKS from Keycloak's well-known endpoint
            jwks_url = f"{config['issuer']}/protocol/openid-connect/certs"
            jwks_client = jwt.PyJWKClient(jwks_url, cache_keys=True)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=config["audience"],
                issuer=config["issuer"],
            )

        return TokenPayload(**payload)

    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.InvalidAudienceError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.InvalidIssuerError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# =============================================================================
# FastAPI Dependencies
# =============================================================================


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> TokenPayload:
    """Extract and validate JWT token from Authorization header.

    Use this dependency when you need the full token payload.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return decode_token(authorization)


async def get_authorized_business_id(
    x_business_id: Annotated[str | None, Header()] = None,
    user: TokenPayload = Depends(get_current_user),  # noqa: B008
) -> str:
    """Extract and validate business_id with tenant authorization.

    Ensures the authenticated user has access to the requested business.
    Use this dependency for all tenant-scoped endpoints.
    """
    if not x_business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Business-ID header required",
        )

    if not user.can_access_business(x_business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to access business '{x_business_id}'",
        )

    return x_business_id


# Alias for clearer intent in route definitions
RequireAuth = Annotated[TokenPayload, Depends(get_current_user)]
RequireBusinessAccess = Annotated[str, Depends(get_authorized_business_id)]
