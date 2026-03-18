from base64 import urlsafe_b64encode

from app.schemas.auth import AuthUserRead


class AuthService:
    def login(self, *, email: str, password: str) -> tuple[str, str, AuthUserRead] | None:
        del password
        if email.strip().lower() != "demo@novu.local":
            return None
        user = AuthUserRead(
            id="usr_1",
            email="demo@novu.local",
            fullName="Demo Manager",
            role="manager",
            isActive=True,
            organizationId="org_1",
        )
        access_token = urlsafe_b64encode(f"access:{user.id}".encode()).decode()
        refresh_token = urlsafe_b64encode(f"refresh:{user.id}".encode()).decode()
        return access_token, refresh_token, user

    def me(self) -> AuthUserRead:
        return AuthUserRead(
            id="usr_1",
            email="demo@novu.local",
            fullName="Demo Manager",
            role="manager",
            isActive=True,
            organizationId="org_1",
        )
