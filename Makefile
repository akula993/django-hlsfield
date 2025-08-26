.PHONY: help install test lint clean build publish

help:
	@echo "Available commands:"
	@echo "  install     Install package and dependencies"
	@echo "  test        Run tests"
	@echo "  lint        Run linting"
	@echo "  clean       Clean build artifacts"
	@echo "  build       Build package"
	@echo "  publish     Publish to PyPI"

install:
	pip install -e ".[dev]"
	pre-commit install

test:
	python -m pytest tests/ -v

test-integration:
	python -m pytest tests/ -m integration -v

lint:
	black --check src/ tests/
	isort --check-only src/ tests/
	flake8 src/ tests/
	mypy src/hlsfield/

format:
	black src/ tests/
	isort src/ tests/

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -delete

build: clean
	python -m build

publish-test: build
	python -m twine upload --repository testpypi dist/*

publish: build
	python -m twine upload dist/*

docker-build:
	docker build -f examples/docker/Dockerfile -t django-hlsfield .

docker-run:
	docker run -p 8000:8000 django-hlsfield
