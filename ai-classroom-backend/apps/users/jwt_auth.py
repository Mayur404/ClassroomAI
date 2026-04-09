from rest_framework import authentication
from rest_framework import exceptions

from apps.users.models import User
from apps.users.jwt_utils import decode_token


class JWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token = parts[1].strip()
        if not token:
            return None

        try:
            payload = decode_token(token)
        except Exception as exc:
            raise exceptions.AuthenticationFailed(f"Invalid token: {exc}") from exc

        if payload.get("type") != "access":
            raise exceptions.AuthenticationFailed("Invalid access token type.")

        user_id = payload.get("sub")
        if not user_id:
            raise exceptions.AuthenticationFailed("Token subject missing.")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("User not found.") from exc

        return (user, token)
