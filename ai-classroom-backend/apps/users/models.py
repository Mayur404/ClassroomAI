from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "TEACHER")
        extra_fields.setdefault("name", "Admin")

        return self.create_user(email, password, **extra_fields)


class UserRole(models.TextChoices):
    TEACHER = "TEACHER", "Teacher"
    STUDENT = "STUDENT", "Student"


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=UserRole.choices)
    google_id = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name", "role"]

    def clean(self) -> None:
        super().clean()

    def __str__(self) -> str:
        return f"{self.name} ({self.email})"
