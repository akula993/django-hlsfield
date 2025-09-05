# debug_hlsfield.py
"""
Скрипт для диагностики проблем с путями в django-hlsfield
"""

import os
import django
from django.conf import settings

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'videotest.settings')
django.setup()

from django.core.files.storage import default_storage
from videotest.models import Video  # Замените на вашу модель
from hlsfield.tasks import _get_base_key
from hlsfield import defaults


def debug_storage_paths():
    """Диагностика путей storage"""
    print("=== ДИАГНОСТИКА STORAGE ===")
    print(f"MEDIA_ROOT: {getattr(settings, 'MEDIA_ROOT', 'NOT SET')}")
    print(f"DEFAULT_FILE_STORAGE: {getattr(settings, 'DEFAULT_FILE_STORAGE', 'default')}")
    print(f"Storage class: {default_storage.__class__.__name__}")
    print(f"Storage location: {getattr(default_storage, 'location', 'NOT SET')}")
    print()


def debug_hlsfield_settings():
    """Диагностика настроек hlsfield"""
    print("=== НАСТРОЙКИ HLSFIELD ===")
    print(f"HLS_SUBDIR: {defaults.HLS_SUBDIR}")
    print(f"DASH_SUBDIR: {defaults.DASH_SUBDIR}")
    print(f"ADAPTIVE_SUBDIR: {defaults.ADAPTIVE_SUBDIR}")
    print(f"SIDECAR_LAYOUT: {defaults.SIDECAR_LAYOUT}")
    print()


def debug_path_generation():
    """Тестирование генерации путей"""
    print("=== ГЕНЕРАЦИЯ ПУТЕЙ ===")

    # Тестовые имена файлов
    test_names = [
        "videos/12345678/test.mp4",
        "test.mp4",
        "videos/folder/subfolder/video.mp4"
    ]

    for name in test_names:
        print(f"Исходное имя: {name}")
        hls_key = _get_base_key(name, defaults.HLS_SUBDIR)
        dash_key = _get_base_key(name, defaults.DASH_SUBDIR)
        adaptive_key = _get_base_key(name, defaults.ADAPTIVE_SUBDIR)

        print(f"  HLS key: {hls_key}")
        print(f"  DASH key: {dash_key}")
        print(f"  Adaptive key: {adaptive_key}")
        print()


def debug_existing_video():
    """Диагностика существующего видео"""
    print("=== СУЩЕСТВУЮЩИЕ ВИДЕО ===")

    try:
        videos = Video.objects.all()[:3]  # Первые 3 видео

        if not videos:
            print("Видео не найдены в базе данных")
            return

        for video in videos:
            print(f"Video ID: {video.id}")

            # Проверяем каждое поле
            if hasattr(video, 'video') and video.video:
                print(f"  video.name: {video.video.name}")

                # Проверяем storage путь
                try:
                    storage_path = video.video.storage.path(video.video.name)
                    print(f"  storage path: {storage_path}")
                    print(f"  file exists: {os.path.exists(storage_path)}")
                except Exception as e:
                    print(f"  storage path error: {e}")

                # Проверяем URL
                try:
                    url = video.video.url
                    print(f"  URL: {url}")
                except Exception as e:
                    print(f"  URL error: {e}")

                # Проверяем HLS/DASH поля если есть
                if hasattr(video, 'hls_master') and video.hls_master:
                    print(f"  HLS master: {video.hls_master}")

                if hasattr(video, 'dash_manifest') and video.dash_manifest:
                    print(f"  DASH manifest: {video.dash_manifest}")

            print()

    except Exception as e:
        print(f"Ошибка при работе с видео: {e}")


def test_storage_save():
    """Тест сохранения в storage"""
    print("=== ТЕСТ STORAGE SAVE ===")

    # Создаем тестовый файл
    test_content = b"test content"

    test_paths = [
        "test/simple.txt",
        "videos/12345678/adaptive/test.txt",
        "videos/folder/hls/test.txt"
    ]

    for test_path in test_paths:
        try:
            from io import BytesIO
            file_obj = BytesIO(test_content)

            saved_name = default_storage.save(test_path, file_obj)
            print(f"Тест путь: {test_path}")
            print(f"Сохранен как: {saved_name}")

            # Проверяем существование
            exists = default_storage.exists(saved_name)
            print(f"Существует: {exists}")

            # Получаем полный путь
            try:
                full_path = default_storage.path(saved_name)
                print(f"Полный путь: {full_path}")
                print(f"Реально существует: {os.path.exists(full_path)}")
            except:
                print("Не удается получить полный путь (возможно S3)")

            # Удаляем тестовый файл
            default_storage.delete(saved_name)
            print("Тестовый файл удален")
            print()

        except Exception as e:
            print(f"Ошибка при тесте {test_path}: {e}")
            print()


if __name__ == "__main__":
    print("🔍 ДИАГНОСТИКА DJANGO-HLSFIELD")
    print("=" * 50)

    debug_storage_paths()
    debug_hlsfield_settings()
    debug_path_generation()
    debug_existing_video()
    test_storage_save()

    print("Диагностика завершена!")
