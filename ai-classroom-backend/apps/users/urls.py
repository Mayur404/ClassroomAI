from django.urls import path

from .views import DemoLoginView, MeView

urlpatterns = [
    path("demo-login/", DemoLoginView.as_view(), name="demo-login"),
    path("me/", MeView.as_view(), name="me"),
]
