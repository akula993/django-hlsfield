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
