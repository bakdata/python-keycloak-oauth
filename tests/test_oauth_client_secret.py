import json
from pathlib import Path
from typing import Annotated, Generator
from fastapi import Depends, FastAPI, Request, status
import httpx
from starlette.middleware.sessions import SessionMiddleware
from keycloak import KeycloakAdmin
import pytest
from testcontainers.core.waiting_utils import wait_for_logs
from keycloak_oauth import KeycloakOAuth2, User
from testcontainers.keycloak import KeycloakContainer
from fastapi.testclient import TestClient
from twill import browser
from twill.commands import form_value


class TestKeycloakOAuth2ClientSecret:
    RESOURCES_PATH = Path(__file__).parent.absolute() / "resources/keycloak"

    @pytest.fixture(scope="class")
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
        container.with_bind_ports(container.port, container.port).start()
        wait_for_logs(container, "Running the server in development mode.")
        keycloak = container.get_client()

        assert keycloak.connection.base_url == container.get_base_api_url() + "/"
        keycloak.import_realm(
            json.loads(
                Path(self.RESOURCES_PATH / "realm_client_secret.json").read_bytes()
            )
        )
        keycloak.change_current_realm("bakdata")

        user_id = keycloak.create_user({"username": keycloak.connection.username})
        keycloak.set_user_password(
            user_id, keycloak.connection.password, temporary=False
        )
        keycloak.enable_user(user_id)

        yield keycloak

        container.stop()

    @pytest.fixture()
    def app(self) -> FastAPI:
        return FastAPI()

    @pytest.fixture()
    def client(self, app: FastAPI, keycloak: KeycloakAdmin) -> TestClient:
        keycloak_oauth = KeycloakOAuth2(
            client_id="test-client",
            client_secret="ZPSWENNxF0z3rT8xQORol9NpXQFJxiZf",
            server_metadata_url=f"{keycloak.connection.base_url}/realms/bakdata/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
        )
        keycloak_oauth.setup_fastapi_routes()
        app.include_router(keycloak_oauth.router, prefix="/auth")
        app.add_middleware(SessionMiddleware, secret_key="!secret")

        @app.get("/")
        def root(
            request: Request, user: Annotated[User, Depends(KeycloakOAuth2.get_user)]
        ) -> str:
            return f"Hello {user.name}"

        @app.get("/foo")
        def foo(
            request: Request, user: Annotated[User, Depends(KeycloakOAuth2.get_user)]
        ) -> str:
            return "foo"

        @app.get("/bar")
        def bar(
            request: Request, user: Annotated[User, Depends(KeycloakOAuth2.get_user)]
        ) -> str:
            return "bar"

        return TestClient(app)

    def test_keycloak_setup(self, keycloak: KeycloakAdmin):
        assert keycloak.connection.realm_name == "bakdata"

    @pytest.mark.parametrize("endpoint", ["/", "/foo", "/bar"])
    def test_protected_endpoint(self, client: TestClient, endpoint: str):
        response = client.get(endpoint)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize(
        "query_params",
        [
            None,
            httpx.QueryParams({"next": "/foo"}),
            httpx.QueryParams({"next": "/bar", "unrelated": "should be hidden"}),
        ],
    )
    def test_login_redirect(
        self,
        client: TestClient,
        keycloak: KeycloakAdmin,
        query_params: httpx.QueryParams | None,
    ):
        response = client.get("/auth/login", params=query_params)
        keycloak_base_url = httpx.URL(keycloak.connection.base_url)
        assert response.url.host == keycloak_base_url.host
        assert response.url.port == keycloak_base_url.port
        assert response.url.path == "/realms/bakdata/protocol/openid-connect/auth"
        assert response.url.params["client_id"] == "test-client"
        redirect_uri = httpx.URL(response.url.params["redirect_uri"])
        assert redirect_uri.host == client.base_url.host
        assert redirect_uri.path == "/auth/callback"
        if query_params:
            assert set(redirect_uri.params.keys()) == {"next"}
            assert redirect_uri.params["next"] == query_params["next"]
        else:
            assert not redirect_uri.params

    def test_logout_redirect(self, client: TestClient):
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert response.headers["location"] == "/"

    def test_auth_flow(self, client: TestClient, keycloak: KeycloakAdmin):
        # try accessing protected endpoint
        response = client.get("/", follow_redirects=False)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # let's login, should redirect to Keycloak login page
        response = client.get("/auth/login", follow_redirects=False)
        assert response.is_redirect
        redirect_target = response.headers["location"]
        assert "/realms/bakdata/protocol/openid-connect/auth" in redirect_target

        # open Keycloak login form in browser and login
        browser.go(redirect_target)
        assert browser.title == "Sign in to bakdata"
        browser.show_forms()
        assert keycloak.connection.username  # HACK: fix wrong type annotation
        assert keycloak.connection.password
        form_value("1", "username", keycloak.connection.username)
        form_value("1", "password", keycloak.connection.password)
        with pytest.raises(httpx.ConnectError) as exc:
            browser.submit("0")
        assert exc.value.request.url.host == client.base_url.host
        assert exc.value.request.url.path == "/auth/callback"

        # first check the redirect
        response = client.get(exc.value.request.url, follow_redirects=False)
        assert response.is_redirect
        assert response.headers["location"] == "/"

        # now follow the redirect
        response = client.get(response.headers["location"])
        assert response.is_success
        assert response.read() == b'"Hello test"'

        # logout user
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.is_redirect

        # check that endpoint is inaccessible again
        response = client.get("/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
