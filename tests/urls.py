from django.urls import path, include

urlpatterns = [
    path('admin/', include('django.contrib.admin.urls')),
    path('hlsfield/', include('hlsfield.urls')),
]
