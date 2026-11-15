from rest_framework.throttling import UserRateThrottle


class ChatSendThrottle(UserRateThrottle):
    """Messages a person may send, across all their conversations."""

    scope = "chat_send"
