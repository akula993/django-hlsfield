"""
URL patterns for django-hlsfield
"""

from django.urls import path

app_name = 'hlsfield'

urlpatterns = [
    # Basic URL patterns for hlsfield
    # Add specific endpoints as needed
]

# Optionally include views if they exist
try:
    from . import views
    # Add view URLs here when views are implemented
except ImportError:
    pass
