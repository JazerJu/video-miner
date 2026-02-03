"""
WebSocket routing for the video app
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/realtime-transcription/$', consumers.RealtimeTranscriptionConsumer.as_asgi()),
]