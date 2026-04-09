from django.urls import path

from .views import AssignmentDetailView, AssignmentGenerateView, AssignmentListView, AssignmentPublishView
from .views import AssignmentManualCreateView

urlpatterns = [
    path("courses/<int:course_id>/assignments/", AssignmentListView.as_view(), name="assignment-list"),
    path("courses/<int:course_id>/assignments/generate/", AssignmentGenerateView.as_view(), name="assignment-generate"),
    path("assignments/<int:pk>/", AssignmentDetailView.as_view(), name="assignment-detail"),
    path("courses/<int:course_id>/assignments/manual/", AssignmentManualCreateView.as_view(), name="assignment-manual"),
    path("assignments/<int:assignment_id>/publish/", AssignmentPublishView.as_view(), name="assignment-publish"),
]
