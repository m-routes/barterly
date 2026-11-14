from rest_framework.throttling import UserRateThrottle


class UploadUrlThrottle(UserRateThrottle):
    scope = "media_upload"
