# Keycloak

The realm file in this directory is imported by:

- the optional Docker Compose Keycloak container
- the Kubernetes `keycloak` deployment after `deploy-k8s.sh` creates the `keycloak-realm` ConfigMap

Realm settings:

- Realm: `openwebui`
- Client: `openwebui`
- Redirect URI: `https://openwebui.fake-domain.change.me/*`
- Issuer: `https://openwebui-sso.fake-domain.change.me/realms/openwebui`

The client secret in the realm export is intentionally set to `CHANGE_ME`. Replace it through Kubernetes secrets or environment variables before using real SSO flows.

