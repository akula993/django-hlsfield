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
