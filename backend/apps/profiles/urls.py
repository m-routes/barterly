from django.urls import path

from apps.profiles.views import MyTalentProfileView, MyVendorProfileView, SkillListView

app_name = "profiles"

urlpatterns = [
    path("profiles/vendor/me/", MyVendorProfileView.as_view(), name="vendor-me"),
    path("profiles/talent/me/", MyTalentProfileView.as_view(), name="talent-me"),
    path("profiles/skills/", SkillListView.as_view(), name="skills"),
]
