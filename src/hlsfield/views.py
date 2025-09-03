# Упрощенный views.py - только базовое API

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.apps import apps
from django.utils import timezone
from django.db import models
import json


@method_decorator(csrf_exempt, name='dispatch')
class VideoStatusView(View):
    """API для проверки статуса обработки видео"""

    def get(self, request, model_label, pk, field_name):
        try:
            Model = apps.get_model(model_label)
            instance = Model.objects.get(pk=pk)
            field_file = getattr(instance, field_name)

            status_data = {
                'status': 'processing',
                'qualities_ready': 0,
                'hls_url': None,
                'dash_url': None,
                'preview_url': None,
                'processing_progress': 0
            }

            # Проверяем статус обработки
            if hasattr(instance, 'processing_status'):
                processing_status = getattr(instance, 'processing_status')
                if processing_status:
                    if 'ready' in processing_status:
                        status_data['status'] = 'ready'
                        if 'qualities' in processing_status:
                            import re
                            match = re.search(r'(\d+)_qualities', processing_status)
                            if match:
                                status_data['qualities_ready'] = int(match.group(1))
                    elif processing_status == 'preview_ready':
                        status_data['status'] = 'preview_ready'
                        status_data['qualities_ready'] = 1

            # Добавляем URL-ы если готовы
            if hasattr(field_file, 'master_url'):
                try:
                    hls_url = field_file.master_url()
                    if hls_url:
                        status_data['hls_url'] = hls_url
                except:
                    pass

            if hasattr(field_file, 'dash_url'):
                try:
                    dash_url = field_file.dash_url()
                    if dash_url:
                        status_data['dash_url'] = dash_url
                except:
                    pass

            if hasattr(field_file, 'preview_url'):
                try:
                    preview_url = field_file.preview_url()
                    if preview_url:
                        status_data['preview_url'] = preview_url
                except:
                    pass

            # Простая оценка прогресса
            if status_data['status'] == 'ready':
                status_data['processing_progress'] = 100
            elif status_data['status'] == 'preview_ready':
                status_data['processing_progress'] = 30
            else:
                # Оценка по времени
                if hasattr(instance, 'created_at'):
                    time_elapsed = (timezone.now() - instance.created_at).total_seconds()
                    progress = min(90, (time_elapsed / 300) * 100)  # 5 минут = 100%
                    status_data['processing_progress'] = int(progress)

            return JsonResponse(status_data)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)


# Простая модель для базовой аналитики
class VideoEvent(models.Model):
    """Базовая модель для событий воспроизведения видео"""

    EVENT_TYPES = [
        ('play', 'Play'),
        ('pause', 'Pause'),
        ('ended', 'Ended'),
        ('error', 'Error'),
    ]

    video_id = models.CharField(max_length=255, db_index=True)
    session_id = models.CharField(max_length=255, db_index=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    current_time = models.FloatField(default=0)  # Время в секундах
    quality = models.CharField(max_length=20, null=True, blank=True)
    additional_data = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'hlsfield'
        indexes = [
            models.Index(fields=['video_id', 'timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.video_id} - {self.event_type} at {self.current_time}s"


@method_decorator(csrf_exempt, name='dispatch')
class VideoAnalyticsView(View):
    """Простое API для сбора аналитики"""

    def post(self, request):
        try:
            data = json.loads(request.body)

            # Сохраняем базовое событие
            VideoEvent.objects.create(
                video_id=data.get('video_id', ''),
                session_id=data.get('session_id', 'anonymous'),
                event_type=data.get('type', 'play'),
                timestamp=timezone.now(),
                current_time=data.get('currentTime', 0),
                quality=data.get('quality'),
                additional_data=data
            )

            return JsonResponse({'status': 'ok'})

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)


# URL patterns
from django.urls import path

app_name = 'hlsfield'

urlpatterns = [
    path('api/video-status/<str:model_label>/<str:pk>/<str:field_name>/',
         VideoStatusView.as_view(), name='video_status'),

    path('api/video-analytics/',
         VideoAnalyticsView.as_view(), name='video_analytics'),
]


# Django Admin (упрощенный)
from django.contrib import admin

@admin.register(VideoEvent)
class VideoEventAdmin(admin.ModelAdmin):
    list_display = ['video_id', 'event_type', 'current_time', 'quality', 'timestamp']
    list_filter = ['event_type', 'quality', 'timestamp']
    search_fields = ['video_id', 'session_id']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'

    def get_queryset(self, request):
        # Показываем только события за последние 7 дней
        qs = super().get_queryset(request)
        if not request.GET.get('timestamp__gte'):
            from datetime import timedelta
            seven_days_ago = timezone.now() - timedelta(days=7)
            qs = qs.filter(timestamp__gte=seven_days_ago)
        return qs
