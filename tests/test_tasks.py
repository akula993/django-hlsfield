from unittest.mock import patch, MagicMock
from django.test import TestCase
from hlsfield.tasks import build_hls_for_field_sync, build_dash_for_field_sync


class TasksTest(TestCase):
    """Тесты для Celery задач"""

    @patch('hlsfield.utils.transcode_hls_variants')
    @patch('hlsfield.utils.pull_to_local')
    @patch('hlsfield.utils.save_tree_to_storage')
    def test_build_hls_task(self, mock_save_tree, mock_pull, mock_transcode):
        """Тест задачи создания HLS"""

        # Настройка моков
        mock_pull.return_value = Path("/tmp/input.mp4")
        mock_transcode.return_value = Path("/tmp/hls/master.m3u8")
        mock_save_tree.return_value = ["hls/master.m3u8"]

        # Создаем тестовую модель
        video_obj = TestHLSVideoModel.objects.create(
            title="Task Test",
            video=self.create_uploaded_file()
        )

        # Запускаем задачу
        build_hls_for_field_sync(
            video_obj._meta.label,
            video_obj.pk,
            'video'
        )

        # Проверяем что все функции были вызваны
        mock_pull.assert_called_once()
        mock_transcode.assert_called_once()
        mock_save_tree.assert_called_once()

        # Проверяем что поле обновилось
        video_obj.refresh_from_db()
        self.assertIsNotNone(video_obj.hls_playlist)

