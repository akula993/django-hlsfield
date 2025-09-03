#!/usr/bin/env python
"""
Скрипт для демонстрации работы hlsfield
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', '..test.settings')
django.setup()

from examples.models import SimpleVideo, HLSVideo


def demo_simple_video():
    """Демонстрация SimpleVideo"""
    print("=== Демонстрация SimpleVideo ===")

    video = SimpleVideo.objects.create(title="Демо видео")
    print(f"Создано видео: {video.title}")

    # Показываем поля модели
    print("Поля модели:")
    for field in video._meta.fields:
        print(f"  - {field.name}: {field.get_internal_type()}")

    return video


def demo_hls_video():
    """Демонстрация HLSVideo"""
    print("\n=== Демонстрация HLSVideo ===")

    video = HLSVideo.objects.create(title="Демо HLS видео")
    print(f"Создано HLS видео: {video.title}")

    print("Поля модели:")
    for field in video._meta.fields:
        print(f"  - {field.name}: {field.get_internal_type()}")

    return video


if __name__ == "__main__":
    print("Демонстрация django-hlsfield\n")

    demo_simple_video()
    demo_hls_video()

    print("\nДемонстрация завершена!")
