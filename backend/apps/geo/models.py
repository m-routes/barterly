"""Every geocoding answer we ever got, so the same address is never looked up twice."""

from django.db import models


class GeocodeResult(models.Model):
    provider = models.CharField(max_length=30)
    query = models.CharField(max_length=300, help_text="Normalized: lower case, single spaces.")
    found = models.BooleanField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    display_name = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    postcode = models.CharField(max_length=20, blank=True)
    fetched_at = models.DateTimeField()
    hits = models.PositiveIntegerField(default=0, help_text="Times served from the cache.")

    class Meta:
        ordering = ["-fetched_at"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "query"], name="geo_result_once_per_query"),
            models.CheckConstraint(
                condition=models.Q(found=False)
                | models.Q(latitude__isnull=False, longitude__isnull=False),
                name="geo_result_found_has_point",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}: {self.query} ({'found' if self.found else 'not found'})"
