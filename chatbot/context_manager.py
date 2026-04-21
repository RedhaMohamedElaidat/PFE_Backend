from .models import ChatMessage


def get_last_context(user):
    last_msg = ChatMessage.objects.filter(
        user=user,
        role="assistant"
    ).order_by("-created_at").first()

    if last_msg and last_msg.context:
        return last_msg.context

    return {}


def update_context(old_context, new_data):
    context = old_context.copy()
    context.update(new_data)
    return context