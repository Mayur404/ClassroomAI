from django.urls import path

from .views import SubmissionCreateView, SubmissionDetailView, SubmissionPrecheckView, SubmissionRegradeView

urlpatterns = [
    path("assignments/<int:assignment_id>/submissions/", SubmissionCreateView.as_view(), name="submission-create"),
    path("assignments/<int:assignment_id>/precheck/", SubmissionPrecheckView.as_view(), name="submission-precheck"),
    path("submissions/<int:pk>/", SubmissionDetailView.as_view(), name="submission-detail"),
    path("submissions/<int:submission_id>/regrade/", SubmissionRegradeView.as_view(), name="submission-regrade"),
]
