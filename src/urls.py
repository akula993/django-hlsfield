from django.urls import path, include

# Простые URL patterns для базовой функциональности
app_name = 'hlsfield'

urlpatterns = [
    # Базовые endpoints можно добавить позже
]

# Опционально включить views если они есть
try:
    from . import views
    if hasattr(views, 'urlpatterns'):
        urlpatterns.extend(views.urlpatterns)
except ImportError:
    pass
