from django.urls import path
from .views import ChatbotView, ChatHistoryView

urlpatterns = [
    path("",        ChatbotView.as_view(),     name="chatbot"),
    path("history/", ChatHistoryView.as_view(), name="chatbot-history"),
]