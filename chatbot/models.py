from django.db import models
from users.models import User


class ChatMessage(models.Model):

    ROLE_CHOICES = (
        ("user", "User"),
        ("assistant", "Assistant"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    message = models.TextField()
    context = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)