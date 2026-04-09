from django.urls import path

from .views import (
    CourseQuizAlertListView,
    PracticeQuizGenerateView,
    QuizAnalyticsView,
    QuizAttemptAnswerUpsertView,
    QuizAttemptStartView,
    QuizAttemptSubmitView,
    QuizDetailView,
    QuizGenerateView,
    QuizListView,
    QuizPublishView,
    QuizQuestionCreateView,
    QuizQuestionDetailView,
)


urlpatterns = [
    path("courses/<int:course_id>/quizzes/", QuizListView.as_view(), name="quiz-list"),
    path("courses/<int:course_id>/sessions/<int:session_id>/quizzes/generate/", QuizGenerateView.as_view(), name="quiz-generate"),
    path(
        "courses/<int:course_id>/sessions/<int:session_id>/practice-quizzes/generate/",
        PracticeQuizGenerateView.as_view(),
        name="practice-quiz-generate",
    ),
    path("courses/<int:course_id>/quiz-alerts/", CourseQuizAlertListView.as_view(), name="quiz-alerts"),
    path("quizzes/<int:quiz_id>/", QuizDetailView.as_view(), name="quiz-detail"),
    path("quizzes/<int:quiz_id>/publish/", QuizPublishView.as_view(), name="quiz-publish"),
    path("quizzes/<int:quiz_id>/questions/", QuizQuestionCreateView.as_view(), name="quiz-question-create"),
    path("questions/<int:question_id>/", QuizQuestionDetailView.as_view(), name="quiz-question-detail"),
    path("quizzes/<int:quiz_id>/attempts/start/", QuizAttemptStartView.as_view(), name="quiz-attempt-start"),
    path("attempts/<int:attempt_id>/answers/", QuizAttemptAnswerUpsertView.as_view(), name="quiz-attempt-answers"),
    path("attempts/<int:attempt_id>/submit/", QuizAttemptSubmitView.as_view(), name="quiz-attempt-submit"),
    path("quizzes/<int:quiz_id>/analytics/", QuizAnalyticsView.as_view(), name="quiz-analytics"),
]
