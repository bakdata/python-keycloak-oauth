from typing import Any
import fastapi
from fastapi.encoders import jsonable_encoder
import pydantic
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from authlib.jose import JWTClaims, JsonWebToken, JsonWebKey

from starlette import status
from starlette.datastructures import URL
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse


class User(pydantic.BaseModel):
    name: str
    email: pydantic.EmailStr | None
    roles: list[str]
    """Complete access token. Required for token propagation."""
    token: str


class KeycloakOAuth2:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        server_metadata_url: str,
        client_kwargs: dict[str, Any],
        base_url: str = "/",
        logout_target: str = "/",
    ) -> None:
        self._base_url = base_url
        self._logout_page = logout_target
        oauth = OAuth()
        oauth.register(
            name="keycloak",
            # client_id and client_secret are created in keycloak
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=server_metadata_url,
            client_kwargs=client_kwargs,
        )
        assert isinstance(oauth.keycloak, StarletteOAuth2App)
        self.keycloak = oauth.keycloak

    def setup_fastapi_routes(self) -> None:
        self.router = fastapi.APIRouter()
        self.router.add_api_route("/login", self.login_page)
        self.router.add_api_route("/callback", self.auth)
        self.router.add_api_route("/logout", self.logout)

    async def login_page(
        self, request: Request, redirect_target: str | None = None
    ) -> RedirectResponse:
        redirect_uri = (
            URL(redirect_target)
            if redirect_target
            else request.url_for("auth")  # /auth/callback
        )
        if next := request.query_params.get("next"):
            redirect_uri = redirect_uri.include_query_params(next=next)
        return await self.keycloak.authorize_redirect(request, redirect_uri)

    async def auth(self, request: Request) -> RedirectResponse:
        token = await self.keycloak.authorize_access_token(request)
        claims = await self.parse_claims(token)
        user = User(
            name=claims["preferred_username"],
            email=claims.get("email"),
            roles=claims["realm_access"]["roles"],
            token=token["access_token"],
        )
        request.session["user"] = jsonable_encoder(user)
        redirect_uri = request.query_params.get("next") or self._base_url
        return RedirectResponse(redirect_uri)

    async def parse_claims(self, token: dict[str, Any]) -> JWTClaims:
        metadata = await self.keycloak.load_server_metadata()
        alg_values = metadata.get("id_token_signing_alg_values_supported")
        if not alg_values:
            alg_values = ["RS256"]
        jwt = JsonWebToken(alg_values)
        jwk_set = await self.keycloak.fetch_jwk_set()
        claims = jwt.decode(
            token["access_token"],
            key=JsonWebKey.import_key_set(jwk_set),
        )
        return claims

    async def logout(self, request: Request) -> RedirectResponse:
        request.session.pop("user", None)
        return RedirectResponse(self._logout_page)

    @staticmethod
    async def get_user(request: Request) -> User:
        if (user := request.session.get("user")) is not None:
            return User.model_validate(user)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
