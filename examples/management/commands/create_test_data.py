from django.core.management.base import BaseCommand
from examples.fixtures import create_simple_video, create_hls_video


class Command(BaseCommand):
    help = 'Создает тестовые данные для examples приложения'

    def handle(self, *args, **options):
        self.stdout.write('Создание тестовых данных...')

        # Создаем тестовые видео
        simple_video = create_simple_video(title='Тестовое простое видео')
        hls_video = create_hls_video(title='Тестовое HLS видео')

        self.stdout.write(
            self.style.SUCCESS(
                f'Созданы тестовые данные: {simple_video}, {hls_video}'
            )
        )
