from django.urls import path

from .views import ChatAskView, ChatHistoryView, ChatFeedbackView, ChatStreamingView

urlpatterns = [
    path("courses/<int:course_id>/chat/", ChatHistoryView.as_view(), name="chat-history"),
    path("courses/<int:course_id>/chat/ask/", ChatAskView.as_view(), name="chat-ask"),
    path("courses/<int:course_id>/chat/stream/", ChatStreamingView.as_view(), name="chat-stream"),
    path("chat/<int:message_id>/feedback/", ChatFeedbackView.as_view(), name="chat-feedback"),
]
