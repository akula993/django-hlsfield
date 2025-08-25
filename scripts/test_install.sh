#!/bin/bash
# Тестирование установки пакета из разных источников

set -e

echo "🧪 Тестирование установки django-hlsfield"
echo "========================================"

# Создаем временную директорию
TEST_DIR=$(mktemp -d)
echo "📁 Тестовая директория: $TEST_DIR"

cd "$TEST_DIR"

# Функция для тестирования установки
test_installation() {
    local install_command="$1"
    local test_name="$2"

    echo ""
    echo "🧪 Тест: $test_name"
    echo "Команда: $install_command"
    echo "----------------------------------------"

    # Создаем виртуальное окружение
    python -m venv test_env
    source test_env/bin/activate

    # Устанавливаем пакет
    pip install --upgrade pip
    eval "$install_command"

    # Тестируем импорт
    python -c "
import hlsfield
print(f'✅ Импорт успешен. Версия: {hlsfield.__version__}')

# Тестируем основные классы
from hlsfield import VideoField, HLSVideoField, DASHVideoField, AdaptiveVideoField
print('✅ Все поля импортированы успешно')

# Тестируем настройки
from hlsfield import defaults
print('✅ Настройки загружены')

# Проверяем наличие шаблонов
import hlsfield
import os
templates_dir = os.path.join(os.path.dirname(hlsfield.__file__), 'templates')
if os.path.exists(templates_dir):
    print('✅ Шаблоны найдены')
else:
    print('❌ Шаблоны не найдены')
"

    # Деактивируем окружение
    deactivate
    rm -rf test_env

    echo "✅ Тест '$test_name' прошел успешно!"
}

# Тестируем разные способы установки
test_installation "pip install django-hlsfield" "PyPI Production"

# Если есть тестовая версия
if pip search django-hlsfield --index https://test.pypi.org/simple/ &>/dev/null; then
    test_installation "pip install --index-url https://test.pypi.org/simple/ django-hlsfield" "Test PyPI"
fi

# Тестируем установку с дополнениями
test_installation "pip install 'django-hlsfield[celery]'" "С Celery"
test_installation "pip install 'django-hlsfield[s3]'" "С S3"
test_installation "pip install 'django-hlsfield[all]'" "Полная установка"

# Очищаем
cd /tmp
rm -rf "$TEST_DIR"

echo ""
echo "🎉 Все тесты установки прошли успешно!"
