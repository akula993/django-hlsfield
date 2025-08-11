# django-hlsfield

[![PyPI version](https://badge.fury.io/py/django-hlsfield.svg)](https://badge.fury.io/py/django-hlsfield)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Django 4.2+](https://img.shields.io/badge/django-4.2+-green.svg)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🎥 **Автоматическое создание адаптивного видео для Django**

Django-библиотека для автоматической обработки видео с генерацией HLS/DASH стримов, превью и метаданных. Просто загрузите видео — получите адаптивный стрим с выбором качества!

## ✨ Возможности

- 📹 **VideoField** — базовое поле с извлечением метаданных и превью
- 🎬 **HLSVideoField** — автоматическая генерация HLS с несколькими качествами
- 📺 **DASHVideoField** — DASH стриминг для современных браузеров
- 🌐 **AdaptiveVideoField** — HLS + DASH одновременно для максимальной совместимости
- ☁️ **Любые Storage** — работает с локальными файлами, S3, MinIO
- ⚡ **Celery + синхронный режим** — быстрая загрузка + фоновая обработка
- 🎛️ **Готовые плееры** — HTML5 плееры с выбором качества

## 🚀 Быстрый старт

### Установка

```bash
pip install django-hlsfield
```

**Требования:** ffmpeg и ffprobe должны быть установлены в системе

### Настройка

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'hlsfield',
]

# Опционально: пути к бинарям
HLSFIELD_FFMPEG = "ffmpeg"   # или полный путь
HLSFIELD_FFPROBE = "ffprobe"

# Качества видео (по умолчанию)
HLSFIELD_DEFAULT_LADDER = [
    {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
    {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
]
```

## 📝 Примеры использования

### 1. Простое видео с метаданными

```python
# models.py
from django.db import models
from hlsfield import VideoField

class Video(models.Model):
    title = models.CharField(max_length=200)
    video = VideoField(
        upload_to="videos/",
        duration_field="duration",      # автозаполнение длительности
        width_field="width",            # ширина кадра
        height_field="height",          # высота кадра
        preview_field="preview_image"   # путь к превью
    )

    # Поля для метаданных (опционально)
    duration = models.DurationField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    preview_image = models.CharField(max_length=500, null=True, blank=True)

# Использование
video = Video.objects.get(pk=1)
print(f"Длительность: {video.duration}")
print(f"Разрешение: {video.width}x{video.height}")
print(f"Превью: {video.video.preview_url()}")
```

### 2. HLS адаптивное видео

```python
# models.py
from hlsfield import HLSVideoField

class Lecture(models.Model):
    title = models.CharField(max_length=200)
    video = HLSVideoField(
        upload_to="lectures/",
        hls_playlist_field="hls_master"  # поле для master.m3u8
    )
    hls_master = models.CharField(max_length=500, null=True, blank=True)

# templates/lecture_detail.html
{% if lecture.video.master_url %}
    {% include "hlsfield/players/hls_player.html" with hls_url=lecture.video.master_url %}
{% else %}
    <p>Видео обрабатывается...</p>
{% endif %}
```

### 3. Полный стек: HLS + DASH

```python
# models.py
from hlsfield import AdaptiveVideoField

class Movie(models.Model):
    title = models.CharField(max_length=200)
    video = AdaptiveVideoField(
        upload_to="movies/",
        hls_playlist_field="hls_playlist",
        dash_manifest_field="dash_manifest",
        ladder=[  # настройка качеств
            {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
            {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
        ]
    )
    hls_playlist = models.CharField(max_length=500, null=True, blank=True)
    dash_manifest = models.CharField(max_length=500, null=True, blank=True)

# templates/movie_detail.html
{% include "hlsfield/players/universal_player.html" with hls_url=movie.video.master_url dash_url=movie.video.dash_url %}
```

### 4. Интеграция с S3

```python
# settings.py
from storages.backends.s3boto3 import S3Boto3Storage

class MediaStorage(S3Boto3Storage):
    bucket_name = 'my-video-bucket'
    region_name = 'us-east-1'

DEFAULT_FILE_STORAGE = 'myapp.storage.MediaStorage'

# models.py - без изменений!
class Video(models.Model):
    video = HLSVideoField(upload_to="videos/")  # работает с S3 автоматически
```

### 5. Настройка качества и параметров

```python
# settings.py
HLSFIELD_DEFAULT_LADDER = [
    {"height": 240, "v_bitrate": 300, "a_bitrate": 64},   # мобайл
    {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},  # SD
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128}, # HD
    {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160}, # Full HD
    {"height": 1440, "v_bitrate": 8000, "a_bitrate": 192}, # 2K
]

HLSFIELD_SEGMENT_DURATION = 6  # длина сегментов в секундах

# models.py - кастомное качество для конкретного поля
class PremiumVideo(models.Model):
    video = HLSVideoField(
        ladder=[
            {"height": 1080, "v_bitrate": 6000, "a_bitrate": 160},
            {"height": 1440, "v_bitrate": 12000, "a_bitrate": 192},
            {"height": 2160, "v_bitrate": 20000, "a_bitrate": 256},  # 4K
        ]
    )
```

## 🔧 Настройка Celery (рекомендуется)

Без Celery обработка видео блокирует запрос. С Celery — мгновенная загрузка + фоновая обработка.

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'hlsfield',
]

# celery.py
from celery import Celery
app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Запуск воркера
# celery -A myproject worker -l info
```

## 🎮 Готовые плееры

Библиотека включает готовые HTML-шаблоны плееров:

```html
<!-- HLS плеер -->
{% include "hlsfield/players/hls_player.html" with hls_url=video.master_url %}

<!-- DASH плеер -->
{% include "hlsfield/players/dash_player.html" with dash_url=video.dash_url %}

<!-- Универсальный (HLS + DASH + прямое MP4) -->
{% include "hlsfield/players/universal_player.html" with hls_url=... dash_url=... video_url=... %}

<!-- Адаптивный (автовыбор HLS/DASH) -->
{% include "hlsfield/players/adaptive_player.html" with hls_url=... dash_url=... %}
```

## 📁 Структура файлов

После обработки видео структура будет выглядеть так:

```
media/
└── videos/
    └── abc12345/
        ├── my_video.mp4           # оригинал
        ├── preview.jpg            # превью-кадр
        ├── meta.json             # метаданные
        └── hls/                  # HLS артефакты
            ├── master.m3u8       # главный плейлист
            ├── v360/             # качество 360p
            │   ├── index.m3u8
            │   └── seg_*.ts
            ├── v720/             # качество 720p
            │   ├── index.m3u8
            │   └── seg_*.ts
            └── v1080/            # качество 1080p
                ├── index.m3u8
                └── seg_*.ts
```

## ⚙️ Конфигурация

| Настройка | По умолчанию | Описание |
|-----------|--------------|----------|
| `HLSFIELD_FFMPEG` | `"ffmpeg"` | Путь к ffmpeg |
| `HLSFIELD_FFPROBE` | `"ffprobe"` | Путь к ffprobe |
| `HLSFIELD_SEGMENT_DURATION` | `6` | Длина HLS сегментов (сек) |
| `HLSFIELD_DEFAULT_LADDER` | `[360p, 720p, 1080p]` | Качества по умолчанию |
| `HLSFIELD_SIDECAR_LAYOUT` | `"nested"` | Структура файлов |

## 🐛 Решение проблем

### FFmpeg не найден
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Скачать с https://ffmpeg.org/download.html
```

### Большие файлы зависают
```python
# settings.py - увеличить таймауты
FILE_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024  # 100MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024
```

### Проблемы с S3
```python
# Проверить права доступа к bucket
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = 'public-read'  # для публичных видео
```

## 🤝 Вклад в проект

1. Fork репозитория
2. Создайте ветку: `git checkout -b feature/amazing-feature`
3. Commit изменения: `git commit -m 'Add amazing feature'`
4. Push в ветку: `git push origin feature/amazing-feature`
5. Откройте Pull Request

## 📄 Лицензия

MIT License. См. [LICENSE](LICENSE) для деталей.

## 🎯 Roadmap

- [ ] Автотесты и CI/CD
- [ ] WebVTT субтитры и превью-спрайты
- [ ] GPU-ускорение через NVENC/VAAPI
- [ ] Поддержка HEVC/AV1 кодеков
- [ ] Интеграция с CDN (CloudFront, Cloudflare)

---

**Сделано с ❤️ для Django-сообщества**
