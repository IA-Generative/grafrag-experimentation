import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from config import Settings, get_settings

LOGGER = logging.getLogger(__name__)
BEARER_SCHEME = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    sub: str
    email: str
    preferred_username: str
    groups: list[str]
    roles: list[str]
    raw_payload: dict[str, object]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


class KeycloakTokenValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwk_client = PyJWKClient(self.settings.keycloak_jwks_url)

    def client_config(self, client_id: str, auth_required: bool) -> dict[str, object]:
        return {
            "auth_required": auth_required,
            "openwebui_url": self.settings.openwebui_public_url,
            "keycloak_url": self.settings.keycloak_public_url,
            "keycloak_js_url": self.settings.keycloak_js_url,
            "realm": self.settings.keycloak_realm,
            "client_id": client_id,
        }

    def validate_token(self, token: str) -> dict[str, object]:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token).key
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256", "RS384", "RS512"],
                issuer=self.settings.keycloak_issuer,
                options={"verify_aud": False},
            )
        except (InvalidTokenError, PyJWKClientError, OSError) as error:
            LOGGER.warning("Keycloak token validation failed: %s", error)
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

    def optional_payload(
        self,
        credentials: HTTPAuthorizationCredentials | None,
    ) -> dict[str, object] | None:
        if credentials is None or credentials.scheme.lower() != "bearer":
            return None
        return self.validate_token(credentials.credentials)

    def require_payload(
        self,
        credentials: HTTPAuthorizationCredentials | None,
        detail: str,
    ) -> dict[str, object]:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return self.validate_token(credentials.credentials)

    def user_from_payload(self, payload: dict[str, object]) -> AuthenticatedUser:
        realm_access = payload.get("realm_access")
        if isinstance(realm_access, dict):
            roles = realm_access.get("roles")
            role_values = [str(item) for item in roles] if isinstance(roles, list) else []
        else:
            role_values = []

        groups = payload.get("groups")
        group_values = [str(item) for item in groups] if isinstance(groups, list) else []

        return AuthenticatedUser(
            sub=str(payload.get("sub") or ""),
            email=str(payload.get("email") or ""),
            preferred_username=str(
                payload.get("preferred_username")
                or payload.get("name")
                or payload.get("email")
                or payload.get("sub")
                or ""
            ),
            groups=group_values,
            roles=role_values,
            raw_payload=payload,
        )


class GraphViewerAuth:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.validator = KeycloakTokenValidator(settings)

    def viewer_config(self) -> dict[str, object]:
        return self.validator.client_config(
            self.settings.graph_viewer_client_id,
            self.settings.graph_viewer_auth_required,
        )

    def require_viewer_token(
        self,
        credentials: HTTPAuthorizationCredentials | None = Depends(BEARER_SCHEME),
    ) -> dict[str, object] | None:
        if not self.settings.graph_viewer_auth_required:
            return None
        return self.validator.require_payload(
            credentials,
            "A valid Keycloak bearer token is required for the GraphRAG Viewer.",
        )


class CorpusManagerAuth:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.validator = KeycloakTokenValidator(settings)

    def viewer_config(self) -> dict[str, object]:
        config = self.validator.client_config(
            self.settings.corpus_manager_client_id,
            self.settings.corpus_manager_auth_required,
        )
        config["corpus_manager_url"] = self.settings.corpus_manager_public_url
        return config

    def require_user(
        self,
        credentials: HTTPAuthorizationCredentials | None = Depends(BEARER_SCHEME),
    ) -> AuthenticatedUser:
        if not self.settings.corpus_manager_auth_required:
            return AuthenticatedUser(
                sub="local-admin",
                email="local-admin@test.local",
                preferred_username="local-admin",
                groups=["local-admins"],
                roles=["admin"],
                raw_payload={},
            )
        payload = self.validator.require_payload(
            credentials,
            "A valid Keycloak bearer token is required for the Corpus Manager.",
        )
        return self.validator.user_from_payload(payload)


@lru_cache(maxsize=1)
def get_keycloak_token_validator() -> KeycloakTokenValidator:
    return KeycloakTokenValidator(get_settings())


@lru_cache(maxsize=1)
def get_graph_viewer_auth() -> GraphViewerAuth:
    return GraphViewerAuth(get_settings())


@lru_cache(maxsize=1)
def get_corpus_manager_auth() -> CorpusManagerAuth:
    return CorpusManagerAuth(get_settings())
