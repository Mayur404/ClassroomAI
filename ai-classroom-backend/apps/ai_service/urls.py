"""
URL patterns for AI service advanced features.
Routes for streaming, adaptive difficulty, conversations, and analytics.
"""

from django.urls import path

from .advanced_views import (
    AdaptiveDifficultyView,
    ConversationSummaryView,
    ConversationExportView,
    FeedbackAnalysisView,
    DashboardMetricsView,
    FlashcardReviewView,
    SarvamTranslateView,
    StudyToolsGenerateView,
    WeakTopicAnalysisView,
)

urlpatterns = [
    # Adaptive difficulty
    path(
        "courses/<int:course_id>/students/<int:student_id>/difficulty/",
        AdaptiveDifficultyView.as_view(),
        name="adaptive-difficulty"
    ),
    
    # Conversation summaries
    path(
        "conversations/<int:student_id>/courses/<int:course_id>/summary/",
        ConversationSummaryView.as_view(),
        name="conversation-summary"
    ),
    
    # Conversation export
    path(
        "conversations/<int:student_id>/courses/<int:course_id>/export/",
        ConversationExportView.as_view(),
        name="conversation-export"
    ),
    
    # Feedback analysis
    path(
        "courses/<int:course_id>/feedback-analysis/",
        FeedbackAnalysisView.as_view(),
        name="feedback-analysis"
    ),
    
    # Dashboard
    path(
        "dashboard/metrics/",
        DashboardMetricsView.as_view(),
        name="dashboard-metrics"
    ),
    path(
        "courses/<int:course_id>/study-tools/",
        StudyToolsGenerateView.as_view(),
        name="study-tools-generate",
    ),
    path(
        "flashcards/<int:flashcard_id>/review/",
        FlashcardReviewView.as_view(),
        name="flashcard-review",
    ),
    path(
        "courses/<int:course_id>/weak-topics/",
        WeakTopicAnalysisView.as_view(),
        name="weak-topics",
    ),
    path(
        "sarvam/translate/",
        SarvamTranslateView.as_view(),
        name="sarvam-translate",
    ),
]
