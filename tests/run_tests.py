#!/usr/bin/env python
"""
Скрипт для запуска тестов
"""
import os
import sys

# Добавляем путь к src в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')

    import django
    from django.conf import settings
    from django.test.utils import get_runner

    django.setup()

    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2)

    failures = test_runner.run_tests(['tests'])

    sys.exit(bool(failures))
