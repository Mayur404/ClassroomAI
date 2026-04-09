from django.contrib.auth import authenticate
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


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=UserRole.choices)
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_email(self, value):
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Email cannot be empty.")
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate_name(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Name cannot be empty.")
        return normalized

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            name=validated_data["name"],
            role=validated_data["role"],
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password", "")
        user = authenticate(request=self.context.get("request"), username=email, password=password)
        if not user:
            # Fallback for legacy users whose emails were stored with mixed casing.
            legacy_user = User.objects.filter(email__iexact=email).first()
            if legacy_user and legacy_user.check_password(password):
                user = legacy_user
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        attrs["user"] = user
        return attrs
