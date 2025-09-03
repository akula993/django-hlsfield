"""
🛠️ Вспомогательные функции для django-hlsfield

Содержит utility функции для работы с видео:
- Генерация upload_to путей
- Создание уникальных идентификаторов
- Работа с метаданными
- Форматирование времени и размеров
- Интеграция с Django

Автор: akula993
Лицензия: MIT
"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from django.core.files.base import File
from django.core.files.storage import default_storage
from django.utils.text import slugify


# ==============================================================================
# ГЕНЕРАЦИЯ ПУТЕЙ ДЛЯ UPLOAD_TO
# ==============================================================================

def video_upload_to(instance, filename: str) -> str:
    """
    Стандартная функция upload_to для видео файлов.

    Создает структуру: videos/{uuid8}/{filename}

    Args:
        instance: Экземпляр модели
        filename: Оригинальное имя файла

    Returns:
        str: Путь для сохранения файла

    Example:
        video = VideoField(upload_to=video_upload_to)
    """
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]  # 8-символьный UUID
    clean_filename = slugify(stem)[:50] + ext.lower()  # Безопасное имя
    return f"videos/{folder}/{clean_filename}"


def date_based_upload_to(instance, filename: str) -> str:
    """
    Upload_to на основе даты создания.

    Создает структуру: videos/2025/01/15/{uuid4}/{filename}

    Args:
        instance: Экземпляр модели
        filename: Оригинальное имя файла

    Returns:
        str: Путь с датой
    """
    now = datetime.now()
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]
    clean_filename = slugify(stem)[:50] + ext.lower()

    return f"videos/{now.year:04d}/{now.month:02d}/{now.day:02d}/{folder}/{clean_filename}"


def user_based_upload_to(instance, filename: str) -> str:
    """
    Upload_to на основе пользователя.

    Создает структуру: videos/users/{user_id}/{uuid8}/{filename}

    Args:
        instance: Экземпляр модели с user или owner полем
        filename: Оригинальное имя файла

    Returns:
        str: Путь с пользователем
    """
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]
    clean_filename = slugify(stem)[:50] + ext.lower()

    # Пытаемся получить ID пользователя из разных полей
    user_id = "anonymous"

    if hasattr(instance, 'user') and instance.user:
        user_id = str(instance.user.id)
    elif hasattr(instance, 'owner') and instance.owner:
        user_id = str(instance.owner.id)
    elif hasattr(instance, 'created_by') and instance.created_by:
        user_id = str(instance.created_by.id)

    return f"videos/users/{user_id}/{folder}/{clean_filename}"


def content_type_upload_to(instance, filename: str) -> str:
    """
    Upload_to на основе типа контента.

    Создает структуру: videos/{content_type}/{uuid8}/{filename}
    Где content_type может быть: movies, lessons, ads, etc.

    Args:
        instance: Экземпляр модели
        filename: Оригинальное имя файла

    Returns:
        str: Путь с типом контента
    """
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]
    clean_filename = slugify(stem)[:50] + ext.lower()

    # Определяем тип контента из модели
    content_type = "general"

    if hasattr(instance, 'content_type') and instance.content_type:
        content_type = slugify(instance.content_type)
    elif hasattr(instance, 'category') and instance.category:
        content_type = slugify(instance.category)
    else:
        # Определяем по имени модели
        model_name = instance._meta.model_name.lower()
        content_type = {
            'movie': 'movies',
            'lesson': 'lessons',
            'tutorial': 'tutorials',
            'advertisement': 'ads',
            'course': 'courses',
        }.get(model_name, 'general')

    return f"videos/{content_type}/{folder}/{clean_filename}"


def get_video_upload_path(instance=None, filename: str = None,
                          strategy: str = "uuid") -> str:
    """
    Универсальная функция для генерации upload путей.

    Args:
        instance: Экземпляр модели (может быть None)
        filename: Имя файла (может быть None для генерации папки)
        strategy: Стратегия именования ('uuid', 'date', 'user', 'content')

    Returns:
        str: Сгенерированный путь

    Example:
        path = get_video_upload_path(strategy='date')
        video = VideoField(upload_to=lambda i, f: get_video_upload_path(i, f, 'user'))
    """

    strategies = {
        'uuid': video_upload_to,
        'date': date_based_upload_to,
        'user': user_based_upload_to,
        'content': content_type_upload_to,
    }

    if strategy not in strategies:
        strategy = 'uuid'

    upload_func = strategies[strategy]

    # Если filename не предоставлен, генерируем временное имя
    if filename is None:
        filename = f"temp_{uuid.uuid4().hex[:8]}.mp4"

    return upload_func(instance, filename)


# ==============================================================================
# ГЕНЕРАЦИЯ УНИКАЛЬНЫХ ИДЕНТИФИКАТОРОВ
# ==============================================================================

def generate_video_id(length: int = 8) -> str:
    """
    Генерирует короткий уникальный ID для видео.

    Args:
        length: Длина ID (по умолчанию 8 символов)

    Returns:
        str: Уникальный ID

    Example:
        video_id = generate_video_id()  # "a1b2c3d4"
    """
    return uuid.uuid4().hex[:length]


def generate_secure_video_id(seed_data: Union[str, bytes] = None) -> str:
    """
    Генерирует криптографически стойкий ID для видео.

    Args:
        seed_data: Дополнительные данные для генерации

    Returns:
        str: Безопасный ID
    """
    if seed_data is None:
        seed_data = f"{uuid.uuid4()}{datetime.now().isoformat()}"

    if isinstance(seed_data, str):
        seed_data = seed_data.encode('utf-8')

    return hashlib.sha256(seed_data).hexdigest()[:16]


def generate_content_hash(file_path: Union[str, Path], chunk_size: int = 8192) -> str:
    """
    Генерирует хэш содержимого видеофайла.

    Args:
        file_path: Путь к файлу
        chunk_size: Размер чанка для чтения

    Returns:
        str: SHA256 хэш файла
    """
    hash_sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hash_sha256.update(chunk)

    return hash_sha256.hexdigest()


# ==============================================================================
# РАБОТА С МЕТАДАННЫМИ
# ==============================================================================

def extract_filename_metadata(filename: str) -> Dict[str, Any]:
    """
    Извлекает метаданные из имени файла.

    Args:
        filename: Имя файла

    Returns:
        dict: Извлеченные метаданные

    Example:
        meta = extract_filename_metadata("movie_1920x1080_30fps.mp4")
        # {'width': 1920, 'height': 1080, 'fps': 30, 'title': 'movie'}
    """
    metadata = {'title': '', 'width': None, 'height': None, 'fps': None}

    # Удаляем расширение
    stem = Path(filename).stem

    # Ищем разрешение (1920x1080, 1280x720, etc.)
    import re
    resolution_match = re.search(r'(\d{3,4})x(\d{3,4})', stem)
    if resolution_match:
        metadata['width'] = int(resolution_match.group(1))
        metadata['height'] = int(resolution_match.group(2))
        # Удаляем из названия
        stem = re.sub(r'_?\d{3,4}x\d{3,4}_?', '_', stem)

    # Ищем FPS (30fps, 60fps, etc.)
    fps_match = re.search(r'(\d+)fps', stem, re.IGNORECASE)
    if fps_match:
        metadata['fps'] = int(fps_match.group(1))
        stem = re.sub(r'_?\d+fps_?', '_', stem, flags=re.IGNORECASE)

    # Очищаем название
    title = re.sub(r'[_\-]+', ' ', stem).strip()
    title = re.sub(r'\s+', ' ', title)  # Убираем множественные пробелы
    metadata['title'] = title.title() if title else 'Untitled'

    return metadata


def combine_video_metadata(*metadata_dicts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Объединяет несколько словарей метаданных с приоритетом.

    Args:
        *metadata_dicts: Словари метаданных (приоритет по порядку)

    Returns:
        dict: Объединенные метаданные
    """
    combined = {}

    for meta in reversed(metadata_dicts):  # Обратный порядок для правильного приоритета
        combined.update({k: v for k, v in meta.items() if v is not None})

    return combined


def sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очищает и валидирует метаданные.

    Args:
        metadata: Исходные метаданные

    Returns:
        dict: Очищенные метаданные
    """
    sanitized = {}

    # Безопасные числовые поля
    numeric_fields = ['width', 'height', 'duration', 'fps', 'bitrate']
    for field in numeric_fields:
        if field in metadata:
            try:
                value = float(metadata[field])
                if value > 0 and value < 1e6:  # Разумные пределы
                    sanitized[field] = int(value) if field != 'duration' else value
            except (ValueError, TypeError):
                pass

    # Безопасные строковые поля
    string_fields = ['title', 'codec', 'format']
    for field in string_fields:
        if field in metadata and isinstance(metadata[field], str):
            # Очищаем от потенциально опасных символов
            clean_value = re.sub(r'[<>"\']', '', str(metadata[field]))[:100]
            if clean_value.strip():
                sanitized[field] = clean_value.strip()

    return sanitized


# ==============================================================================
# ФОРМАТИРОВАНИЕ И ПРЕДСТАВЛЕНИЕ
# ==============================================================================

def format_duration(seconds: Union[int, float]) -> str:
    """
    Форматирует длительность в человекочитаемый вид.

    Args:
        seconds: Длительность в секундах

    Returns:
        str: Отформатированная строка

    Example:
        format_duration(3661)  # "1:01:01"
        format_duration(125)   # "2:05"
    """
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "0:00"

    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_file_size(bytes_size: int) -> str:
    """
    Форматирует размер файла в человекочитаемый вид.

    Args:
        bytes_size: Размер в байтах

    Returns:
        str: Отформатированная строка

    Example:
        format_file_size(1536000)  # "1.5 MB"
    """
    if bytes_size < 0:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(bytes_size)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def format_bitrate(bps: int) -> str:
    """
    Форматирует битрейт в человекочитаемый вид.

    Args:
        bps: Битрейт в битах в секунду

    Returns:
        str: Отформатированный битрейт

    Example:
        format_bitrate(2500000)  # "2.5 Mbps"
    """
    if bps < 0:
        return "0 bps"

    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} Mbps"
    elif bps >= 1_000:
        return f"{bps / 1_000:.0f} Kbps"
    else:
        return f"{bps} bps"


def format_video_info(metadata: Dict[str, Any]) -> str:
    """
    Форматирует информацию о видео в краткую строку.

    Args:
        metadata: Метаданные видео

    Returns:
        str: Краткая информация

    Example:
        info = format_video_info(meta)  # "1920×1080, 5:23, 2.5 Mbps"
    """
    parts = []

    # Разрешение
    if 'width' in metadata and 'height' in metadata:
        parts.append(f"{metadata['width']}×{metadata['height']}")

    # Длительность
    if 'duration' in metadata:
        parts.append(format_duration(metadata['duration']))

    # Битрейт
    if 'bitrate' in metadata:
        parts.append(format_bitrate(metadata['bitrate']))

    # FPS
    if 'fps' in metadata:
        parts.append(f"{metadata['fps']} fps")

    return ", ".join(parts) if parts else "No info"


# ==============================================================================
# РАБОТА С ФАЙЛАМИ И STORAGE
# ==============================================================================

def ensure_directory_exists(path: Union[str, Path], storage=None) -> bool:
    """
    Гарантирует существование директории.

    Args:
        path: Путь к директории
        storage: Django storage (по умолчанию default_storage)

    Returns:
        bool: True если директория создана/существует
    """
    if storage is None:
        storage = default_storage

    path_str = str(path)

    try:
        # Для локального storage
        if hasattr(storage, 'path'):
            full_path = Path(storage.path(path_str))
            full_path.mkdir(parents=True, exist_ok=True)
            return True

        # Для облачных storage - пытаемся сохранить пустой файл для создания "папки"
        test_file = f"{path_str.rstrip('/')}/._directory_marker"
        if not storage.exists(test_file):
            storage.save(test_file, File(open('/dev/null', 'rb')))

        return True

    except Exception:
        return False


def clean_filename(filename: str, max_length: int = 100) -> str:
    """
    Очищает имя файла от небезопасных символов.

    Args:
        filename: Исходное имя файла
        max_length: Максимальная длина

    Returns:
        str: Безопасное имя файла
    """
    # Разделяем имя и расширение
    stem = Path(filename).stem
    suffix = Path(filename).suffix

    # Очищаем имя
    clean_stem = re.sub(r'[^\w\s\-_.]', '', stem)  # Только безопасные символы
    clean_stem = re.sub(r'[-\s_]+', '_', clean_stem)  # Объединяем разделители
    clean_stem = clean_stem.strip('_.')  # Убираем с краев

    # Ограничиваем длину
    max_stem_length = max_length - len(suffix)
    if len(clean_stem) > max_stem_length:
        clean_stem = clean_stem[:max_stem_length].rstrip('_.')

    # Если имя получилось пустым, генерируем случайное
    if not clean_stem:
        clean_stem = f"file_{uuid.uuid4().hex[:8]}"

    return clean_stem + suffix.lower()


def get_file_extension_info(filename: str) -> Dict[str, Any]:
    """
    Получает информацию о файле по расширению.

    Args:
        filename: Имя файла

    Returns:
        dict: Информация о типе файла
    """
    extension = Path(filename).suffix.lower()

    # Карта расширений и их характеристик
    extension_map = {
        '.mp4': {
            'type': 'video/mp4',
            'container': 'MP4',
            'streaming_friendly': True,
            'quality': 'high',
            'compression': 'good',
        },
        '.mov': {
            'type': 'video/quicktime',
            'container': 'QuickTime',
            'streaming_friendly': True,
            'quality': 'high',
            'compression': 'variable',
        },
        '.avi': {
            'type': 'video/x-msvideo',
            'container': 'AVI',
            'streaming_friendly': False,
            'quality': 'variable',
            'compression': 'variable',
        },
        '.webm': {
            'type': 'video/webm',
            'container': 'WebM',
            'streaming_friendly': True,
            'quality': 'high',
            'compression': 'excellent',
        },
        '.mkv': {
            'type': 'video/x-matroska',
            'container': 'Matroska',
            'streaming_friendly': False,
            'quality': 'high',
            'compression': 'variable',
        },
    }

    info = extension_map.get(extension, {
        'type': 'video/unknown',
        'container': 'Unknown',
        'streaming_friendly': False,
        'quality': 'unknown',
        'compression': 'unknown',
    })

    info['extension'] = extension
    return info


# ==============================================================================
# ИНТЕГРАЦИЯ С DJANGO
# ==============================================================================

def get_model_video_fields(model_class) -> List[str]:
    """
    Получает список всех video полей в модели.

    Args:
        model_class: Класс Django модели

    Returns:
        list: Список имен video полей
    """
    from .fields import VideoField, HLSVideoField, DASHVideoField, AdaptiveVideoField

    video_field_types = (VideoField, HLSVideoField, DASHVideoField, AdaptiveVideoField)
    video_fields = []

    for field in model_class._meta.fields:
        if isinstance(field, video_field_types):
            video_fields.append(field.name)

    return video_fields


def get_video_field_metadata(instance, field_name: str) -> Dict[str, Any]:
    """
    Получает все доступные метаданные для video поля.

    Args:
        instance: Экземпляр модели
        field_name: Имя video поля

    Returns:
        dict: Все метаданные поля
    """
    field = instance._meta.get_field(field_name)
    video_file = getattr(instance, field_name)

    if not video_file:
        return {}

    metadata = {}

    # Основная информация
    if hasattr(video_file, 'name') and video_file.name:
        metadata['filename'] = Path(video_file.name).name
        metadata['path'] = video_file.name

    # URL для доступа
    if hasattr(video_file, 'url'):
        try:
            metadata['url'] = video_file.url
        except Exception:
            pass

    # Метаданные из модели или файлов
    if hasattr(video_file, 'metadata'):
        try:
            file_metadata = video_file.metadata()
            metadata.update(file_metadata)
        except Exception:
            pass

    # HLS/DASH URLs
    if hasattr(video_file, 'master_url'):
        try:
            hls_url = video_file.master_url()
            if hls_url:
                metadata['hls_url'] = hls_url
        except Exception:
            pass

    if hasattr(video_file, 'dash_url'):
        try:
            dash_url = video_file.dash_url()
            if dash_url:
                metadata['dash_url'] = dash_url
        except Exception:
            pass

    # Превью
    if hasattr(video_file, 'preview_url'):
        try:
            preview_url = video_file.preview_url()
            if preview_url:
                metadata['preview_url'] = preview_url
        except Exception:
            pass

    return metadata


def create_video_upload_to_function(strategy: str = 'uuid', **kwargs):
    """
    Фабрика для создания upload_to функций.

    Args:
        strategy: Стратегия именования
        **kwargs: Дополнительные параметры

    Returns:
        callable: Функция upload_to

    Example:
        upload_func = create_video_upload_to_function('user')
        video = VideoField(upload_to=upload_func)
    """

    def upload_to_function(instance, filename):
        return get_video_upload_path(instance, filename, strategy)

    upload_to_function.strategy = strategy
    upload_to_function.kwargs = kwargs

    return upload_to_function


# ==============================================================================
# ЭКСПОРТ ФУНКЦИЙ
# ==============================================================================

__all__ = [
    # Upload_to функции
    'video_upload_to',
    'date_based_upload_to',
    'user_based_upload_to',
    'content_type_upload_to',
    'get_video_upload_path',
    'create_video_upload_to_function',

    # Генерация ID
    'generate_video_id',
    'generate_secure_video_id',
    'generate_content_hash',

    # Метаданные
    'extract_filename_metadata',
    'combine_video_metadata',
    'sanitize_metadata',

    # Форматирование
    'format_duration',
    'format_file_size',
    'format_bitrate',
    'format_video_info',

    # Файлы
    'ensure_directory_exists',
    'clean_filename',
    'get_file_extension_info',

    # Django интеграция
    'get_model_video_fields',
    'get_video_field_metadata',
]
