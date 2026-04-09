from django.utils import timezone
from django.conf import settings
from rest_framework import permissions, status, exceptions
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import DemoLoginSerializer, LoginSerializer, RegisterSerializer, UserSerializer
from .jwt_utils import decode_token, issue_access_token, issue_refresh_token


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at"])
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "access_token": issue_access_token(user),
                "refresh_token": issue_refresh_token(user),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at"])
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "access_token": issue_access_token(user),
                "refresh_token": issue_refresh_token(user),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class DemoLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Security: Only allow demo login in debug/development mode
        if not settings.DEBUG:
            raise exceptions.PermissionDenied(
                "Demo login is only available in development mode. "
                "Please use standard authentication in production."
            )
            
        serializer = DemoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data["email"].strip().lower()
        name = serializer.validated_data["name"]
        role = serializer.validated_data["role"]
        
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "name": name,
                "role": role,
            },
        )
        
        if not created:
            user.name = name
            user.role = role
            
        user.last_login_at = timezone.now()
        user.save()
        
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "access_token": issue_access_token(user),
                "refresh_token": issue_refresh_token(user),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = str(request.data.get("refresh_token", "")).strip()
        if not refresh_token:
            return Response({"detail": "refresh_token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                return Response({"detail": "Invalid token type."}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.get(id=payload.get("sub"))
        except Exception as exc:
            return Response({"detail": f"Invalid refresh token: {exc}"}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "access_token": issue_access_token(user),
                "refresh_token": issue_refresh_token(user),
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"ok": True}, status=status.HTTP_200_OK)
