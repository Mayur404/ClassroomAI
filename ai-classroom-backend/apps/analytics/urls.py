from django.urls import path

from .views import CourseAnalyticsView

urlpatterns = [
    path("courses/<int:course_id>/analytics/", CourseAnalyticsView.as_view(), name="course-analytics"),
]
