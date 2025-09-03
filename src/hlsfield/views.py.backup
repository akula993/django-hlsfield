# src/hlsfield/views.py

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.apps import apps
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
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
                            # Извлекаем количество готовых качеств из статуса
                            import re
                            match = re.search(r'(\d+)_qualities', processing_status)
                            if match:
                                status_data['qualities_ready'] = int(match.group(1))
                    elif processing_status == 'preview_ready':
                        status_data['status'] = 'preview_ready'
                        status_data['qualities_ready'] = 1

            # Добавляем URL-ы если они готовы
            if hasattr(field_file, 'master_url') and field_file.master_url():
                status_data['hls_url'] = field_file.master_url()

            if hasattr(field_file, 'dash_url') and field_file.dash_url():
                status_data['dash_url'] = field_file.dash_url()

            if hasattr(field_file, 'preview_url') and field_file.preview_url():
                status_data['preview_url'] = field_file.preview_url()

            # Прогресс обработки (примерная оценка)
            if status_data['status'] == 'ready':
                status_data['processing_progress'] = 100
            elif status_data['status'] == 'preview_ready':
                status_data['processing_progress'] = 30
            else:
                # Оцениваем прогресс по времени с момента создания
                if hasattr(instance, 'created_at'):
                    time_elapsed = (timezone.now() - instance.created_at).total_seconds()
                    # Примерно 5 минут на полную обработку
                    estimated_total = 300
                    progress = min(90, (time_elapsed / estimated_total) * 100)
                    status_data['processing_progress'] = int(progress)

            return JsonResponse(status_data)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class VideoAnalyticsView(View):
    """API для сбора аналитики воспроизведения"""

    def post(self, request):
        try:
            data = json.loads(request.body)

            # Сохраняем событие аналитики
            VideoEvent.objects.create(
                video_id=data.get('video_id'),
                session_id=data.get('session_id', 'anonymous'),
                event_type=data.get('type'),
                timestamp=timezone.now(),
                current_time=data.get('currentTime', 0),
                quality=data.get('quality'),
                format=data.get('format'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                ip_address=self._get_client_ip(request),
                additional_data=data
            )

            return JsonResponse({'status': 'ok'})

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)

    def _get_client_ip(self, request):
        """Получает IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class VideoStatsView(View):
    """API для получения статистики по видео"""

    def get(self, request, video_id):
        try:
            # Основная статистика
            stats = {
                'total_views': 0,
                'unique_viewers': 0,
                'avg_watch_time': 0,
                'completion_rate': 0,
                'quality_distribution': {},
                'format_distribution': {},
                'geographic_distribution': {},
                'device_distribution': {},
                'hourly_views': [],
                'buffer_events': 0,
                'errors': 0
            }

            # Получаем события за последние 30 дней
            thirty_days_ago = timezone.now() - timedelta(days=30)
            events = VideoEvent.objects.filter(
                video_id=video_id,
                timestamp__gte=thirty_days_ago
            )

            if not events.exists():
                return JsonResponse(stats)

            # Подсчитываем основные метрики
            play_events = events.filter(event_type='play')
            stats['total_views'] = play_events.count()
            stats['unique_viewers'] = events.values('session_id').distinct().count()

            # Среднее время просмотра
            end_events = events.filter(event_type__in=['ended', 'pause']).exclude(current_time=0)
            if end_events.exists():
                stats['avg_watch_time'] = end_events.aggregate(
                    avg_time=Avg('current_time')
                )['avg_time'] or 0

            # Процент завершения
            ended_events = events.filter(event_type='ended').count()
            if stats['total_views'] > 0:
                stats['completion_rate'] = (ended_events / stats['total_views']) * 100

            # Распределение по качеству
            quality_stats = events.exclude(quality__isnull=True).values('quality').annotate(
                count=Count('id')
            )
            stats['quality_distribution'] = {
                item['quality']: item['count'] for item in quality_stats
            }

            # Распределение по формату
            format_stats = events.exclude(format__isnull=True).values('format').annotate(
                count=Count('id')
            )
            stats['format_distribution'] = {
                item['format']: item['count'] for item in format_stats
            }

            # События буферизации и ошибки
            stats['buffer_events'] = events.filter(event_type='buffer_start').count()
            stats['errors'] = events.filter(event_type='error').count()

            # Почасовая статистика за последние 24 часа
            twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
            hourly_events = events.filter(
                timestamp__gte=twenty_four_hours_ago,
                event_type='play'
            ).extra(
                select={'hour': "DATE_FORMAT(timestamp, '%%H')"}
            ).values('hour').annotate(count=Count('id')).order_by('hour')

            stats['hourly_views'] = [
                {'hour': int(item['hour']), 'views': item['count']}
                for item in hourly_events
            ]

            return JsonResponse(stats)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)


class BatchVideoOperationsView(View):
    """API для массовых операций с видео"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            operation = data.get('operation')
            video_ids = data.get('video_ids', [])
            model_label = data.get('model_label')
            field_name = data.get('field_name')

            if operation == 'optimize':
                from .progressive_tasks import batch_optimize_videos
                result = batch_optimize_videos.delay(
                    model_label, video_ids, field_name,
                    target_qualities=data.get('target_qualities', 3)
                )
                return JsonResponse({
                    'status': 'queued',
                    'task_id': result.id,
                    'message': f'Optimization queued for {len(video_ids)} videos'
                })

            elif operation == 'create_previews':
                from .progressive_tasks import batch_create_previews
                result = batch_create_previews.delay(model_label, video_ids, field_name)
                return JsonResponse({
                    'status': 'queued',
                    'task_id': result.id,
                    'message': f'Preview creation queued for {len(video_ids)} videos'
                })

            elif operation == 'health_check':
                from .progressive_tasks import health_check_videos
                result = health_check_videos.delay(model_label, field_name)
                return JsonResponse({
                    'status': 'queued',
                    'task_id': result.id,
                    'message': 'Health check initiated'
                })

            else:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Unknown operation: {operation}'
                }, status=400)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)


# Модель для хранения событий аналитики
from django.db import models


class VideoEvent(models.Model):
    """Модель для хранения событий воспроизведения видео"""

    EVENT_TYPES = [
        ('play', 'Play'),
        ('pause', 'Pause'),
        ('ended', 'Ended'),
        ('buffer_start', 'Buffer Start'),
        ('buffer_end', 'Buffer End'),
        ('quality_change', 'Quality Change'),
        ('error', 'Error'),
        ('seek', 'Seek'),
    ]

    video_id = models.CharField(max_length=255, db_index=True)
    session_id = models.CharField(max_length=255, db_index=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    current_time = models.FloatField(default=0)  # Время в секундах
    quality = models.CharField(max_length=20, null=True, blank=True)
    format = models.CharField(max_length=10, null=True, blank=True)  # hls/dash/mp4
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    additional_data = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'hlsfield'
        indexes = [
            models.Index(fields=['video_id', 'timestamp']),
            models.Index(fields=['session_id', 'timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.video_id} - {self.event_type} at {self.current_time}s"


# URL patterns
from django.urls import path

app_name = 'hlsfield'

urlpatterns = [
    path('api/video-status/<str:model_label>/<str:pk>/<str:field_name>/',
         VideoStatusView.as_view(), name='video_status'),

    path('api/video-analytics/',
         VideoAnalyticsView.as_view(), name='video_analytics'),

    path('api/video-stats/<str:video_id>/',
         VideoStatsView.as_view(), name='video_stats'),

    path('api/batch-operations/',
         BatchVideoOperationsView.as_view(), name='batch_operations'),
]

# Django Admin для аналитики
from django.contrib import admin


@admin.register(VideoEvent)
class VideoEventAdmin(admin.ModelAdmin):
    list_display = ['video_id', 'event_type', 'current_time', 'quality', 'format', 'timestamp']
    list_filter = ['event_type', 'format', 'quality', 'timestamp']
    search_fields = ['video_id', 'session_id']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'

    def get_queryset(self, request):
        # Показываем только события за последние 7 дней по умолчанию
        qs = super().get_queryset(request)
        if not request.GET.get('timestamp__gte'):
            seven_days_ago = timezone.now() - timedelta(days=7)
            qs = qs.filter(timestamp__gte=seven_days_ago)
        return qs


# Management команды для аналитики
# src/hlsfield/management/commands/video_analytics_report.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from hlsfield.models import VideoEvent
import json


class Command(BaseCommand):
    help = 'Generates video analytics report'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Number of days to analyze')
        parser.add_argument('--format', choices=['json', 'table'], default='table')
        parser.add_argument('--video-id', help='Analyze specific video only')

    def handle(self, *args, **options):
        days = options['days']
        output_format = options['format']
        video_id = options.get('video_id')

        start_date = timezone.now() - timedelta(days=days)

        # Базовый queryset
        events = VideoEvent.objects.filter(timestamp__gte=start_date)
        if video_id:
            events = events.filter(video_id=video_id)

        # Собираем статистику
        stats = {
            'period': f"Last {days} days",
            'total_events': events.count(),
            'unique_videos': events.values('video_id').distinct().count(),
            'unique_sessions': events.values('session_id').distinct().count(),
            'play_events': events.filter(event_type='play').count(),
            'completion_events': events.filter(event_type='ended').count(),
            'error_events': events.filter(event_type='error').count(),
            'buffer_events': events.filter(event_type='buffer_start').count(),
        }

        # Топ видео по просмотрам
        top_videos = events.filter(event_type='play').values('video_id').annotate(
            views=models.Count('id')
        ).order_by('-views')[:10]
        stats['top_videos'] = list(top_videos)

        # Распределение по качеству
        quality_dist = events.exclude(quality__isnull=True).values('quality').annotate(
            count=models.Count('id')
        ).order_by('-count')
        stats['quality_distribution'] = list(quality_dist)

        if output_format == 'json':
            self.stdout.write(json.dumps(stats, indent=2, default=str))
        else:
            self._print_table_report(stats)

    def _print_table_report(self, stats):
        self.stdout.write(self.style.SUCCESS(f"\n📊 Video Analytics Report - {stats['period']}\n"))
        self.stdout.write(f"Total Events: {stats['total_events']}")
        self.stdout.write(f"Unique Videos: {stats['unique_videos']}")
        self.stdout.write(f"Unique Sessions: {stats['unique_sessions']}")
        self.stdout.write(f"Play Events: {stats['play_events']}")
        self.stdout.write(f"Completion Events: {stats['completion_events']}")
        self.stdout.write(f"Error Events: {stats['error_events']}")
        self.stdout.write(f"Buffer Events: {stats['buffer_events']}")

        if stats.get('top_videos'):
            self.stdout.write(self.style.SUCCESS("\n🏆 Top Videos by Views:"))
            for i, video in enumerate(stats['top_videos'], 1):
                self.stdout.write(f"{i}. {video['video_id']}: {video['views']} views")

        if stats.get('quality_distribution'):
            self.stdout.write(self.style.SUCCESS("\n📺 Quality Distribution:"))
            for quality in stats['quality_distribution']:
                self.stdout.write(f"{quality['quality']}: {quality['count']} events")


# Middleware для автоматической аналитики
class VideoAnalyticsMiddleware:
    """Middleware для автоматического трекинга просмотров видео"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Трекаем загрузки страниц с видео
        if hasattr(request, 'resolver_match') and request.resolver_match:
            if 'video' in request.resolver_match.url_name.lower():
                self._track_page_view(request)

        return response

    def _track_page_view(self, request):
        """Записывает просмотр страницы с видео"""
        try:
            # Извлекаем ID видео из URL или параметров
            video_id = (request.resolver_match.kwargs.get('pk') or
                        request.GET.get('video_id'))

            if video_id:
                VideoEvent.objects.create(
                    video_id=str(video_id),
                    session_id=request.session.session_key or 'anonymous',
                    event_type='page_view',
                    timestamp=timezone.now(),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    ip_address=self._get_client_ip(request),
                    additional_data={'url': request.get_full_path()}
                )
        except Exception:
            # Не ломаем сайт из-за аналитики
            pass

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
