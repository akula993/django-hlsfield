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

Автор: django-hlsfield team
Лицензия: MIT
"""

import os
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ==============================================================================
# БЕЗОПАСНЫЙ ДОСТУП К DJANGO SETTINGS
# ==============================================================================

def _get_django_settings():
    """Безопасно получает объект Django settings"""
    try:
        from django.conf import settings as django_settings
        from django.core.exceptions import ImproperlyConfigured
        configured = getattr(django_settings, "configured", False)
        if not configured:
            return None

        # Пробуем обратиться к настройкам
        django_settings.DEBUG  # Это вызовет ImproperlyConfigured если не настроено
        return django_settings
    except (ImportError, ImproperlyConfigured):
        # Django не установлен
        return None
    except Exception:
        # Другие проблемы с настройками
        return None


def _get_setting(name: str, default):
    """
    Получает значение настройки из Django settings или возвращает default.

    Args:
        name: Имя настройки с префиксом HLSFIELD_
        default: Значение по умолчанию

    Returns:
        Значение настройки или default
    """
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

# Путь к исполняемому файлу ffmpeg
FFMPEG = _get_setting("HLSFIELD_FFMPEG", "ffmpeg")

# Путь к исполняемому файлу ffprobe
FFPROBE = _get_setting("HLSFIELD_FFPROBE", "ffprobe")

# Таймаут для операций ffmpeg в секундах
FFMPEG_TIMEOUT = int(_get_setting("HLSFIELD_FFMPEG_TIMEOUT", 300))  # 5 минут

# ==============================================================================
# ЛЕСТНИЦЫ КАЧЕСТВ ПО УМОЛЧАНИЮ
# ==============================================================================

# Основная лестница качеств (используется если не указана кастомная)
DEFAULT_LADDER = _get_setting("HLSFIELD_DEFAULT_LADDER", [
    {"height": 240, "v_bitrate": 300, "a_bitrate": 64},  # Мобильный 3G
    {"height": 360, "v_bitrate": 800, "a_bitrate": 96},  # Мобильный 4G/WiFi
    {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},  # SD качество
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},  # HD качество
    {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},  # Full HD
])

# Компактная лестница для ограниченного трафика
MOBILE_LADDER = _get_setting("HLSFIELD_MOBILE_LADDER", [
    {"height": 240, "v_bitrate": 300, "a_bitrate": 64},
    {"height": 360, "v_bitrate": 600, "a_bitrate": 96},
    {"height": 480, "v_bitrate": 900, "a_bitrate": 96},
])

# Premium лестница с высокими битрейтами
PREMIUM_LADDER = _get_setting("HLSFIELD_PREMIUM_LADDER", [
    {"height": 480, "v_bitrate": 1500, "a_bitrate": 128},
    {"height": 720, "v_bitrate": 3000, "a_bitrate": 128},
    {"height": 1080, "v_bitrate": 6000, "a_bitrate": 160},
    {"height": 1440, "v_bitrate": 12000, "a_bitrate": 192},  # 2K
    {"height": 2160, "v_bitrate": 25000, "a_bitrate": 256},  # 4K
])

# ==============================================================================
# ПАРАМЕТРЫ СЕГМЕНТАЦИИ
# ==============================================================================

# Длительность сегментов HLS в секундах
SEGMENT_DURATION = int(_get_setting("HLSFIELD_SEGMENT_DURATION", 6))

# Длительность сегментов DASH в секундах (обычно короче чем HLS)
DASH_SEGMENT_DURATION = int(_get_setting("HLSFIELD_DASH_SEGMENT_DURATION", 4))

# Максимальное количество сегментов в плейлисте (для ограничения размера)
MAX_SEGMENTS_IN_PLAYLIST = int(_get_setting("HLSFIELD_MAX_SEGMENTS", 1000))

# ==============================================================================
# СТРУКТУРА ФАЙЛОВ
# ==============================================================================

# Layout для sidecar файлов: "nested" или "flat"
# nested: videos/abc123/hls/master.m3u8, videos/abc123/preview.jpg
# flat: videos/abc123.mp4, videos/abc123_hls_master.m3u8, videos/abc123_preview.jpg
SIDECAR_LAYOUT = _get_setting("HLSFIELD_SIDECAR_LAYOUT", "nested")

# Имена файлов для nested layout
PREVIEW_FILENAME = _get_setting("HLSFIELD_PREVIEW_FILENAME", "preview.jpg")
META_FILENAME = _get_setting("HLSFIELD_META_FILENAME", "meta.json")

# Поддиректории для разных типов контента
HLS_SUBDIR = _get_setting("HLSFIELD_HLS_SUBDIR", "hls")
DASH_SUBDIR = _get_setting("HLSFIELD_DASH_SUBDIR", "dash")
ADAPTIVE_SUBDIR = _get_setting("HLSFIELD_ADAPTIVE_SUBDIR", "adaptive")

# ==============================================================================
# АВТОМАТИЧЕСКИЙ UPLOAD_TO
# ==============================================================================

# Включать ли автоматический upload_to для полей без явного указания
USE_DEFAULT_UPLOAD_TO = bool(_get_setting("HLSFIELD_USE_DEFAULT_UPLOAD_TO", True))

# Dotted path к функции upload_to (например: "myapp.utils.video_upload_to")
DEFAULT_UPLOAD_TO_PATH = _get_setting("HLSFIELD_DEFAULT_UPLOAD_TO", None)


def default_upload_to(instance, filename: str) -> str:
    """
    Функция upload_to по умолчанию.

    Создает структуру: videos/{uuid8}/{filename}

    Args:
        instance: Экземпляр модели
        filename: Имя загружаемого файла

    Returns:
        str: Путь для сохранения файла
    """
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]  # 8-символьный UUID
    return f"videos/{folder}/{stem}{ext}"


def date_based_upload_to(instance, filename: str) -> str:
    """
    Upload_to на основе даты.

    Создает структуру: videos/2025/01/15/{uuid4}/{filename}
    """
    from datetime import datetime

    now = datetime.now()
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex

    return f"videos/{now.year:04d}/{now.month:02d}/{now.day:02d}/{folder}/{stem}{ext}"


def user_based_upload_to(instance, filename: str) -> str:
    """
    Upload_to на основе пользователя.

    Создает структуру: videos/users/{user_id}/{uuid8}/{filename}
    """
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]

    # Пытаемся получить ID пользователя
    user_id = "anonymous"
    if hasattr(instance, 'user') and hasattr(instance.user, 'id'):
        user_id = str(instance.user.id)
    elif hasattr(instance, 'owner') and hasattr(instance.owner, 'id'):
        user_id = str(instance.owner.id)

    return f"videos/users/{user_id}/{folder}/{stem}{ext}"


# ==============================================================================
# НАСТРОЙКИ ОБРАБОТКИ
# ==============================================================================

# Время (в секундах) для извлечения превью кадра
DEFAULT_PREVIEW_AT = float(_get_setting("HLSFIELD_DEFAULT_PREVIEW_AT", 3.0))

# Включать ли обработку видео при сохранении
PROCESS_ON_SAVE = bool(_get_setting("HLSFIELD_PROCESS_ON_SAVE", True))

# Создавать ли превью автоматически
CREATE_PREVIEW = bool(_get_setting("HLSFIELD_CREATE_PREVIEW", True))

# Извлекать ли метаданные автоматически
EXTRACT_METADATA = bool(_get_setting("HLSFIELD_EXTRACT_METADATA", True))

# ==============================================================================
# ОГРАНИЧЕНИЯ И ВАЛИДАЦИЯ
# ==============================================================================

# Максимальный размер загружаемого файла в байтах
MAX_FILE_SIZE = int(_get_setting("HLSFIELD_MAX_FILE_SIZE", 2 * 1024 ** 3))  # 2GB

# Минимальный размер файла в байтах
MIN_FILE_SIZE = int(_get_setting("HLSFIELD_MIN_FILE_SIZE", 1000))  # 1KB

# Разрешенные MIME типы
ALLOWED_MIME_TYPES = _get_setting("HLSFIELD_ALLOWED_MIME_TYPES", [
    'video/mp4',
    'video/avi',
    'video/mov',
    'video/wmv',
    'video/flv',
    'video/webm',
    'video/quicktime',
    'video/x-msvideo',
    'video/x-ms-wmv',
])

# Разрешенные расширения файлов
ALLOWED_EXTENSIONS = _get_setting("HLSFIELD_ALLOWED_EXTENSIONS", [
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv',
    '.m4v', '.3gp', '.ogv', '.asf'
])

# Максимальное разрешение видео (высота в пикселях)
MAX_VIDEO_HEIGHT = int(_get_setting("HLSFIELD_MAX_VIDEO_HEIGHT", 8192))

# Минимальное разрешение видео
MIN_VIDEO_HEIGHT = int(_get_setting("HLSFIELD_MIN_VIDEO_HEIGHT", 144))

# Максимальная длительность видео в секундах
MAX_VIDEO_DURATION = int(_get_setting("HLSFIELD_MAX_VIDEO_DURATION", 7200))  # 2 часа

# ==============================================================================
# CELERY НАСТРОЙКИ
# ==============================================================================

# Имя очереди для задач обработки видео
CELERY_QUEUE = _get_setting("HLSFIELD_CELERY_QUEUE", "default")

# Приоритет задач обработки видео (0-9, где 9 = высший приоритет)
CELERY_PRIORITY = int(_get_setting("HLSFIELD_CELERY_PRIORITY", 5))

# Таймаут для задач Celery в секундах
CELERY_TASK_TIMEOUT = int(_get_setting("HLSFIELD_CELERY_TASK_TIMEOUT", 3600))  # 1 час

# Количество повторных попыток при ошибках
CELERY_TASK_RETRY = int(_get_setting("HLSFIELD_CELERY_TASK_RETRY", 3))

# Задержка между повторами в секундах
CELERY_RETRY_DELAY = int(_get_setting("HLSFIELD_CELERY_RETRY_DELAY", 60))

# ==============================================================================
# КОДИРОВАНИЕ И КАЧЕСТВО
# ==============================================================================

# Пресет FFmpeg для кодирования (скорость vs качество)
# ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
FFMPEG_PRESET = _get_setting("HLSFIELD_FFMPEG_PRESET", "veryfast")

# Профиль H.264 (baseline, main, high)
H264_PROFILE = _get_setting("HLSFIELD_H264_PROFILE", "main")

# Уровень H.264 (влияет на совместимость с устройствами)
H264_LEVEL = _get_setting("HLSFIELD_H264_LEVEL", "4.1")

# Pixel format (yuv420p для максимальной совместимости)
PIXEL_FORMAT = _get_setting("HLSFIELD_PIXEL_FORMAT", "yuv420p")

# Аудио кодек
AUDIO_CODEC = _get_setting("HLSFIELD_AUDIO_CODEC", "aac")

# Частота дискретизации аудио
AUDIO_SAMPLE_RATE = int(_get_setting("HLSFIELD_AUDIO_SAMPLE_RATE", 48000))

# Количество аудио каналов
AUDIO_CHANNELS = int(_get_setting("HLSFIELD_AUDIO_CHANNELS", 2))

# ==============================================================================
# МОНИТОРИНГ И ЛОГИРОВАНИЕ
# ==============================================================================

# Включать ли подробное логирование операций FFmpeg
VERBOSE_LOGGING = bool(_get_setting("HLSFIELD_VERBOSE_LOGGING", False))

# Сохранять ли FFmpeg логи на диск для отладки
SAVE_FFMPEG_LOGS = bool(_get_setting("HLSFIELD_SAVE_FFMPEG_LOGS", False))

# Директория для логов FFmpeg
FFMPEG_LOG_DIR = _get_setting("HLSFIELD_FFMPEG_LOG_DIR", "/tmp/hlsfield_logs")

# Включать ли метрики производительности
ENABLE_PERFORMANCE_METRICS = bool(_get_setting("HLSFIELD_ENABLE_PERFORMANCE_METRICS", False))

# Сохранять ли статистику транскодинга
SAVE_TRANSCODING_STATS = bool(_get_setting("HLSFIELD_SAVE_TRANSCODING_STATS", False))

# ==============================================================================
# STORAGE И CDN
# ==============================================================================

# Использовать ли CDN для доставки контента
USE_CDN = bool(_get_setting("HLSFIELD_USE_CDN", False))

# Базовый URL CDN (если используется)
CDN_BASE_URL = _get_setting("HLSFIELD_CDN_BASE_URL", "")

# Время жизни кеша для плейлистов в секундах
PLAYLIST_CACHE_TTL = int(_get_setting("HLSFIELD_PLAYLIST_CACHE_TTL", 300))  # 5 минут

# Время жизни кеша для сегментов в секундах
SEGMENT_CACHE_TTL = int(_get_setting("HLSFIELD_SEGMENT_CACHE_TTL", 86400))  # 24 часа

# Включать ли сжатие плейлистов
COMPRESS_PLAYLISTS = bool(_get_setting("HLSFIELD_COMPRESS_PLAYLISTS", True))

# ==============================================================================
# ЭКСПЕРИМЕНТАЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

# Включать ли экспериментальные функции
ENABLE_EXPERIMENTAL = bool(_get_setting("HLSFIELD_ENABLE_EXPERIMENTAL", False))

# Использовать ли GPU ускорение (NVENC, VAAPI)
ENABLE_GPU_ACCELERATION = bool(_get_setting("HLSFIELD_ENABLE_GPU_ACCELERATION", False))

# Тип GPU ускорения: 'nvenc', 'vaapi', 'videotoolbox'
GPU_ACCELERATION_TYPE = _get_setting("HLSFIELD_GPU_ACCELERATION_TYPE", "nvenc")

# Включать ли AV1 кодек для современных браузеров
ENABLE_AV1_CODEC = bool(_get_setting("HLSFIELD_ENABLE_AV1_CODEC", False))

# Включать ли HEVC (H.265) кодек
ENABLE_HEVC_CODEC = bool(_get_setting("HLSFIELD_ENABLE_HEVC_CODEC", False))

# Создавать ли WebVTT субтитры автоматически
AUTO_GENERATE_SUBTITLES = bool(_get_setting("HLSFIELD_AUTO_GENERATE_SUBTITLES", False))

# ==============================================================================
# ПРОИЗВОДИТЕЛЬНОСТЬ И ОПТИМИЗАЦИЯ
# ==============================================================================

# Количество одновременных задач транскодинга
MAX_CONCURRENT_TRANSCODING = int(_get_setting("HLSFIELD_MAX_CONCURRENT_TRANSCODING", 2))

# Размер буфера для операций IO в байтах
IO_BUFFER_SIZE = int(_get_setting("HLSFIELD_IO_BUFFER_SIZE", 1024 * 1024))  # 1MB

# Использовать ли многопоточность FFmpeg
ENABLE_FFMPEG_THREADING = bool(_get_setting("HLSFIELD_ENABLE_FFMPEG_THREADING", True))

# Количество потоков для FFmpeg (0 = автоопределение)
FFMPEG_THREADS = int(_get_setting("HLSFIELD_FFMPEG_THREADS", 0))

# Включать ли оптимизацию для конкретных устройств
DEVICE_SPECIFIC_OPTIMIZATION = bool(_get_setting("HLSFIELD_DEVICE_SPECIFIC_OPTIMIZATION", False))

# ==============================================================================
# DEVELOPMENT И DEBUG
# ==============================================================================

# Сохранять ли временные файлы для отладки
KEEP_TEMP_FILES = bool(_get_setting("HLSFIELD_KEEP_TEMP_FILES", False))

# Директория для временных файлов (None = system temp)
TEMP_DIR = _get_setting("HLSFIELD_TEMP_DIR", None)

# Включать ли дополнительную валидацию в debug режиме
DEBUG_VALIDATION = bool(_get_setting("HLSFIELD_DEBUG_VALIDATION", False))

# Эмулировать ли медленную сеть для тестирования
SIMULATE_SLOW_NETWORK = bool(_get_setting("HLSFIELD_SIMULATE_SLOW_NETWORK", False))

# ==============================================================================
# КОНСТАНТЫ И ВСПОМОГАТЕЛЬНЫЕ ЗНАЧЕНИЯ
# ==============================================================================

# Поддерживаемые видео кодеки
SUPPORTED_VIDEO_CODECS = [
    'h264', 'libx264', 'h265', 'libx265', 'hevc', 'vp8', 'vp9', 'av1'
]

# Поддерживаемые аудио кодеки
SUPPORTED_AUDIO_CODECS = [
    'aac', 'mp3', 'opus', 'vorbis'
]

# Поддерживаемые контейнеры
SUPPORTED_CONTAINERS = [
    'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', '3gp'
]

# Магические байты для определения типов файлов
FILE_SIGNATURES = {
    b'\x00\x00\x00\x14ftypqt': 'video/quicktime',
    b'\x00\x00\x00\x18ftypisom': 'video/mp4',
    b'\x00\x00\x00\x1cftypisom': 'video/mp4',
    b'\x00\x00\x00\x20ftypisom': 'video/mp4',
    b'RIFF': 'video/avi',
    b'FLV\x01': 'video/x-flv',
}


# ==============================================================================
# RUNTIME ИНФОРМАЦИЯ
# ==============================================================================

def get_runtime_info() -> dict:
    """
    Возвращает информацию о runtime конфигурации.

    Returns:
        dict: Словарь с текущими настройками
    """
    import shutil
    import sys
    from pathlib import Path

    # Проверяем доступность FFmpeg
    ffmpeg_available = shutil.which(FFMPEG) is not None
    ffprobe_available = shutil.which(FFPROBE) is not None

    # Информация о системе
    try:
        import psutil
        cpu_count = psutil.cpu_count()
        memory_total = psutil.virtual_memory().total
        disk_free = psutil.disk_usage('/').free
    except ImportError:
        cpu_count = os.cpu_count()
        memory_total = None
        disk_free = None

    # Django информация
    django_settings = _get_django_settings()
    django_configured = django_settings is not None

    return {
        'ffmpeg': {
            'ffmpeg_path': FFMPEG,
            'ffprobe_path': FFPROBE,
            'ffmpeg_available': ffmpeg_available,
            'ffprobe_available': ffprobe_available,
            'timeout': FFMPEG_TIMEOUT,
        },
        'processing': {
            'default_ladder_count': len(DEFAULT_LADDER),
            'segment_duration': SEGMENT_DURATION,
            'max_file_size_mb': MAX_FILE_SIZE // (1024 * 1024),
            'process_on_save': PROCESS_ON_SAVE,
        },
        'system': {
            'cpu_count': cpu_count,
            'memory_total_gb': memory_total // (1024 ** 3) if memory_total else None,
            'disk_free_gb': disk_free // (1024 ** 3) if disk_free else None,
            'python_version': sys.version,
        },
        'django': {
            'configured': django_configured,
            'settings_module': os.environ.get('DJANGO_SETTINGS_MODULE'),
        },
        'features': {
            'use_cdn': USE_CDN,
            'gpu_acceleration': ENABLE_GPU_ACCELERATION,
            'experimental': ENABLE_EXPERIMENTAL,
            'verbose_logging': VERBOSE_LOGGING,
        }
    }


def validate_settings() -> list[str]:
    """
    Валидирует текущие настройки и возвращает список проблем.

    Returns:
        list[str]: Список найденных проблем
    """
    issues = []

    # Проверяем FFmpeg
    import shutil
    if not shutil.which(FFMPEG):
        issues.append(f"FFmpeg not found at '{FFMPEG}'. Install FFmpeg or set HLSFIELD_FFMPEG path.")

    if not shutil.which(FFPROBE):
        issues.append(f"FFprobe not found at '{FFPROBE}'. Install FFmpeg or set HLSFIELD_FFPROBE path.")

    # Проверяем лестницу качеств
    try:
        from .fields import validate_ladder
        validate_ladder(DEFAULT_LADDER)
    except Exception as e:
        issues.append(f"Invalid DEFAULT_LADDER: {e}")

    # Проверяем директории
    if TEMP_DIR and not os.path.isdir(TEMP_DIR):
        issues.append(f"TEMP_DIR '{TEMP_DIR}' does not exist")

    if SAVE_FFMPEG_LOGS and not os.path.isdir(os.path.dirname(FFMPEG_LOG_DIR)):
        issues.append(f"FFmpeg log directory parent does not exist: {FFMPEG_LOG_DIR}")

    # Проверяем лимиты
    if MAX_FILE_SIZE <= 0:
        issues.append("MAX_FILE_SIZE must be positive")

    if SEGMENT_DURATION <= 0 or SEGMENT_DURATION > 60:
        issues.append("SEGMENT_DURATION must be between 1 and 60 seconds")

    # Проверяем upload_to функцию
    if DEFAULT_UPLOAD_TO_PATH:
        try:
            from importlib import import_module
            module_path, func_name = DEFAULT_UPLOAD_TO_PATH.rsplit(".", 1)
            module = import_module(module_path)
            func = getattr(module, func_name)
            if not callable(func):
                issues.append(f"DEFAULT_UPLOAD_TO_PATH '{DEFAULT_UPLOAD_TO_PATH}' is not callable")
        except Exception as e:
            issues.append(f"Cannot import DEFAULT_UPLOAD_TO_PATH '{DEFAULT_UPLOAD_TO_PATH}': {e}")

    return issues


# ==============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ==============================================================================

def setup_logging():
    """Настраивает логирование для hlsfield"""

    # Настройка основного логгера
    logger = logging.getLogger('hlsfield')

    if VERBOSE_LOGGING:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Добавляем handler если его нет
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
