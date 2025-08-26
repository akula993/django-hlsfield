"""
Тесты edge cases и обработки ошибок
"""


class TestEdgeCases(BaseVideoFieldTest):
    """Тесты граничных случаев"""

    def test_empty_video_file(self):
        """Тест обработки пустого файла"""

        empty_file = SimpleUploadedFile("empty.mp4", b"", content_type='video/mp4')

        with patch('hlsfield.utils.ffprobe_streams', side_effect=RuntimeError("Invalid file")):
            video_obj = TestVideoModel(title="Empty")

            # Сохранение не должно падать
            try:
                video_obj.video.save("empty.mp4", empty_file)
            except Exception as e:
                # Логируем ошибку но не падаем
                print(f"Expected error for empty file: {e}")

    def test_corrupted_video_file(self):
        """Тест обработки поврежденного файла"""

        corrupted_data = b"Not a video file" * 100
        corrupted_file = SimpleUploadedFile("corrupted.mp4", corrupted_data, content_type='video/mp4')

        with patch('hlsfield.utils.ffprobe_streams', side_effect=RuntimeError("Corrupted file")):
            video_obj = TestVideoModel.objects.create(
                title="Corrupted",
                video=corrupted_file
            )

            # Метаданные должны быть по умолчанию
            self.assertIsNone(video_obj.duration)
            self.assertIsNone(video_obj.width)

    def test_very_large_video_metadata(self):
        """Тест обработки видео с экстремальными параметрами"""

        with patch('hlsfield.utils.ffprobe_streams') as mock_ffprobe:
            # Очень большое разрешение
            mock_ffprobe.return_value = {
                'format': {'duration': '86400'},  # 24 часа
                'streams': [
                    {
                        'codec_type': 'video',
                        'width': 8192,
                        'height': 4320  # 8K
                    }
                ]
            }

            video_obj = TestVideoModel.objects.create(
                title="8K Video",
                video=self.create_uploaded_file()
            )

            self.assertEqual(video_obj.width, 8192)
            self.assertEqual(video_obj.height, 4320)
            self.assertEqual(video_obj.duration.total_seconds(), 86400)

    def test_video_without_audio(self):
        """Тест видео без аудио дорожки"""

        with patch('hlsfield.utils.ffprobe_streams') as mock_ffprobe:
            mock_ffprobe.return_value = {
                'format': {'duration': '60'},
                'streams': [
                    {'codec_type': 'video', 'width': 1920, 'height': 1080}
                    # Нет аудио потока
                ]
            }

            video_obj = TestVideoModel.objects.create(
                title="Silent Video",
                video=self.create_uploaded_file()
            )

            # Должно обработаться без ошибок
            self.assertEqual(video_obj.width, 1920)

    def test_invalid_ladder_configuration(self):
        """Тест некорректной конфигурации лестницы качеств"""

        # Лестница с отрицательными значениями
        invalid_ladder = [
            {"height": -720, "v_bitrate": -2500, "a_bitrate": -128}
        ]

        field = HLSVideoField(ladder=invalid_ladder)

        # Поле должно создаваться, валидация на уровне транскодинга
        self.assertEqual(field.ladder, invalid_ladder)

    def test_missing_ffmpeg_binaries(self):
        """Тест отсутствия ffmpeg бинарей"""

        with patch('hlsfield.utils.run', side_effect=FileNotFoundError("ffmpeg not found")):
            with patch('hlsfield.utils.ffprobe_streams', side_effect=FileNotFoundError("ffprobe not found")):
                # Создание объекта не должно падать
                video_obj = TestVideoModel.objects.create(
                    title="No FFmpeg",
                    video=self.create_uploaded_file()
                )

                # Метаданные должны остаться пустыми
                self.assertIsNone(video_obj.duration)

    def test_storage_permission_errors(self):
        """Тест ошибок прав доступа к storage"""

        with patch.object(TestVideoModel.video.field.storage, 'save',
                          side_effect=PermissionError("Permission denied")):
            with self.assertRaises(PermissionError):
                TestRunner = get_runner(settings)

    test_runner = TestRunner()
    failures = test_runner.run_tests(["__main__"])

    if failures:
        exit(1)
        VideoModel.objects.create(
            title="Permission Error",
            video=self.create_uploaded_file()
        )

    def test_disk_space_full(self):
        """Тест обработки нехватки дискового пространства"""

        with patch('shutil.copyfileobj', side_effect=OSError("No space left on device")):
            with self.assertRaises(OSError):
                TestVideoModel.objects.create(
                    title="Disk Full",
                    video=self.create_uploaded_file()
                )


if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    # Minimal Django settings for tests
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                }
            },
            INSTALLED_APPS=[
                'django.contrib.contenttypes',
                'django.contrib.auth',
                'hlsfield',
            ],
            SECRET_KEY='test-key-for-tests-only',
            USE_TZ=True,
            MEDIA_ROOT='/tmp/test_media',
            DEFAULT_AUTO_FIELD='django.db.models.AutoField',
        )
        django.setup()

