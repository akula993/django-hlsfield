# src/hlsfield/apps.py
"""
🎬 Django App конфигурация для django-hlsfield

Настраивает приложение при загрузке Django:
- Проверяет системные требования (FFmpeg)
- Регистрирует сигналы
- Инициализирует настройки
- Выполняет health checks

Автор: akula993
Лицензия: MIT
"""

import logging
import os
import shutil
import sys
from typing import List

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import Error, Warning as CheckWarning, register, Tags

logger = logging.getLogger(__name__)


class HLSFieldConfig(AppConfig):
    """Конфигурация приложения django-hlsfield"""

    default_auto_field = "django.db.models.AutoField"
    name = "hlsfield"
    verbose_name = "HLS Video Fields"

    def ready(self):
        """Вызывается когда приложение готово к использованию"""

        # Импортируем сигналы для их регистрации
        try:
            from . import signals  # noqa
        except ImportError:
            pass

        # Инициализируем настройки логирования
        self._setup_logging()

        # Выводим информацию о версии при debug
        if settings.DEBUG:
            self._print_version_info()

        # Регистрируем system checks
        register(check_ffmpeg_availability, Tags.compatibility)
        register(check_hlsfield_settings, Tags.compatibility)
        register(check_storage_configuration, Tags.compatibility)

        logger.info("django-hlsfield application ready")

    def _setup_logging(self):
        """Настраивает логирование для пакета"""

        from . import defaults

        # Получаем или создаем logger для пакета
        hlsfield_logger = logging.getLogger('hlsfield')

        # Устанавливаем уровень логирования
        if defaults.VERBOSE_LOGGING or settings.DEBUG:
            hlsfield_logger.setLevel(logging.DEBUG)
        else:
            hlsfield_logger.setLevel(logging.INFO)

        # Добавляем handler если нет встроенного
        if not hlsfield_logger.handlers and not logging.getLogger().handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '[%(asctime)s] %(name)s.%(levelname)s: %(message)s',
                datefmt='%H:%M:%S'
            )
            handler.setFormatter(formatter)
            hlsfield_logger.addHandler(handler)

    def _print_version_info(self):
        """Выводит информацию о версии при debug режиме"""

        try:
            from . import __version__
            from . import defaults

            info_lines = [
                f"📹 django-hlsfield v{__version__} loaded",
                f"   FFmpeg: {defaults.FFMPEG}",
                f"   Segments: {defaults.SEGMENT_DURATION}s",
                f"   Qualities: {len(defaults.DEFAULT_LADDER)}",
            ]

            # Проверяем доступность Celery
            try:
                import celery
                info_lines.append(f"   Celery: {celery.__version__}")
            except ImportError:
                info_lines.append("   Celery: not available")

            logger.info("\n".join(info_lines))

        except Exception as e:
            logger.debug(f"Could not print version info: {e}")


# ==============================================================================
# DJANGO SYSTEM CHECKS
# ==============================================================================

def check_ffmpeg_availability(app_configs, **kwargs) -> List[Error]:
    """Проверяет доступность FFmpeg и FFprobe"""

    from . import defaults

    errors = []

    # Проверяем FFmpeg
    if not shutil.which(defaults.FFMPEG):
        errors.append(
            Error(
                'FFmpeg not found',
                hint=(
                    f'FFmpeg binary not found at "{defaults.FFMPEG}". '
                    'Install FFmpeg or set HLSFIELD_FFMPEG setting to correct path.'
                ),
                obj='hlsfield.ffmpeg',
                id='hlsfield.E001',
            )
        )

    # Проверяем FFprobe
    if not shutil.which(defaults.FFPROBE):
        errors.append(
            Error(
                'FFprobe not found',
                hint=(
                    f'FFprobe binary not found at "{defaults.FFPROBE}". '
                    'Install FFmpeg or set HLSFIELD_FFPROBE setting to correct path.'
                ),
                obj='hlsfield.ffprobe',
                id='hlsfield.E002',
            )
        )

    return errors


def check_hlsfield_settings(app_configs, **kwargs) -> List[CheckWarning]:
    """Проверяет настройки django-hlsfield"""

    from . import defaults

    warnings = []

    # Проверяем лестницу качеств
    try:
        from .fields import validate_ladder
        validate_ladder(defaults.DEFAULT_LADDER)
    except Exception as e:
        warnings.append(
            CheckWarning(
                f'Invalid DEFAULT_LADDER configuration: {e}',
                hint='Check HLSFIELD_DEFAULT_LADDER setting format',
                obj='hlsfield.settings',
                id='hlsfield.W001',
            )
        )

    # Проверяем разумность настроек
    if defaults.SEGMENT_DURATION < 2 or defaults.SEGMENT_DURATION > 60:
        warnings.append(
            CheckWarning(
                f'SEGMENT_DURATION ({defaults.SEGMENT_DURATION}s) outside recommended range 2-60s',
                hint='Very short or long segments may cause playback issues',
                obj='hlsfield.settings',
                id='hlsfield.W002',
            )
        )

    # Проверяем максимальный размер файла
    if defaults.MAX_FILE_SIZE > 10 * 1024 ** 3:  # > 10GB
        warnings.append(
            CheckWarning(
                f'MAX_FILE_SIZE ({defaults.MAX_FILE_SIZE / (1024 ** 3):.1f}GB) is very large',
                hint='Large files may cause memory issues during processing',
                obj='hlsfield.settings',
                id='hlsfield.W003',
            )
        )

    return warnings


def check_storage_configuration(app_configs, **kwargs) -> List[CheckWarning]:
    """Проверяет настройки storage"""

    from django.core.exceptions import ImproperlyConfigured
    warnings = []

    try:
        from django.conf import settings
        # Проверяем MEDIA_ROOT если используется локальное хранение
        if hasattr(settings, 'DEFAULT_FILE_STORAGE'):
            if 'FileSystemStorage' in settings.DEFAULT_FILE_STORAGE:
                media_root = getattr(settings, 'MEDIA_ROOT', '')

                if not media_root:
                    warnings.append(
                        CheckWarning(
                            'MEDIA_ROOT not set with FileSystemStorage',
                            hint='Set MEDIA_ROOT for file uploads to work properly',
                            obj='django.settings',
                            id='hlsfield.W004',
                        )
                    )
                elif not os.path.exists(media_root):
                    warnings.append(
                        CheckWarning(
                            f'MEDIA_ROOT directory does not exist: {media_root}',
                            hint='Create the directory or update MEDIA_ROOT setting',
                            obj='django.settings',
                            id='hlsfield.W005',
                        )
                    )
                elif not os.access(media_root, os.W_OK):
                    warnings.append(
                        CheckWarning(
                            f'MEDIA_ROOT is not writable: {media_root}',
                            hint='Check directory permissions',
                            obj='django.settings',
                            id='hlsfield.W006',
                        )
                    )

    except (ImportError, ImproperlyConfigured):
        # Django не настроен
        pass

    return warnings


# ==============================================================================
# УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ
# ==============================================================================

class HLSFieldReadyState:
    """Отслеживает состояние готовности приложения"""

    _ready = False
    _checks_passed = True
    _errors = []

    @classmethod
    def mark_ready(cls):
        """Отмечает приложение как готовое"""
        cls._ready = True

    @classmethod
    def is_ready(cls) -> bool:
        """Проверяет готовность приложения"""
        return cls._ready and cls._checks_passed

    @classmethod
    def add_error(cls, error: str):
        """Добавляет ошибку инициализации"""
        cls._errors.append(error)
        cls._checks_passed = False

    @classmethod
    def get_errors(cls) -> List[str]:
        """Возвращает список ошибок"""
        return cls._errors.copy()


# ==============================================================================
# АВТОМАТИЧЕСКИЕ МИГРАЦИИ (при необходимости)
# ==============================================================================

def auto_create_media_directories():
    """Автоматически создает необходимые директории"""

    if not hasattr(settings, 'MEDIA_ROOT') or not settings.MEDIA_ROOT:
        return

    media_root = Path(settings.MEDIA_ROOT)

    # Создаем базовую структуру директорий
    directories = [
        media_root / 'videos',
        media_root / 'videos' / 'hls',
        media_root / 'videos' / 'dash',
        media_root / 'videos' / 'previews',
    ]

    created = []
    for directory in directories:
        try:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                created.append(str(directory))
        except Exception as e:
            logger.warning(f"Could not create directory {directory}: {e}")

    if created:
        logger.info(f"Created media directories: {', '.join(created)}")


# ==============================================================================
# ИНТЕГРАЦИЯ С DJANGO DEBUG TOOLBAR (опционально)
# ==============================================================================

def setup_debug_toolbar_panels():
    """Добавляет панели в Django Debug Toolbar если доступно"""

    try:
        from debug_toolbar.settings import CONFIG

        # Добавляем нашу панель для мониторинга видео обработки
        if 'hlsfield.debug.VideoProcessingPanel' not in CONFIG['SHOW_TOOLBAR_CALLBACK']:
            pass  # Реализация панели в debug.py

    except ImportError:
        pass  # Debug toolbar не установлен

# ==============================================================================
# СИГНАЛЫ ДЛЯ ИНТЕГРАЦИИ
# ==============================================================================

# В отдельном файле signals.py можно добавить:
# from django.db.models.signals import post_migrate
# from django.dispatch import receiver
#
# @receiver(post_migrate, sender=HLSFieldConfig)
# def create_media_directories(sender, **kwargs):
#     """Создает директории после миграций"""
#     auto_create_media_directories()
