"""Fixed choice lists for profiles."""

from django.db import models


class BusinessType(models.TextChoices):
    HOSTEL = "hostel", "Hostel"
    HOMESTAY = "homestay", "Homestay"
    GUESTHOUSE = "guesthouse", "Guesthouse"
    HOTEL = "hotel", "Hotel"
    RESORT = "resort", "Resort"
    CAFE = "cafe", "Café"
    RESTAURANT = "restaurant", "Restaurant"
    CAMP = "camp", "Camp"
    FARM = "farm", "Farm stay"
    TOUR_OPERATOR = "tour_operator", "Tour operator"
    COWORKING = "coworking", "Co-working / co-living"
    OTHER = "other", "Other"


class TalentType(models.TextChoices):
    ARTIST = "artist", "Artist / muralist"
    PHOTO_VIDEO = "photo_video", "Photographer / videographer"
    CONTENT_CREATOR = "content_creator", "Content creator / social media"
    MUSICIAN = "musician", "Musician / performer"
    WELLNESS = "wellness", "Yoga / wellness"
    CULINARY = "culinary", "Chef / barista"
    HOSPITALITY = "hospitality", "Hospitality / front desk"
    TEACHER = "teacher", "Teacher / workshop host"
    TECH = "tech", "Tech / design"
    OUTDOOR = "outdoor", "Outdoor / trek guide"
    OTHER = "other", "Other"


INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # Union territories
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh",
    "Lakshadweep", "Puducherry",
]  # fmt: skip
STATE_CHOICES = [(name, name) for name in INDIAN_STATES]

# ISO 639 codes: Indian languages first, then those travellers commonly speak.
LANGUAGES = {
    "as": "Assamese", "bn": "Bengali", "en": "English", "gu": "Gujarati", "hi": "Hindi",
    "kn": "Kannada", "kok": "Konkani", "ml": "Malayalam", "mr": "Marathi", "ne": "Nepali",
    "or": "Odia", "pa": "Punjabi", "ta": "Tamil", "te": "Telugu", "ur": "Urdu",
    "ar": "Arabic", "de": "German", "es": "Spanish", "fr": "French", "he": "Hebrew",
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "nl": "Dutch", "pt": "Portuguese",
    "ru": "Russian", "zh": "Chinese",
}  # fmt: skip
MAX_LANGUAGES = 10
MAX_SKILLS = 15
MIN_AGE_YEARS = 18
