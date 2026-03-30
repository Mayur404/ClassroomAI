from django.urls import path

from .views import CourseAnalyticsView, StudentAnalyticsView, TopicAnalyticsView, ErrorLogView

urlpatterns = [
    path("courses/<int:course_id>/analytics/", CourseAnalyticsView.as_view(), name="course-analytics"),
    path("students/<int:student_id>/analytics/", StudentAnalyticsView.as_view(), name="student-analytics"),
    path("topics/analytics/", TopicAnalyticsView.as_view(), name="topic-analytics"),
    path("errors/log", ErrorLogView.as_view(), name="error-log"),
]
