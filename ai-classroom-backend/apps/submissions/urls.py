from django.urls import path

from .views import (
    SubmissionCreateView,
    SubmissionDetailView,
    SubmissionRegradeView,
    SubmissionTeacherGradeView,
)

urlpatterns = [
    path("assignments/<int:assignment_id>/submissions/", SubmissionCreateView.as_view(), name="submission-create"),
    path("submissions/<int:pk>/", SubmissionDetailView.as_view(), name="submission-detail"),
    path("submissions/<int:submission_id>/regrade/", SubmissionRegradeView.as_view(), name="submission-regrade"),
    path("submissions/<int:submission_id>/teacher-grade/", SubmissionTeacherGradeView.as_view(), name="submission-teacher-grade"),
]
