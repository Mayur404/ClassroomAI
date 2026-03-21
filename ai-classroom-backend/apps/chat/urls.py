from django.urls import path

from .views import ChatAskView, ChatHistoryView

urlpatterns = [
    path("courses/<int:course_id>/chat/", ChatHistoryView.as_view(), name="chat-history"),
    path("courses/<int:course_id>/chat/ask/", ChatAskView.as_view(), name="chat-ask"),
]
