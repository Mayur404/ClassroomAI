from django.urls import path

from .views import (
    CourseDetailView,
    CourseListCreateView,
    EnrollmentCreateView,
    ScheduleApproveView,
    ScheduleCompleteView,
    ScheduleGenerateView,
    SyllabusUploadView,
    TeacherDashboardView,
)

urlpatterns = [
    path("courses/", CourseListCreateView.as_view(), name="course-list"),
    path("courses/<int:pk>/", CourseDetailView.as_view(), name="course-detail"),
    path("courses/<int:course_id>/syllabus/", SyllabusUploadView.as_view(), name="course-syllabus"),
    path("courses/<int:course_id>/schedule/generate/", ScheduleGenerateView.as_view(), name="schedule-generate"),
    path("courses/<int:course_id>/schedule/approve/", ScheduleApproveView.as_view(), name="schedule-approve"),
    path("schedule/<int:schedule_id>/complete/", ScheduleCompleteView.as_view(), name="schedule-complete"),
    path("enrollments/", EnrollmentCreateView.as_view(), name="enrollment-create"),
    path("teacher/dashboard/", TeacherDashboardView.as_view(), name="teacher-dashboard"),
]
