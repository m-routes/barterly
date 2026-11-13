from rest_framework.throttling import UserRateThrottle


class KycStartThrottle(UserRateThrottle):
    """Each started ID check costs money at the provider."""

    scope = "kyc_start"
