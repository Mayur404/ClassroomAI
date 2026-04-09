from django.urls import path

from .views import DemoLoginView, LoginView, LogoutView, MeView, RegisterView, TokenRefreshView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("signup/", RegisterView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("signin/", LoginView.as_view(), name="signin"),
    path("demo-login/", DemoLoginView.as_view(), name="demo-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
]
