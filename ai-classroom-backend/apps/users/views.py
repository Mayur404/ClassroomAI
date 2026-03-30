from django.utils import timezone
from django.conf import settings
from rest_framework import permissions, status, exceptions
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import DemoLoginSerializer, UserSerializer


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
        
        email = serializer.validated_data["email"]
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
        return Response({"token": token.key, "user": UserSerializer(user).data}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
