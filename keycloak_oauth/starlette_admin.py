from typing import Sequence
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route
from starlette_admin.auth import AdminUser, AuthProvider, login_not_required
from starlette_admin.base import BaseAdmin
from keycloak_oauth import KeycloakOAuth2, User


class KeycloakAuthProvider(AuthProvider):
    def __init__(
        self,
        keycloak: KeycloakOAuth2,
        login_path: str = "/login",
        logout_path: str = "/logout",
        allow_paths: Sequence[str] | None = None,
        allow_routes: Sequence[str] | None = None,
    ) -> None:
        self.keycloak = keycloak
        super().__init__(login_path, logout_path, allow_paths, allow_routes)

    async def is_authenticated(self, request: Request) -> bool:
        try:
            user = await self.keycloak.get_user(request)
            request.state.user = user
            return True
        except HTTPException:
            return False

    def get_admin_user(self, request: Request) -> AdminUser | None:
        user: User = request.state.user
        return AdminUser(
            username=user.name,
            # photo_url=user.avatar,  # TODO
        )

    async def render_login(
        self, request: Request, admin: BaseAdmin
    ) -> RedirectResponse:
        redirect_uri = request.url_for(admin.route_name + ":authorize_keycloak")
        return await self.keycloak.login_page(request, str(redirect_uri))

    async def render_logout(
        self, request: Request, admin: BaseAdmin
    ) -> RedirectResponse:
        return await self.keycloak.logout(request)

    @login_not_required
    async def handle_auth_callback(self, request: Request) -> RedirectResponse:
        return await self.keycloak.auth(request)

    @login_not_required
    async def public_keys(self, request: Request) -> JSONResponse:
        keys = await self.keycloak.public_keys(request)
        return JSONResponse(keys)

    def setup_admin(self, admin: BaseAdmin) -> None:
        super().setup_admin(admin)
        """add custom authentication callback route"""
        admin.routes.append(
            Route(
                "/auth/callback",
                self.handle_auth_callback,
                methods=["GET"],
                name="authorize_keycloak",
            )
        )
        admin.routes.append(
            Route(
                "/auth/certs",
                self.public_keys,
                methods=["GET"],
            )
        )
