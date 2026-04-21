from django.contrib import admin
from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display  = ['user', 'role', 'short_message', 'created_at']
    list_filter   = ['role', 'created_at']
    search_fields = ['message', 'user__username', 'user__first_name']
    ordering      = ['-created_at']
    readonly_fields = ['created_at']

    def short_message(self, obj):
        return obj.message[:60] + "..." if len(obj.message) > 60 else obj.message
    short_message.short_description = "Message"