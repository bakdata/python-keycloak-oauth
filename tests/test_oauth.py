import json
from pathlib import Path
from typing import Generator
from fastapi import FastAPI, status
from starlette.datastructures import URL
from starlette.middleware.sessions import SessionMiddleware
from keycloak import KeycloakAdmin
import pytest
from keycloak_oauth import KeycloakOAuth2
from testcontainers.keycloak import KeycloakContainer
from fastapi.testclient import TestClient


class TestKeycloakOAuth2:
    RESOURCES_PATH = Path(__file__).parent.absolute() / "resources/keycloak"

    @pytest.fixture(scope="session")
    def keycloak(self) -> Generator[KeycloakAdmin, None, None]:
        container = (
            KeycloakContainer()
            .with_name("keycloak")
            .with_volume_mapping(
                str(self.RESOURCES_PATH),
                "/opt/keycloak/data/import",
            )
        )
        assert isinstance(
            container, KeycloakContainer
        )  # HACK: wrong type annotation in testcontainers `with_command`
        container.start()
        keycloak = container.get_client()
        keycloak.import_realm(
            json.loads(Path(self.RESOURCES_PATH / "realm.json").read_bytes())
        )
        keycloak.change_current_realm("bakdata")
        assert keycloak.connection.base_url == container.get_base_api_url() + "/"
        yield keycloak
        container.stop()

        # NOTE: altenative:
        # container = KeycloakContainer("quay.io/keycloak/keycloak:19.0").with_command(
        #     "start-dev --import-realm"
        # )
        # os.environ["KEYCLOAK_USER"] = "admin"
        # os.environ["KEYCLOAK_PASSWORD"] = "admin"
        # container.env = {
        #     "KC_HTTP_RELATIVE_PATH": "/auth",
        #     "KEYCLOAK_USER": "admin",
        #     "KEYCLOAK_PASSWORD": "admin",
        #     "KEYCLOAK_ADMIN": "admin",
        #     "KEYCLOAK_ADMIN_PASSWORD": "admin",
        # }
        # assert isinstance(container, KeycloakContainer)
        # container.start()
        # keycloak = container.get_client()
        # yield keycloak
        # container.stop()

    @pytest.fixture()
    def app(self) -> FastAPI:
        return FastAPI()

    @pytest.fixture()
    def client(self, app: FastAPI, keycloak: KeycloakAdmin) -> TestClient:
        keycloak_oauth = KeycloakOAuth2(
            client_id="test-client",
            client_secret="ZPSWENNxF0z3rT8xQORol9NpXQFJxiZf",
            server_metadata_url=f"{keycloak.connection.base_url}/realms/bakdata/.well-known/openid-configuration",
            client_kwargs={},
        )
        keycloak_oauth.setup_fastapi_routes()
        app.include_router(keycloak_oauth.router, prefix="/auth")
        app.add_middleware(
            SessionMiddleware, secret_key="ZPSWENNxF0z3rT8xQORol9NpXQFJxiZf"
        )
        return TestClient(app)

    def test_keycloak_setup(self, keycloak: KeycloakAdmin):
        assert keycloak.connection.realm_name == "bakdata"

    def test_login_redirect(self, client: TestClient, keycloak: KeycloakAdmin):
        response = client.get("/auth/login")
        keycloak_base_url = URL(keycloak.connection.base_url)
        assert response.url.host == keycloak_base_url.hostname
        assert response.url.port == keycloak_base_url.port
        assert response.url.path == "/realms/bakdata/protocol/openid-connect/auth"
        assert response.url.params["client_id"] == "test-client"
        assert response.url.params["redirect_uri"]
        assert URL(response.url.params["redirect_uri"]).path == "/auth/callback"
        # assert response.status_code == status.HTTP_200_OK

    def test_logout_redirect(self, client: TestClient):
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert response.headers["location"] == "/"
