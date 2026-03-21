from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import DemoLoginSerializer, UserSerializer


class DemoLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = DemoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, _ = User.objects.get_or_create(
            email=serializer.validated_data["email"],
            defaults={
                "name": serializer.validated_data["name"],
                "role": serializer.validated_data["role"],
            },
        )
        user.name = serializer.validated_data["name"]
        user.role = serializer.validated_data["role"]
        user.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data}, status=status.HTTP_200_OK)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)
