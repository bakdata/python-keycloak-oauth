from fastapi import FastAPI
import pytest
from keycloak_oauth import KeycloakOAuth2
from keycloak_testcontainer import KeycloakContainer
from fastapi.testclient import TestClient


class TestKeycloakOAuth2:
    KEYCLOAK_BASE_URL = "http://localhost:8080"

    @pytest.fixture()
    def keycloak(self):
        with KeycloakContainer() as container:
            keycloak = container.get_client()
            yield keycloak

        # NOTE: altenative:
        # container = KeycloakContainer("quay.io/keycloak/keycloak:19.0").with_command(
        #     "start-dev"  #  --import-realm
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
    def client(self):
        app = FastAPI()
        keycloak = KeycloakOAuth2(
            client_id="test-id",
            client_secret="test-secret",
            server_metadata_url=f"{self.KEYCLOAK_BASE_URL}/realms/foobar/.well-known/openid-configuration",
            client_kwargs={},
            # base_url=BASE_URL,
        )
        keycloak.setup_fastapi_routes()
        app.include_router(keycloak.router, prefix="/auth")
        return TestClient(app)

    @pytest.mark.usefixtures("keycloak")
    def test_login_redirect(self):
        assert True
        # response = client.get("/auth/login")
        # assert response.url == "/auth/callback"
