from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/", include("apps.courses.urls")),
    path("api/", include("apps.assignments.urls")),
    path("api/", include("apps.submissions.urls")),
    path("api/", include("apps.chat.urls")),
    path("api/", include("apps.analytics.urls")),
    path("api/", include("apps.ai_service.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
