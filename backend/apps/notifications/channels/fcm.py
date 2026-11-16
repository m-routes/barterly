"""Push through Firebase Cloud Messaging (firebase-admin, the API's own credentials).

Devices register FCM registration tokens (mobile/lib/src/notifications/push.dart).
firebase-admin and firebase_messaging now prefer Firebase Installation IDs (`fid`)
and warn that `token` is deprecated; it still works. Move both sides together.

The payload carries the deep links: `data.path` (the app's route, opened by the mobile
app when the push is tapped), `data.url` and `webpush.fcm_options.link` (the web
console page), and `data.notification_id` (marked read when opened).
"""

from apps.notifications.channels.base import (
    Message,
    PermanentFailure,
    Result,
    TemporaryFailure,
)


def messaging_app():
    """A firebase-admin app on the API's own credentials (Application Default
    Credentials: the Cloud Run service account, which needs FCM send permission)."""
    import firebase_admin
    from django.conf import settings

    name = "barterly-messaging"
    try:
        return firebase_admin.get_app(name)
    except ValueError:
        options = (
            {"projectId": settings.FIREBASE_PROJECT_ID} if settings.FIREBASE_PROJECT_ID else None
        )
        return firebase_admin.initialize_app(options=options, name=name)


def build(message: Message, token: str):
    from firebase_admin import messaging

    return messaging.Message(
        token=token,
        notification=messaging.Notification(title=message.title, body=message.body),
        data={
            "notification_id": message.notification_id,
            "kind": message.kind,
            "path": message.app_path,
            "url": message.web_url,
        },
        android=messaging.AndroidConfig(priority="high" if message.urgent else "normal"),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10" if message.urgent else "5"},
        ),
        webpush=messaging.WebpushConfig(
            fcm_options=messaging.WebpushFCMOptions(link=message.web_url)
            if message.web_url
            else None,
        ),
    )


class FcmPushProvider:
    name = "fcm"

    def send(self, message: Message) -> Result:
        from firebase_admin import exceptions, messaging

        if not message.to:
            raise PermanentFailure("No device to send to.")
        sent, dead, temporary = [], [], []
        for token in message.to:
            try:
                sent.append(messaging.send(build(message, token), app=messaging_app()))
            except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
                dead.append(token)
            except exceptions.InvalidArgumentError:
                dead.append(token)
            except exceptions.FirebaseError as exc:
                temporary.append(str(exc))
        if sent:
            return Result(provider=self.name, reference=sent[0], dead_tokens=tuple(dead))
        if temporary:
            raise TemporaryFailure("; ".join(temporary))
        raise PermanentFailure("Every device token was rejected.")
