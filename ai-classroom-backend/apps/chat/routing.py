from django.urls import re_path

from .consumers import VoiceChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/voice-chat/(?P<course_id>\d+)/$", VoiceChatConsumer.as_asgi()),
]
