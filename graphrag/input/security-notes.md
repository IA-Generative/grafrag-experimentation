# Security Notes

No real credentials are stored in this repository.

Kubernetes secrets must be created from placeholder templates or generated from environment variables during deployment. Ingress resources terminate TLS with cert-manager and Let's Encrypt, and Keycloak handles OIDC-based authentication for Open WebUI.

