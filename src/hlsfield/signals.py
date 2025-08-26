# src/hlsfield/signals.py
"""
🎬 Django сигналы для django-hlsfield

Автоматическая обработка событий жизненного цикла видео:
- Создание директорий после миграций
- Очистка файлов при удалении объектов
- Автоматические уведомления
- Обновление статистики
- Интеграция с внешними системами

Автор: akula993
Лицензия: MIT
"""

import logging
import os
import time
from pathlib import Path
from typing import List, Optional

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.db.models.signals import (
    post_migrate, post_save, post_delete,
    pre_save, pre_delete, m2m_changed
)
from django.dispatch import receiver
from django.utils import timezone

from .apps import HLSFieldConfig
from .exceptions import StorageError
from .helpers import get_model_video_fields

logger = logging.getLogger(__name__)


# ==============================================================================
# СИГНАЛЫ МИГРАЦИЙ И ИНИЦИАЛИЗАЦИИ
# ==============================================================================

@receiver(post_migrate, sender=HLSFieldConfig)
def create_media_directories(sender, **kwargs):
    """
    Создает необходимые media директории после миграций.

    Создает базовую структуру папок для видео файлов,
    превью, HLS и DASH контента.
    """
    if not hasattr(settings, 'MEDIA_ROOT') or not settings.MEDIA_ROOT:
        logger.debug("MEDIA_ROOT not configured, skipping directory creation")
        return

    media_root = Path(settings.MEDIA_ROOT)

    # Базовые директории для видео
    directories = [
        media_root / 'videos',
        media_root / 'videos' / 'hls',
        media_root / 'videos' / 'dash',
        media_root / 'videos' / 'adaptive',
        media_root / 'videos' / 'previews',
        media_root / 'videos' / 'temp',  # Для временных файлов
    ]

    # Дополнительные директории из настроек
    extra_dirs = getattr(settings, 'HLSFIELD_EXTRA_DIRECTORIES', [])
    for extra_dir in extra_dirs:
        directories.append(media_root / extra_dir)

    created = []
    failed = []

    for directory in directories:
        try:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                created.append(str(directory))

                # Устанавливаем правильные разрешения
                try:
                    os.chmod(directory, 0o755)
                except OSError:
                    pass  # Игнорируем если не можем изменить права

        except Exception as e:
            failed.append(f"{directory}: {e}")
            logger.warning(f"Could not create directory {directory}: {e}")

    if created:
        logger.info(f"Created media directories: {', '.join(created)}")

    if failed:
        logger.warning(f"Failed to create directories: {', '.join(failed)}")


@receiver(post_migrate)
def cleanup_old_migrations_cache(sender, **kwargs):
    """Очищает кеш после миграций для корректной работы"""

    # Очищаем кеш настроек
    cache_keys = [
        'hlsfield_settings_validated',
        'ffmpeg_availability_checked',
        'video_analytics_*',
    ]

    for pattern in cache_keys:
        if '*' in pattern:
            # Очищаем по паттерну (если поддерживается)
            try:
                cache.delete_many(cache.keys(pattern.replace('*', '*')))
            except (AttributeError, NotImplementedError):
                pass
        else:
            cache.delete(pattern)

    logger.debug("Cleared hlsfield caches after migration")


# ==============================================================================
# СИГНАЛЫ ЖИЗНЕННОГО ЦИКЛА ВИДЕО ОБЪЕКТОВ
# ==============================================================================

@receiver(pre_save)
def video_field_pre_save_handler(sender, instance, **kwargs):
    """
    Обработка перед сохранением объектов с video полями.

    - Подготавливает метаданные
    - Проверяет доступность storage
    - Устанавливает начальные статусы
    """

    # Получаем все video поля модели
    video_fields = get_model_video_fields(sender)

    if not video_fields:
        return  # В модели нет video полей

    for field_name in video_fields:
        field_file = getattr(instance, field_name)

        if not field_file or not field_file.name:
            continue

        # Устанавливаем начальный статус обработки
        if hasattr(instance, 'processing_status') and not getattr(instance, 'processing_status', None):
            setattr(instance, 'processing_status', 'pending')

        # Устанавливаем время загрузки
        if hasattr(instance, 'video_uploaded_at') and not getattr(instance, 'video_uploaded_at', None):
            setattr(instance, 'video_uploaded_at', timezone.now())

        # Генерируем уникальный ID если нужно
        if hasattr(instance, 'video_id') and not getattr(instance, 'video_id', None):
            from .helpers import generate_video_id
            setattr(instance, 'video_id', generate_video_id())


@receiver(post_save)
def video_field_post_save_handler(sender, instance, created, **kwargs):
    """
    Обработка после сохранения объектов с video полями.

    - Обновляет статистику
    - Создает связанные объекты
    - Отправляет уведомления
    """

    video_fields = get_model_video_fields(sender)

    if not video_fields:
        return

    for field_name in video_fields:
        field_file = getattr(instance, field_name)

        if not field_file or not field_file.name:
            continue

        # Обновляем счетчик видео в приложении
        if created:
            _increment_video_counter(sender.__name__)

        # Создаем запись в аналитике если включена
        if _is_analytics_enabled():
            _create_video_analytics_record(instance, field_name, 'uploaded' if created else 'updated')

        # Отправляем уведомление о загрузке
        if created and _should_send_notifications():
            _send_video_upload_notification(instance, field_name)


@receiver(pre_delete)
def video_field_pre_delete_handler(sender, instance, **kwargs):
    """
    Обработка перед удалением объектов с video полями.

    - Сохраняет информацию для аналитики
    - Подготавливает список файлов для удаления
    """

    video_fields = get_model_video_fields(sender)

    if not video_fields:
        return

    # Сохраняем информацию о видео для аналитики
    video_info = {}

    for field_name in video_fields:
        field_file = getattr(instance, field_name)

        if field_file and field_file.name:
            video_info[field_name] = {
                'name': field_file.name,
                'size': _get_file_size_safe(field_file),
                'url': _get_file_url_safe(field_file),
            }

            # Добавляем связанные файлы (HLS, DASH, превью)
            video_info[field_name]['related_files'] = _get_related_files(instance, field_name)

    # Сохраняем во временном атрибуте для post_delete
    setattr(instance, '_hlsfield_deletion_info', video_info)


@receiver(post_delete)
def video_field_post_delete_handler(sender, instance, **kwargs):
    """
    Очистка файлов после удаления объектов с video полями.

    - Удаляет видео файлы из storage
    - Очищает связанные HLS/DASH файлы
    - Обновляет статистику
    """

    # Получаем сохраненную информацию
    deletion_info = getattr(instance, '_hlsfield_deletion_info', {})

    if not deletion_info:
        return

    deleted_files = []
    failed_deletions = []

    for field_name, file_info in deletion_info.items():
        try:
            # Удаляем основной файл
            main_file = file_info['name']
            if main_file and _delete_file_safe(main_file):
                deleted_files.append(main_file)

            # Удаляем связанные файлы
            related_files = file_info.get('related_files', [])
            for related_file in related_files:
                if _delete_file_safe(related_file):
                    deleted_files.append(related_file)
                else:
                    failed_deletions.append(related_file)

        except Exception as e:
            logger.error(f"Error deleting files for {sender.__name__}:{instance.pk}.{field_name}: {e}")
            failed_deletions.append(f"{field_name}: {e}")

    # Логируем результаты
    if deleted_files:
        logger.info(f"Deleted {len(deleted_files)} video files for {sender.__name__}:{instance.pk}")

    if failed_deletions:
        logger.warning(f"Failed to delete {len(failed_deletions)} files: {failed_deletions}")

    # Обновляем статистику
    _decrement_video_counter(sender.__name__)

    # Аналитика удаления
    if _is_analytics_enabled():
        _create_video_analytics_record(instance, None, 'deleted', extra_data=deletion_info)


# ==============================================================================
# СИГНАЛЫ ДЛЯ УВЕДОМЛЕНИЙ И ИНТЕГРАЦИЙ
# ==============================================================================

@receiver(post_save)
def video_processing_status_changed(sender, instance, created, **kwargs):
    """
    Отслеживает изменения статуса обработки видео.

    Отправляет уведомления когда видео готово к просмотру.
    """

    if not hasattr(instance, 'processing_status'):
        return

    # Проверяем изменился ли статус на "готово"
    if not created:
        try:
            # Получаем предыдущую версию из БД
            old_instance = sender.objects.get(pk=instance.pk)
            old_status = getattr(old_instance, 'processing_status', None)
            new_status = getattr(instance, 'processing_status', None)

            # Если статус изменился на готовность
            if old_status != new_status and new_status in ['ready', 'hls_ready', 'dash_ready', 'adaptive_ready']:
                _handle_video_ready_notification(instance, new_status)

        except sender.DoesNotExist:
            pass  # Объект был создан только что
        except Exception as e:
            logger.warning(f"Error checking processing status change: {e}")


@receiver(post_save)
def update_video_statistics(sender, instance, created, **kwargs):
    """
    Обновляет статистику видео при изменениях.

    Ведет счетчики загрузок, обработки, размеров файлов.
    """

    video_fields = get_model_video_fields(sender)

    if not video_fields:
        return

    # Обновляем общую статистику приложения
    try:
        _update_app_statistics(sender, instance, created)
    except Exception as e:
        logger.debug(f"Failed to update statistics: {e}")


# ==============================================================================
# ИНТЕГРАЦИОННЫЕ СИГНАЛЫ
# ==============================================================================

@receiver(post_save)
def integrate_with_search_engines(sender, instance, created, **kwargs):
    """
    Интеграция с поисковыми системами при добавлении видео.

    Отправляет данные в Elasticsearch, Solr и т.д.
    """

    if not _is_search_integration_enabled():
        return

    video_fields = get_model_video_fields(sender)

    if not video_fields:
        return

    try:
        # Подготавливаем данные для индексации
        search_data = _prepare_search_data(instance, video_fields)

        if search_data:
            _send_to_search_engine(search_data, action='index' if created else 'update')

    except Exception as e:
        logger.warning(f"Search engine integration failed: {e}")


@receiver(post_delete)
def remove_from_search_engines(sender, instance, **kwargs):
    """Удаляет видео из поисковых индексов"""

    if not _is_search_integration_enabled():
        return

    video_fields = get_model_video_fields(sender)

    if video_fields:
        try:
            _send_to_search_engine({'id': instance.pk}, action='delete')
        except Exception as e:
            logger.warning(f"Search engine removal failed: {e}")


@receiver(post_save)
def trigger_cdn_purge(sender, instance, created, **kwargs):
    """
    Очищает CDN кеш при обновлении видео.

    Интегрируется с CloudFlare, CloudFront, KeyCDN и другими.
    """

    if not _is_cdn_integration_enabled():
        return

    video_fields = get_model_video_fields(sender)

    if not video_fields:
        return

    urls_to_purge = []

    for field_name in video_fields:
        field_file = getattr(instance, field_name)

        if field_file and field_file.name:
            # Собираем URL для очистки
            urls_to_purge.extend(_get_cdn_urls_for_purge(instance, field_name))

    if urls_to_purge:
        try:
            _purge_cdn_cache(urls_to_purge)
            logger.info(f"Purged {len(urls_to_purge)} URLs from CDN cache")
        except Exception as e:
            logger.warning(f"CDN cache purge failed: {e}")


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def _increment_video_counter(model_name: str):
    """Увеличивает счетчик видео для модели"""
    cache_key = f"hlsfield_video_count_{model_name}"

    try:
        current = cache.get(cache_key, 0)
        cache.set(cache_key, current + 1, 86400)  # 24 часа
    except Exception:
        pass


def _decrement_video_counter(model_name: str):
    """Уменьшает счетчик видео для модели"""
    cache_key = f"hlsfield_video_count_{model_name}"

    try:
        current = cache.get(cache_key, 0)
        cache.set(cache_key, max(0, current - 1), 86400)
    except Exception:
        pass


def _get_file_size_safe(field_file) -> Optional[int]:
    """Безопасно получает размер файла"""
    try:
        return field_file.size
    except Exception:
        return None


def _get_file_url_safe(field_file) -> Optional[str]:
    """Безопасно получает URL файла"""
    try:
        return field_file.url
    except Exception:
        return None


def _get_related_files(instance, field_name: str) -> List[str]:
    """Получает список связанных файлов (HLS, DASH, превью)"""
    related_files = []

    field = instance._meta.get_field(field_name)

    # HLS плейлист
    hls_field = getattr(field, 'hls_playlist_field', None)
    if hls_field:
        hls_path = getattr(instance, hls_field, None)
        if hls_path:
            related_files.append(hls_path)
            # Добавляем предположительные HLS сегменты
            related_files.extend(_get_hls_segments(hls_path))

    # DASH манифест
    dash_field = getattr(field, 'dash_manifest_field', None)
    if dash_field:
        dash_path = getattr(instance, dash_field, None)
        if dash_path:
            related_files.append(dash_path)
            # Добавляем предположительные DASH сегменты
            related_files.extend(_get_dash_segments(dash_path))

    # Превью
    preview_field = getattr(field, 'preview_field', None)
    if preview_field:
        preview_path = getattr(instance, preview_field, None)
        if preview_path:
            related_files.append(preview_path)

    return related_files


def _get_hls_segments(playlist_path: str) -> List[str]:
    """Получает список HLS сегментов по пути к плейлисту"""
    segments = []

    try:
        # Предполагаем структуру: path/to/hls/master.m3u8
        base_dir = str(Path(playlist_path).parent)

        # Добавляем типичные варианты качества
        for quality in ['v240', 'v360', 'v480', 'v720', 'v1080']:
            segments.append(f"{base_dir}/{quality}/index.m3u8")

            # Сегменты (примерно 5-20 файлов)
            for i in range(20):
                segments.append(f"{base_dir}/{quality}/seg_{i:04d}.ts")

    except Exception:
        pass

    return segments


def _get_dash_segments(manifest_path: str) -> List[str]:
    """Получает список DASH сегментов по пути к манифесту"""
    segments = []

    try:
        base_dir = str(Path(manifest_path).parent)

        # DASH init и media сегменты
        for i in range(5):  # Примерно 5 представлений
            segments.append(f"{base_dir}/init-{i}.m4s")

            # Media сегменты
            for j in range(20):
                segments.append(f"{base_dir}/chunk-{i}-{j:05d}.m4s")

    except Exception:
        pass

    return segments


def _delete_file_safe(file_path: str) -> bool:
    """Безопасно удаляет файл из storage"""
    try:
        from django.core.files.storage import default_storage

        if default_storage.exists(file_path):
            default_storage.delete(file_path)
            return True
    except Exception as e:
        logger.debug(f"Could not delete file {file_path}: {e}")

    return False


def _is_analytics_enabled() -> bool:
    """Проверяет включена ли аналитика"""
    return getattr(settings, 'HLSFIELD_ENABLE_ANALYTICS', False)


def _should_send_notifications() -> bool:
    """Проверяет нужно ли отправлять уведомления"""
    return getattr(settings, 'HLSFIELD_SEND_NOTIFICATIONS', False)


def _is_search_integration_enabled() -> bool:
    """Проверяет включена ли интеграция с поиском"""
    return getattr(settings, 'HLSFIELD_SEARCH_INTEGRATION', False)


def _is_cdn_integration_enabled() -> bool:
    """Проверяет включена ли интеграция с CDN"""
    return getattr(settings, 'HLSFIELD_CDN_INTEGRATION', False)


def _create_video_analytics_record(instance, field_name: Optional[str], action: str, extra_data: dict = None):
    """Создает запись в аналитике"""
    try:
        from .views import VideoEvent

        VideoEvent.objects.create(
            video_id=str(instance.pk),
            session_id='system',
            event_type=action,
            timestamp=timezone.now(),
            additional_data=extra_data or {}
        )
    except Exception as e:
        logger.debug(f"Could not create analytics record: {e}")


def _send_video_upload_notification(instance, field_name: str):
    """Отправляет уведомление о загрузке видео"""
    try:
        # Пример интеграции с Django channels или email
        notification_data = {
            'type': 'video_uploaded',
            'instance_id': instance.pk,
            'model': instance._meta.label,
            'field_name': field_name,
            'timestamp': timezone.now().isoformat(),
        }

        # Здесь можно добавить отправку в Slack, Discord, email и т.д.
        logger.info(f"Video uploaded notification: {notification_data}")

    except Exception as e:
        logger.warning(f"Failed to send upload notification: {e}")


def _handle_video_ready_notification(instance, status: str):
    """Обрабатывает уведомления о готовности видео"""
    try:
        # Можно отправить email пользователю
        if hasattr(instance, 'user') and instance.user:
            _send_video_ready_email(instance.user, instance, status)

        # Уведомление в админку
        _send_admin_notification(f"Video {instance.pk} is {status}")

    except Exception as e:
        logger.warning(f"Failed to send ready notification: {e}")


def _send_video_ready_email(user, instance, status: str):
    """Отправляет email о готовности видео"""
    try:
        from django.core.mail import send_mail
        from django.template.loader import render_to_string

        subject = f"Your video is ready!"
        message = render_to_string('hlsfield/emails/video_ready.html', {
            'user': user,
            'instance': instance,
            'status': status,
        })

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )

    except Exception as e:
        logger.debug(f"Could not send video ready email: {e}")


def _send_admin_notification(message: str):
    """Отправляет уведомление администраторам"""
    try:
        from django.core.mail import mail_admins
        mail_admins(
            subject="HLSField Notification",
            message=message,
            fail_silently=True,
        )
    except Exception:
        pass


def _update_app_statistics(sender, instance, created: bool):
    """Обновляет статистику приложения"""
    stats_key = "hlsfield_app_stats"

    try:
        stats = cache.get(stats_key, {
            'total_videos': 0,
            'total_processed': 0,
            'last_update': time.time(),
        })

        if created:
            stats['total_videos'] += 1

        if hasattr(instance, 'processing_status'):
            status = getattr(instance, 'processing_status')
            if status in ['ready', 'hls_ready', 'dash_ready', 'adaptive_ready']:
                stats['total_processed'] += 1

        stats['last_update'] = time.time()
        cache.set(stats_key, stats, 86400)  # 24 часа

    except Exception:
        pass


def _prepare_search_data(instance, video_fields: List[str]) -> dict:
    """Подготавливает данные для поисковых систем"""
    search_data = {
        'id': instance.pk,
        'model': instance._meta.label,
        'timestamp': timezone.now().isoformat(),
    }

    # Добавляем основную информацию
    for field in ['title', 'description', 'tags']:
        if hasattr(instance, field):
            search_data[field] = getattr(instance, field)

    # Добавляем информацию о видео
    for field_name in video_fields:
        try:
            from .helpers import get_video_field_metadata
            metadata = get_video_field_metadata(instance, field_name)
            search_data[f'{field_name}_metadata'] = metadata
        except Exception:
            pass

    return search_data


def _send_to_search_engine(data: dict, action: str):
    """Отправляет данные в поисковую систему"""
    # Заглушка для интеграции с Elasticsearch и т.д.
    logger.debug(f"Search engine {action}: {data}")


def _get_cdn_urls_for_purge(instance, field_name: str) -> List[str]:
    """Получает URL для очистки CDN кеша"""
    urls = []

    try:
        from .helpers import get_video_field_metadata
        metadata = get_video_field_metadata(instance, field_name)

        # Добавляем основные URL
        for url_key in ['url', 'hls_url', 'dash_url', 'preview_url']:
            if url_key in metadata:
                urls.append(metadata[url_key])

    except Exception:
        pass

    return urls


def _purge_cdn_cache(urls: List[str]):
    """Очищает кеш CDN для указанных URL"""
    # Заглушка для интеграции с CloudFlare, CloudFront и т.д.
    logger.debug(f"CDN purge: {urls}")


# ==============================================================================
# УСЛОВНЫЕ СИГНАЛЫ (активируются через настройки)
# ==============================================================================

# Дополнительные сигналы можно активировать через настройки
if getattr(settings, 'HLSFIELD_ENABLE_WEBHOOKS', False):

    @receiver(post_save)
    def send_webhooks(sender, instance, created, **kwargs):
        """Отправляет webhook уведомления"""
        video_fields = get_model_video_fields(sender)

        if video_fields:
            webhook_url = getattr(settings, 'HLSFIELD_WEBHOOK_URL', None)
            if webhook_url:
                try:
                    import requests

                    payload = {
                        'action': 'created' if created else 'updated',
                        'model': sender.__name__,
                        'instance_id': instance.pk,
                        'timestamp': timezone.now().isoformat(),
                    }

                    requests.post(webhook_url, json=payload, timeout=5)

                except Exception as e:
                    logger.warning(f"Webhook failed: {e}")


# ==============================================================================
# СИГНАЛ ДЛЯ ОЧИСТКИ КЕША
# ==============================================================================

@receiver([post_save, post_delete])
def invalidate_related_caches(sender, instance, **kwargs):
    """Очищает связанные кеши при изменении объектов с видео"""

    video_fields = get_model_video_fields(sender)

    if not video_fields:
        return

    # Очищаем кеши связанные с этим объектом
    cache_patterns = [
        f"video_metadata_{instance.pk}",
        f"video_stats_{instance.pk}",
        f"video_analytics_{instance.pk}",
        f"hlsfield_video_count_{sender.__name__}",
    ]

    for pattern in cache_patterns:
        try:
            cache.delete(pattern)
        except Exception:
            pass


# ==============================================================================
# ДОКУМЕНТАЦИЯ И НАСТРОЙКИ
# ==============================================================================

"""
Настройки сигналов в settings.py:

HLSFIELD_ENABLE_ANALYTICS = True          # Включить аналитику
HLSFIELD_SEND_NOTIFICATIONS = True        # Отправлять уведомления
HLSFIELD_SEARCH_INTEGRATION = True        # Интеграция с поиском
HLSFIELD_CDN_INTEGRATION = True           # Интеграция с CDN
HLSFIELD_ENABLE_WEBHOOKS = True           # Webhook уведомления
HLSFIELD_WEBHOOK_URL = "https://..."      # URL для webhook

HLSFIELD_EXTRA_DIRECTORIES = [            # Дополнительные директории
    'videos/backup',
    'videos/temp',
]

# Email настройки для уведомлений
DEFAULT_FROM_EMAIL = 'noreply@example.com'
ADMINS = [('Admin', 'admin@example.com')]
"""
