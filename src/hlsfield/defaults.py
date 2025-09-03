"""
🔧 Настройки по умолчанию для django-hlsfield

Этот модуль содержит все конфигурационные параметры пакета.
Значения можно переопределить через Django settings с префиксом HLSFIELD_.

Пример настройки в settings.py:
    HLSFIELD_FFMPEG = "/usr/local/bin/ffmpeg"
    HLSFIELD_DEFAULT_LADDER = [
        {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
    ]

Автор: akula993
Лицензия: MIT
"""

import logging
import os
import uuid

logger = logging.getLogger(__name__)


# ==============================================================================
# БЕЗОПАСНЫЙ ДОСТУП К DJANGO SETTINGS
# ==============================================================================

def _get_django_settings():
    """Безопасно получает объект Django settings"""
    from django.core.exceptions import ImproperlyConfigured
    try:
        import django
        if not hasattr(django, 'apps') or not django.apps.apps.ready:
            return None

        from django.conf import settings as django_settings

        if not hasattr(django_settings, 'configured') or not django_settings.configured:
            return None

        getattr(django_settings, 'DEBUG', False)
        return django_settings
    except (ImportError, ImproperlyConfigured, AttributeError):
        return None
    except Exception:
        return None


def _get_setting(name: str, default):
    """Получает значение настройки из Django settings или возвращает default"""
    settings = _get_django_settings()
    if settings is None:
        return default
    try:
        return getattr(settings, name, default)
    except Exception:
        logger.debug(f"Could not get setting {name}, using default")
        return default


# ==============================================================================
# ПУТИ К БИНАРНЫМ ФАЙЛАМ FFMPEG
# ==============================================================================

FFMPEG = _get_setting("HLSFIELD_FFMPEG", "ffmpeg")
FFPROBE = _get_setting("HLSFIELD_FFPROBE", "ffprobe")
FFMPEG_TIMEOUT = int(_get_setting("HLSFIELD_FFMPEG_TIMEOUT", 300))  # 5 минут


# ==============================================================================
# ЛЕСТНИЦЫ КАЧЕСТВ
# ==============================================================================

DEFAULT_LADDER = _get_setting("HLSFIELD_DEFAULT_LADDER", [
    {"height": 240, "v_bitrate": 300, "a_bitrate": 64},
    {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
    {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
    {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
])


# ==============================================================================
# ПАРАМЕТРЫ СЕГМЕНТАЦИИ
# ==============================================================================

SEGMENT_DURATION = int(_get_setting("HLSFIELD_SEGMENT_DURATION", 6))
DASH_SEGMENT_DURATION = int(_get_setting("HLSFIELD_DASH_SEGMENT_DURATION", 4))


# ==============================================================================
# СТРУКТУРА ФАЙЛОВ
# ==============================================================================

SIDECAR_LAYOUT = _get_setting("HLSFIELD_SIDECAR_LAYOUT", "nested")
PREVIEW_FILENAME = _get_setting("HLSFIELD_PREVIEW_FILENAME", "preview.jpg")
META_FILENAME = _get_setting("HLSFIELD_META_FILENAME", "meta.json")

HLS_SUBDIR = _get_setting("HLSFIELD_HLS_SUBDIR", "hls")
DASH_SUBDIR = _get_setting("HLSFIELD_DASH_SUBDIR", "dash")
ADAPTIVE_SUBDIR = _get_setting("HLSFIELD_ADAPTIVE_SUBDIR", "adaptive")


# ==============================================================================
# АВТОМАТИЧЕСКИЙ UPLOAD_TO
# ==============================================================================

USE_DEFAULT_UPLOAD_TO = bool(_get_setting("HLSFIELD_USE_DEFAULT_UPLOAD_TO", True))
DEFAULT_UPLOAD_TO_PATH = _get_setting("HLSFIELD_DEFAULT_UPLOAD_TO", None)


def default_upload_to(instance, filename: str) -> str:
    """Функция upload_to по умолчанию"""
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]
    return f"videos/{folder}/{stem}{ext}"


# ==============================================================================
# НАСТРОЙКИ ОБРАБОТКИ
# ==============================================================================

DEFAULT_PREVIEW_AT = float(_get_setting("HLSFIELD_DEFAULT_PREVIEW_AT", 3.0))
PROCESS_ON_SAVE = bool(_get_setting("HLSFIELD_PROCESS_ON_SAVE", True))
CREATE_PREVIEW = bool(_get_setting("HLSFIELD_CREATE_PREVIEW", True))
EXTRACT_METADATA = bool(_get_setting("HLSFIELD_EXTRACT_METADATA", True))


# ==============================================================================
# ОГРАНИЧЕНИЯ И ВАЛИДАЦИЯ
# ==============================================================================

MAX_FILE_SIZE = int(_get_setting("HLSFIELD_MAX_FILE_SIZE", 2 * 1024 ** 3))  # 2GB
MIN_FILE_SIZE = int(_get_setting("HLSFIELD_MIN_FILE_SIZE", 1000))  # 1KB

ALLOWED_MIME_TYPES = _get_setting("HLSFIELD_ALLOWED_MIME_TYPES", [
    'video/mp4',
    'video/avi',
    'video/mov',
    'video/wmv',
    'video/flv',
    'video/webm',
    'video/quicktime',
    'video/x-msvideo',
])

ALLOWED_EXTENSIONS = _get_setting("HLSFIELD_ALLOWED_EXTENSIONS", [
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv',
    '.m4v', '.3gp', '.ogv'
])

MAX_VIDEO_HEIGHT = int(_get_setting("HLSFIELD_MAX_VIDEO_HEIGHT", 8192))
MIN_VIDEO_HEIGHT = int(_get_setting("HLSFIELD_MIN_VIDEO_HEIGHT", 144))
MAX_VIDEO_DURATION = int(_get_setting("HLSFIELD_MAX_VIDEO_DURATION", 7200))  # 2 часа


# ==============================================================================
# CELERY НАСТРОЙКИ
# ==============================================================================

CELERY_QUEUE = _get_setting("HLSFIELD_CELERY_QUEUE", "default")
CELERY_PRIORITY = int(_get_setting("HLSFIELD_CELERY_PRIORITY", 5))
CELERY_TASK_TIMEOUT = int(_get_setting("HLSFIELD_CELERY_TASK_TIMEOUT", 3600))  # 1 час
CELERY_TASK_RETRY = int(_get_setting("HLSFIELD_CELERY_TASK_RETRY", 3))
CELERY_RETRY_DELAY = int(_get_setting("HLSFIELD_CELERY_RETRY_DELAY", 60))


# ==============================================================================
# КОДИРОВАНИЕ И КАЧЕСТВО
# ==============================================================================

FFMPEG_PRESET = _get_setting("HLSFIELD_FFMPEG_PRESET", "veryfast")
H264_PROFILE = _get_setting("HLSFIELD_H264_PROFILE", "main")
H264_LEVEL = _get_setting("HLSFIELD_H264_LEVEL", "4.1")
PIXEL_FORMAT = _get_setting("HLSFIELD_PIXEL_FORMAT", "yuv420p")

AUDIO_CODEC = _get_setting("HLSFIELD_AUDIO_CODEC", "aac")
AUDIO_SAMPLE_RATE = int(_get_setting("HLSFIELD_AUDIO_SAMPLE_RATE", 48000))
AUDIO_CHANNELS = int(_get_setting("HLSFIELD_AUDIO_CHANNELS", 2))


# ==============================================================================
# ЛОГИРОВАНИЕ
# ==============================================================================

VERBOSE_LOGGING = bool(_get_setting("HLSFIELD_VERBOSE_LOGGING", False))
SAVE_FFMPEG_LOGS = bool(_get_setting("HLSFIELD_SAVE_FFMPEG_LOGS", False))
FFMPEG_LOG_DIR = _get_setting("HLSFIELD_FFMPEG_LOG_DIR", "/tmp/hlsfield_logs")


# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================

SUPPORTED_VIDEO_CODECS = ['h264', 'libx264', 'h265', 'libx265', 'vp8', 'vp9']
SUPPORTED_AUDIO_CODECS = ['aac', 'mp3', 'opus']
SUPPORTED_CONTAINERS = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'flv']


# ==============================================================================
# RUNTIME ИНФОРМАЦИЯ (УПРОЩЕННАЯ)
# ==============================================================================

def get_runtime_info() -> dict:
    """Возвращает основную runtime информацию"""
    import shutil
    import sys

    ffmpeg_available = shutil.which(FFMPEG) is not None
    ffprobe_available = shutil.which(FFPROBE) is not None
    django_settings = _get_django_settings()

    return {
        'ffmpeg': {
            'available': ffmpeg_available,
            'path': FFMPEG,
        },
        'processing': {
            'ladder_count': len(DEFAULT_LADDER),
            'segment_duration': SEGMENT_DURATION,
            'max_file_size_mb': MAX_FILE_SIZE // (1024 * 1024),
        },
        'django': {
            'configured': django_settings is not None,
            'settings_module': os.environ.get('DJANGO_SETTINGS_MODULE'),
        },
        'python_version': sys.version.split()[0],
    }


def validate_settings() -> list[str]:
    """Валидирует основные настройки"""
    issues = []

    import shutil
    if not shutil.which(FFMPEG):
        issues.append(f"FFmpeg not found at '{FFMPEG}'")

    if not shutil.which(FFPROBE):
        issues.append(f"FFprobe not found at '{FFPROBE}'")

    if not DEFAULT_LADDER:
        issues.append("DEFAULT_LADDER cannot be empty")

    if MAX_FILE_SIZE <= 0:
        issues.append("MAX_FILE_SIZE must be positive")

    if not (2 <= SEGMENT_DURATION <= 60):
        issues.append("SEGMENT_DURATION must be between 2 and 60 seconds")

    return issues


# ==============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ==============================================================================

def setup_logging():
    """Настраивает базовое логирование"""
    logger = logging.getLogger('hlsfield')

    if VERBOSE_LOGGING:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Инициализация при импорте
if _get_django_settings():
    setup_logging()
