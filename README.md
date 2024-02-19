# starlette-keycloak

Keycloak authentication for FastAPI & Starlette-Admin projects.

## Usage

### FastAPI

```sh
pip install starlette-keycloak[fastapi]
```

```python
from fastapi import FastAPI
from backend.settings import settings, BASE_URL  # secrets
from keycloak.oauth import KeycloakOAuth2

keycloak = KeycloakOAuth2(
    client_id=settings.keycloak.client_id,
    client_secret=settings.keycloak.client_secret,
    server_metadata_url=str(settings.keycloak.server_metadata_url),
    client_kwargs=settings.keycloak.client_kwargs,
    base_url=BASE_URL,
)
# set up the API endpoints
keycloak.setup_fastapi_routes()


app = FastAPI()

app.include_router(keycloak.router, prefix="/auth")

# we now expose the API endpoints for Keycloak:
# /auth/login: redirect to Keycloak login page
# /auth/callback: authorize User with Keycloak access token
# /auth/logout: deauthorize User and redirect to logout page
```

### Starlette-Admin

```sh
pip install starlette-keycloak[starlette]
```

```python
from starlette_admin.contrib.sqla import Admin
from backend.settings import settings, BASE_URL  # secrets
from keycloak.oauth import KeycloakOAuth2
from keycloak.starlette_admin import KeycloakAuthProvider

keycloak = KeycloakOAuth2(
    client_id=settings.keycloak.client_id,
    client_secret=settings.keycloak.client_secret,
    server_metadata_url=str(settings.keycloak.server_metadata_url),
    client_kwargs=settings.keycloak.client_kwargs,
    base_url=BASE_URL,
)

admin = Admin(
    # engine,
    title=...,
    base_url=BASE_URL,
    auth_provider=KeycloakAuthProvider(keycloak),
)
```
