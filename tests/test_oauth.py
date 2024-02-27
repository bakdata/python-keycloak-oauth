import json
from pathlib import Path
from typing import Generator
from fastapi import FastAPI, status
from starlette.middleware.sessions import SessionMiddleware
from keycloak import KeycloakAdmin
import pytest
from keycloak_oauth import KeycloakOAuth2
from keycloak_testcontainer import KeycloakContainer
from fastapi.testclient import TestClient


class TestKeycloakOAuth2:
    KEYCLOAK_BASE_URL = "http://localhost:8080"
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
    def client(self, app: FastAPI) -> TestClient:
        keycloak = KeycloakOAuth2(
            client_id="test-client",
            client_secret="ZPSWENNxF0z3rT8xQORol9NpXQFJxiZf",
            server_metadata_url=f"{self.KEYCLOAK_BASE_URL}/realms/bakdata/.well-known/openid-configuration",
            client_kwargs={},
        )
        keycloak.setup_fastapi_routes()
        app.include_router(keycloak.router, prefix="/auth")
        app.add_middleware(
            SessionMiddleware, secret_key="ZPSWENNxF0z3rT8xQORol9NpXQFJxiZf"
        )
        return TestClient(app)

    def test_keycloak_setup(self, keycloak: KeycloakAdmin):
        assert keycloak.connection.realm_name == "bakdata"

    @pytest.mark.usefixtures("keycloak")
    def test_login_redirect(self, client: TestClient):
        response = client.get("/auth/login", follow_redirects=False)
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert response.headers["location"] == "/auth/callback"

    def test_logout_redirect(self, client: TestClient):
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert response.headers["location"] == "/"
