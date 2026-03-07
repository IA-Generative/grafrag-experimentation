import logging
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from config import Settings, get_settings

LOGGER = logging.getLogger(__name__)
BEARER_SCHEME = HTTPBearer(auto_error=False)


class GraphViewerAuth:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwk_client = PyJWKClient(self.settings.keycloak_jwks_url)

    def viewer_config(self) -> dict[str, object]:
        return {
            "auth_required": self.settings.graph_viewer_auth_required,
            "openwebui_url": self.settings.openwebui_public_url,
            "keycloak_url": self.settings.keycloak_public_url,
            "keycloak_js_url": self.settings.keycloak_js_url,
            "realm": self.settings.keycloak_realm,
            "client_id": self.settings.graph_viewer_client_id,
        }

    def require_viewer_token(
        self,
        credentials: HTTPAuthorizationCredentials | None = Depends(BEARER_SCHEME),
    ) -> dict[str, object] | None:
        if not self.settings.graph_viewer_auth_required:
            return None

        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid Keycloak bearer token is required for the GraphRAG Viewer.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(credentials.credentials).key
            payload = jwt.decode(
                credentials.credentials,
                signing_key,
                algorithms=["RS256", "RS384", "RS512"],
                issuer=self.settings.keycloak_issuer,
                options={"verify_aud": False},
            )
        except (InvalidTokenError, PyJWKClientError, OSError) as error:
            LOGGER.warning("Graph viewer token validation failed: %s", error)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="The Keycloak token is invalid or expired.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from error

        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="The Keycloak token payload is incomplete.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload


@lru_cache(maxsize=1)
def get_graph_viewer_auth() -> GraphViewerAuth:
    return GraphViewerAuth(get_settings())
