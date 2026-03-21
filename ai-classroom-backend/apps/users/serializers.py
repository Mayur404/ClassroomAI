from django.conf import settings
from rest_framework import serializers

from .models import User, UserRole


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "name", "role", "avatar_url")


class DemoLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=UserRole.choices)
