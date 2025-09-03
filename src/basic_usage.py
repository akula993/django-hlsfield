# examples/basic_usage.py
"""
🎬 Базовое использование django-hlsfield

Этот пример показывает как быстро начать работу с django-hlsfield
для создания адаптивного видео стриминга в Django приложении.
"""

# ============================================================================
# 1. НАСТРОЙКА МОДЕЛИ
# ============================================================================

from django.db import models
from hlsfield import VideoField, HLSVideoField, AdaptiveVideoField


class Movie(models.Model):
    """Пример модели фильма с адаптивным видео"""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Основное видео с автоматической генерацией HLS
    video = HLSVideoField(
        upload_to="movies/",
        # Поле для хранения пути к master.m3u8
        hls_playlist_field="hls_playlist",
        # Метаданные будут автоматически извлечены
        duration_field="duration",
        width_field="width",
        height_field="height",
        preview_field="preview_image"
    )

    # Поля для метаданных (заполняются автоматически)
    duration = models.DurationField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    preview_image = models.CharField(max_length=500, null=True, blank=True)
    hls_playlist = models.CharField(max_length=500, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class VideoTutorial(models.Model):
    """Пример для образовательного контента"""

    title = models.CharField(max_length=200)

    # Используем AdaptiveVideoField для максимальной совместимости
    video = AdaptiveVideoField(
        upload_to="tutorials/",
        hls_playlist_field="hls_url",
        dash_manifest_field="dash_url",
        # Настраиваем качества под образовательный контент
        ladder=[
            {"height": 360, "v_bitrate": 600, "a_bitrate": 96},   # Мобильные
            {"height": 720, "v_bitrate": 1800, "a_bitrate": 128}, # Десктоп
            {"height": 1080, "v_bitrate": 3500, "a_bitrate": 160}, # HD
        ]
    )

    hls_url = models.CharField(max_length=500, null=True, blank=True)
    dash_url = models.CharField(max_length=500, null=True, blank=True)


# ============================================================================
# 2. VIEWS ДЛЯ РАБОТЫ С ВИДЕО
# ============================================================================

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.generic import CreateView, DetailView
from django.contrib import messages


class MovieCreateView(CreateView):
    """View для загрузки фильма"""
    model = Movie
    fields = ['title', 'description', 'video']
    template_name = 'movies/upload.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            'Фильм загружен! HLS обработка началась в фоне.'
        )
        return response


class MovieDetailView(DetailView):
    """View для просмотра фильма"""
    model = Movie
    template_name = 'movies/detail.html'
    context_object_name = 'movie'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        movie = self.object

        # Информация о видео для плеера
        context['video_info'] = {
            'hls_url': movie.video.master_url(),
            'preview_url': movie.video.preview_url(),
            'duration': movie.duration.total_seconds() if movie.duration else 0,
            'resolution': f"{movie.width}x{movie.height}" if movie.width and movie.height else None,
        }

        return context


def video_status_api(request, movie_id):
    """API для проверки статуса обработки видео"""
    movie = get_object_or_404(Movie, id=movie_id)

    status = {
        'ready': bool(movie.hls_playlist),
        'hls_url': movie.video.master_url() if movie.hls_playlist else None,
        'preview_url': movie.video.preview_url(),
        'metadata': {
            'duration': movie.duration.total_seconds() if movie.duration else None,
            'width': movie.width,
            'height': movie.height,
        }
    }

    return JsonResponse(status)


# ============================================================================
# 3. ФОРМЫ ДЛЯ ЗАГРУЗКИ
# ============================================================================

from django import forms


class MovieUploadForm(forms.ModelForm):
    """Форма для загрузки фильма с валидацией"""

    class Meta:
        model = Movie
        fields = ['title', 'description', 'video']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Название фильма'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Описание фильма'
            }),
            'video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/*'
            })
        }

    def clean_video(self):
        """Валидация загружаемого видео"""
        video = self.cleaned_data.get('video')

        if video:
            # Проверка размера (максимум 1GB)
            if video.size > 1024 * 1024 * 1024:  # 1GB
                raise forms.ValidationError(
                    'Файл слишком большой. Максимальный размер: 1GB'
                )

            # Проверка типа файла
            allowed_types = [
                'video/mp4', 'video/avi', 'video/mov',
                'video/wmv', 'video/flv', 'video/webm'
            ]

            if hasattr(video, 'content_type') and video.content_type not in allowed_types:
                raise forms.ValidationError(
                    f'Неподдерживаемый тип файла: {video.content_type}'
                )

        return video


# ============================================================================
# 4. ШАБЛОНЫ
# ============================================================================

# templates/movies/upload.html
UPLOAD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Загрузка фильма</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-md-8">
                <h2>🎬 Загрузка фильма</h2>

                {% if messages %}
                    {% for message in messages %}
                        <div class="alert alert-{{ message.tags }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}

                <form method="post" enctype="multipart/form-data" id="upload-form">
                    {% csrf_token %}

                    <div class="mb-3">
                        {{ form.title.label_tag }}
                        {{ form.title }}
                        {{ form.title.errors }}
                    </div>

                    <div class="mb-3">
                        {{ form.description.label_tag }}
                        {{ form.description }}
                        {{ form.description.errors }}
                    </div>

                    <div class="mb-3">
                        {{ form.video.label_tag }}
                        {{ form.video }}
                        {{ form.video.errors }}
                        <div class="form-text">
                            Поддерживаемые форматы: MP4, AVI, MOV, WMV, FLV, WebM<br>
                            Максимальный размер: 1GB
                        </div>
                    </div>

                    <button type="submit" class="btn btn-primary" id="submit-btn">
                        <span id="submit-text">Загрузить</span>
                        <span id="submit-spinner" class="spinner-border spinner-border-sm ms-2" style="display: none;"></span>
                    </button>
                </form>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('upload-form').addEventListener('submit', function() {
            document.getElementById('submit-text').textContent = 'Загружается...';
            document.getElementById('submit-spinner').style.display = 'inline-block';
            document.getElementById('submit-btn').disabled = true;
        });
    </script>
</body>
</html>
"""

# templates/movies/detail.html
DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ movie.title }}</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-4">
        <div class="row">
            <div class="col-md-8">
                <h1>{{ movie.title }}</h1>

                {% if video_info.hls_url %}
                    <!-- Используем готовый плеер от django-hlsfield -->
                    {% include "hlsfield/players/hls_player.html" with hls_url=video_info.hls_url %}
                {% else %}
                    <!-- Показываем превью и статус обработки -->
                    <div class="alert alert-info">
                        <h5>🎬 Видео обрабатывается...</h5>
                        <p>Создается адаптивный стрим. Это может занять несколько минут.</p>

                        {% if video_info.preview_url %}
                            <img src="{{ video_info.preview_url }}" alt="Превью" class="img-thumbnail" style="max-width: 300px;">
                        {% endif %}

                        <div id="processing-status" class="mt-3">
                            <button class="btn btn-sm btn-outline-primary" onclick="checkStatus()">
                                Проверить статус
                            </button>
                        </div>
                    </div>
                {% endif %}

                {% if movie.description %}
                    <div class="mt-4">
                        <h5>Описание</h5>
                        <p>{{ movie.description }}</p>
                    </div>
                {% endif %}

                <div class="mt-4">
                    <h6>Информация о видео</h6>
                    <ul class="list-unstyled">
                        {% if video_info.duration %}
                            <li><strong>Длительность:</strong> {{ video_info.duration|floatformat:0 }} сек</li>
                        {% endif %}
                        {% if video_info.resolution %}
                            <li><strong>Разрешение:</strong> {{ video_info.resolution }}</li>
                        {% endif %}
                        <li><strong>Загружено:</strong> {{ movie.created_at }}</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function checkStatus() {
            try {
                const response = await fetch(`/api/movies/{{ movie.id }}/status/`);
                const data = await response.json();

                if (data.ready) {
                    location.reload(); // Перезагружаем страницу если видео готово
                } else {
                    document.getElementById('processing-status').innerHTML = `
                        <div class="progress mb-2">
                            <div class="progress-bar progress-bar-striped progress-bar-animated"
                                 style="width: 60%"></div>
                        </div>
                        <small class="text-muted">Обработка продолжается...</small>
                    `;
                }
            } catch (error) {
                console.error('Ошибка проверки статуса:', error);
            }
        }

        // Автоматическая проверка статуса каждые 10 секунд
        {% if not video_info.hls_url %}
            setInterval(checkStatus, 10000);
        {% endif %}
    </script>
</body>
</html>
"""


# ============================================================================
# 5. URL КОНФИГУРАЦИЯ
# ============================================================================

from django.urls import path

urlpatterns = [
    path('movies/upload/', MovieCreateView.as_view(), name='movie_upload'),
    path('movies/<int:pk>/', MovieDetailView.as_view(), name='movie_detail'),
    path('api/movies/<int:movie_id>/status/', video_status_api, name='movie_status_api'),
]


# ============================================================================
# 6. DJANGO ADMIN НАСТРОЙКА
# ============================================================================

from django.contrib import admin
from hlsfield.widgets import AdminVideoWidget


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_at', 'duration', 'width', 'height', 'has_hls']
    list_filter = ['created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['duration', 'width', 'height', 'preview_image', 'hls_playlist', 'created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'video')
        }),
        ('Метаданные (автоматически)', {
            'fields': ('duration', 'width', 'height', 'preview_image'),
            'classes': ('collapse',)
        }),
        ('Техническая информация', {
            'fields': ('hls_playlist', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def has_hls(self, obj):
        return bool(obj.hls_playlist)
    has_hls.boolean = True
    has_hls.short_description = 'HLS готов'

    # Кастомный виджет для предварительного просмотра видео
    formfield_overrides = {
        VideoField: {'widget': AdminVideoWidget},
    }


# ============================================================================
# 7. CELERY ЗАДАЧИ (ОПЦИОНАЛЬНО)
# ============================================================================

try:
    from celery import shared_task

    @shared_task
    def notify_video_ready(movie_id):
        """Уведомление о готовности видео"""
        try:
            movie = Movie.objects.get(id=movie_id)
            if movie.hls_playlist:
                # Здесь можно отправить email, push-уведомление и т.д.
                print(f"Видео '{movie.title}' готово к просмотру!")

                # Пример отправки email
                from django.core.mail import send_mail
                send_mail(
                    subject=f'Видео "{movie.title}" готово!',
                    message='Ваше видео было успешно обработано и готово к просмотру.',
                    from_email='noreply@example.com',
                    recipient_list=['user@example.com'],
                    fail_silently=True
                )
        except Movie.DoesNotExist:
            pass

    # Подключаем задачу к сигналу сохранения
    from django.db.models.signals import post_save
    from django.dispatch import receiver

    @receiver(post_save, sender=Movie)
    def movie_hls_ready_handler(sender, instance, **kwargs):
        """Обработчик готовности HLS"""
        if instance.hls_playlist and not getattr(instance, '_hls_notification_sent', False):
            notify_video_ready.delay(instance.id)
            instance._hls_notification_sent = True

except ImportError:
    # Celery не установлен
    pass


# ============================================================================
# 8. ПРИМЕР ИСПОЛЬЗОВАНИЯ В КОДЕ
# ============================================================================

def example_usage():
    """Пример программного использования"""

    # Создание фильма
    from django.core.files import File

    with open('my_video.mp4', 'rb') as video_file:
        movie = Movie.objects.create(
            title='Мой фильм',
            description='Описание фильма',
            video=File(video_file)
        )

    # Сразу после сохранения доступны метаданные и превью
    print(f"Длительность: {movie.duration}")
