#!/bin/bash
# scripts/publish.sh - Скрипт для публикации на PyPI

set -e  # Остановка при ошибке

echo "🎬 Django-HLSField PyPI Publisher"
echo "================================"

# Проверка что мы в правильной директории
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Ошибка: pyproject.toml не найден. Запустите из корневой директории проекта."
    exit 1
fi

# Проверка установленных зависимостей
echo "📦 Проверка зависимостей..."
python -m pip install --upgrade build twine

# Очистка предыдущих сборок
echo "🧹 Очистка старых сборок..."
rm -rf dist/
rm -rf build/
rm -rf *.egg-info/

# Проверка версии
echo "🏷️  Текущая версия:"
python -c "import sys; sys.path.append('src'); import hlsfield; print(f'v{hlsfield.__version__}')"

# Проверка что все файлы добавлены в git
if ! git diff --quiet; then
    echo "⚠️  Внимание: У вас есть несохраненные изменения."
    echo "Хотите продолжить? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Публикация отменена."
        exit 1
    fi
fi

# Запуск тестов
echo "🧪 Запуск тестов..."
if command -v pytest &> /dev/null; then
    python -m pytest tests/ -v
    if [ $? -ne 0 ]; then
        echo "❌ Тесты не прошли. Публикация отменена."
        exit 1
    fi
else
    echo "⚠️  pytest не установлен, пропускаем тесты."
fi

# Проверка качества кода
echo "🔍 Проверка качества кода..."
if command -v black &> /dev/null; then
    echo "  Проверка black..."
    black --check src/
fi

if command -v isort &> /dev/null; then
    echo "  Проверка isort..."
    isort --check-only src/
fi

if command -v flake8 &> /dev/null; then
    echo "  Проверка flake8..."
    flake8 src/
fi

# Сборка пакета
echo "🏗️  Сборка пакета..."
python -m build

# Проверка сборки
echo "🔍 Проверка сборки..."
python -m twine check dist/*

# Показать что будет загружено
echo "📋 Файлы для загрузки:"
ls -la dist/

# Подтверждение публикации
echo ""
echo "🚀 Готовы к публикации на PyPI?"
echo "Файлы: $(ls dist/)"
echo ""
echo "Выберите действие:"
echo "1) Опубликовать на Test PyPI (рекомендуется для первой проверки)"
echo "2) Опубликовать на Production PyPI"
echo "3) Отмена"
echo ""
read -p "Ваш выбор (1/2/3): " choice

case $choice in
    1)
        echo "📤 Публикация на Test PyPI..."
        python -m twine upload --repository testpypi dist/*
        echo ""
        echo "✅ Пакет опубликован на Test PyPI!"
        echo "🔗 Проверьте: https://test.pypi.org/project/django-hlsfield/"
        echo ""
        echo "Для тестирования установки:"
        echo "pip install --index-url https://test.pypi.org/simple/ django-hlsfield"
        ;;
    2)
        echo "📤 Публикация на Production PyPI..."
        python -m twine upload dist/*
        echo ""
        echo "🎉 Пакет успешно опубликован на PyPI!"
        echo "🔗 Доступен по адресу: https://pypi.org/project/django-hlsfield/"
        echo ""
        echo "Теперь пользователи могут установить его:"
        echo "pip install django-hlsfield"

        # Создаем git tag для релиза
        VERSION=$(python -c "import sys; sys.path.append('src'); import hlsfield; print(hlsfield.__version__)")
        echo ""
        echo "🏷️  Создание git тега для релиза..."
        git tag -a "v$VERSION" -m "Release version $VERSION"
        git push origin "v$VERSION"
        echo "✅ Тег v$VERSION создан и отправлен в репозиторий."
        ;;
    3)
        echo "❌ Публикация отменена."
        exit 0
        ;;
    *)
        echo "❌ Неверный выбор. Публикация отменена."
        exit 1
        ;;
esac

echo ""
echo "🎬 Публикация завершена!"

# scripts/setup_pypi.sh - Настройка окружения для PyPI
cat << 'EOF' > scripts/setup_pypi.sh
#!/bin/bash
# Настройка окружения для публикации на PyPI

echo "🔧 Настройка PyPI окружения..."

# Установка зависимостей для публикации
pip install --upgrade build twine

# Создание .pypirc файла для авторизации
if [ ! -f ~/.pypirc ]; then
    echo "📝 Создание ~/.pypirc файла..."
    cat << 'PYPIRC' > ~/.pypirc
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = your-pypi-token-here

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = your-testpypi-token-here
PYPIRC

    echo "✅ Файл ~/.pypirc создан."
    echo "⚠️  ВАЖНО: Замените 'your-pypi-token-here' и 'your-testpypi-token-here'"
    echo "   на ваши реальные токены от PyPI и Test PyPI."
    echo ""
    echo "🔗 Получить токены:"
    echo "   PyPI: https://pypi.org/manage/account/token/"
    echo "   Test PyPI: https://test.pypi.org/manage/account/token/"
else
    echo "✅ Файл ~/.pypirc уже существует."
fi

echo ""
echo "🎯 Следующие шаги:"
echo "1. Получите API токены на PyPI и Test PyPI"
echo "2. Обновите ~/.pypirc с вашими токенами"
echo "3. Запустите ./scripts/publish.sh для публикации"

EOF

# scripts/version_bump.sh - Утилита для обновления версии
cat << 'EOF' > scripts/version_bump.sh
#!/bin/bash
# Утилита для обновления версии пакета

set -e

if [ $# -eq 0 ]; then
    echo "Использование: $0 <новая_версия>"
    echo "Пример: $0 1.0.1"
    exit 1
fi

NEW_VERSION=$1

echo "🏷️  Обновление версии до $NEW_VERSION..."

# Обновляем версию в __init__.py
sed -i.bak "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" src/hlsfield/__init__.py

# Обновляем версию в pyproject.toml
sed -i.bak "s/version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Удаляем backup файлы
rm -f src/hlsfield/__init__.py.bak pyproject.toml.bak

echo "✅ Версия обновлена до $NEW_VERSION"

# Показываем изменения
echo ""
echo "📝 Измененные файлы:"
git diff --name-only

echo ""
echo "🎯 Следующие шаги:"
echo "1. Обновите CHANGELOG.md"
echo "2. Зафиксируйте изменения: git add . && git commit -m 'Bump version to $NEW_VERSION'"
echo "3. Запустите ./scripts/publish.sh"

EOF

# scripts/test_install.sh - Тестирование установки из разных источников
cat << 'EOF' > scripts/test_install.sh
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

EOF

# scripts/check_package.sh - Проверка готовности пакета к публикации
cat << 'EOF' > scripts/check_package.sh
#!/bin/bash
# Проверка готовности пакета к публикации

set -e

echo "🔍 Проверка готовности пакета к публикации"
echo "=========================================="

# Счетчик проблем
ISSUES=0

# Функция для логирования проблем
log_issue() {
    echo "❌ $1"
    ((ISSUES++))
}

log_ok() {
    echo "✅ $1"
}

# Проверка структуры проекта
echo ""
echo "📁 Проверка структуры проекта..."

if [ -f "pyproject.toml" ]; then
    log_ok "pyproject.toml найден"
else
    log_issue "pyproject.toml отсутствует"
fi

if [ -f "README.md" ]; then
    log_ok "README.md найден"
else
    log_issue "README.md отсутствует"
fi

if [ -f "LICENSE" ]; then
    log_ok "LICENSE найден"
else
    log_issue "LICENSE отсутствует"
fi

if [ -f "CHANGELOG.md" ]; then
    log_ok "CHANGELOG.md найден"
else
    log_issue "CHANGELOG.md отсутствует"
fi

if [ -d "src/hlsfield" ]; then
    log_ok "Исходный код найден"
else
    log_issue "Исходный код не найден в src/hlsfield"
fi

# Проверка версии
echo ""
echo "🏷️  Проверка версии..."
VERSION=$(python -c "import sys; sys.path.append('src'); import hlsfield; print(hlsfield.__version__)" 2>/dev/null)
if [ $? -eq 0 ]; then
    log_ok "Версия: $VERSION"
else
    log_issue "Не удается получить версию"
fi

# Проверка качества кода
echo ""
echo "📊 Проверка качества кода..."

if command -v black &> /dev/null; then
    if black --check src/ &>/dev/null; then
        log_ok "Black форматирование"
    else
        log_issue "Код не соответствует black стандартам"
    fi
else
    echo "⚠️  Black не установлен, пропускаем проверку форматирования"
fi

if command -v flake8 &> /dev/null; then
    if flake8 src/ &>/dev/null; then
        log_ok "Flake8 линтинг"
    else
        log_issue "Найдены проблемы в коде (flake8)"
    fi
else
    echo "⚠️  Flake8 не установлен, пропускаем линтинг"
fi

# Проверка зависимостей
echo ""
echo "📦 Проверка зависимостей..."

if python -c "import django" &>/dev/null; then
    log_ok "Django доступен"
else
    log_issue "Django не установлен"
fi

# Проверка сборки
echo ""
echo "🏗️  Тестовая сборка..."
rm -rf dist/ build/ *.egg-info/

if python -m build &>/dev/null; then
    log_ok "Пакет собирается без ошибок"

    # Проверка содержимого
    if python -m twine check dist/* &>/dev/null; then
        log_ok "Пакет проходит twine проверку"
    else
        log_issue "Пакет не прошел twine проверку"
    fi
else
    log_issue "Ошибки при сборке пакета"
fi

# Проверка README
echo ""
echo "📖 Проверка README..."
README_LENGTH=$(wc -c < README.md)
if [ "$README_LENGTH" -gt 1000 ]; then
    log_ok "README содержательный ($README_LENGTH символов)"
else
    log_issue "README слишком короткий ($README_LENGTH символов)"
fi

# Проверка git
echo ""
echo "🔄 Проверка Git..."
if git status &>/dev/null; then
    if [ -z "$(git status --porcelain)" ]; then
        log_ok "Все изменения зафиксированы в git"
    else
        log_issue "Есть незафиксированные изменения"
        echo "   Незафиксированные файлы:"
        git status --porcelain | head -5
    fi
else
    log_issue "Не git репозиторий или git недоступен"
fi

# Итоговый отчет
echo ""
echo "📋 Итоговый отчет"
echo "================"

if [ $ISSUES -eq 0 ]; then
    echo "🎉 Пакет готов к публикации!"
    echo ""
    echo "🚀 Следующие шаги:"
    echo "   1. ./scripts/publish.sh - для публикации"
    echo "   2. git tag v$VERSION - для создания тега релиза"
else
    echo "❌ Найдено проблем: $ISSUES"
    echo ""
    echo "🔧 Исправьте проблемы перед публикацией"
fi

exit $ISSUES

EOF

# Делаем скрипты исполняемыми
chmod +x scripts/publish.sh
chmod +x scripts/setup_pypi.sh
chmod +x scripts/version_bump.sh
chmod +x scripts/test_install.sh
chmod +x scripts/check_package.sh

echo ""
echo "📁 Созданы скрипты:"
echo "  scripts/publish.sh - Публикация на PyPI"
echo "  scripts/setup_pypi.sh - Настройка окружения"
echo "  scripts/version_bump.sh - Обновление версии"
echo "  scripts/test_install.sh - Тестирование установки"
echo "  scripts/check_package.sh - Проверка готовности к публикации"
