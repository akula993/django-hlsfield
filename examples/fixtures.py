import os
from django.core.files.base import ContentFile
from .models import SimpleVideo, HLSVideo
from .utils import get_test_video_content


def create_test_video_instance(model_class, **kwargs):
    """Создает тестовый видео инстанс"""
    defaults = {
        'title': 'Test Video',
    }
    defaults.update(kwargs)

    instance = model_class.objects.create(**defaults)

    # Создаем файл видео
    video_content = get_test_video_content()
    video_file = ContentFile(video_content, name='test.mp4')

    instance.video.save('test.mp4', video_file, save=True)

    return instance


def create_simple_video(**kwargs):
    """Создает SimpleVideo инстанс"""
    return create_test_video_instance(SimpleVideo, **kwargs)


def create_hls_video(**kwargs):
    """Создает HLSVideo инстанс"""
    return create_test_video_instance(HLSVideo, **kwargs)
