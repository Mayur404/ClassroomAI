from django.urls import path

from .views import (
    CourseGlobalSearchView,
    CoursePeopleView,
    CourseDetailView,
    CourseListCreateView,
    EnrollmentCreateView,
    MaterialDeleteView,
    RotateInviteCodeView,
    ScheduleApproveView,
    ScheduleCompleteView,
    ScheduleGenerateView,
    StudentDashboardView,
    StudentNotebookDetailView,
    StudentNotebookListCreateView,
    SyllabusUploadView,
    TeacherDashboardView,
)

urlpatterns = [
    path("courses/", CourseListCreateView.as_view(), name="course-list"),
    path("courses/<int:pk>/", CourseDetailView.as_view(), name="course-detail"),
    path("courses/<int:course_id>/syllabus/", SyllabusUploadView.as_view(), name="course-syllabus"),
    path("materials/<int:material_id>/delete/", MaterialDeleteView.as_view(), name="material-delete"),
    path("courses/<int:course_id>/schedule/generate/", ScheduleGenerateView.as_view(), name="schedule-generate"),
    path("courses/<int:course_id>/schedule/approve/", ScheduleApproveView.as_view(), name="schedule-approve"),
    path("schedule/<int:schedule_id>/complete/", ScheduleCompleteView.as_view(), name="schedule-complete"),
    path("enrollments/", EnrollmentCreateView.as_view(), name="enrollment-create"),
    path("teacher/dashboard/", TeacherDashboardView.as_view(), name="teacher-dashboard"),
    path("student/dashboard/", StudentDashboardView.as_view(), name="student-dashboard"),
    path("courses/<int:course_id>/search/", CourseGlobalSearchView.as_view(), name="course-search"),
    path("courses/<int:course_id>/people/", CoursePeopleView.as_view(), name="course-people"),
    path("courses/<int:course_id>/invite-code/rotate/", RotateInviteCodeView.as_view(), name="course-invite-rotate"),
    path("courses/<int:course_id>/notebooks/", StudentNotebookListCreateView.as_view(), name="notebook-list-create"),
    path("notebooks/<int:pk>/", StudentNotebookDetailView.as_view(), name="notebook-detail"),
]
