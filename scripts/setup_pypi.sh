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
