.PHONY: install test lint format check clean

# Install all dependencies
install:
pip install -r lambdas/shared/requirements.txt
pip install -r requirements-dev.txt

# Run all tests
test:
pytest tests/ -v --cov=lambdas --cov-report=term-missing

# Run only unit tests
test-unit:
pytest tests/unit/ -v

# Run tests with coverage report
test-cov:
pytest tests/ --cov=lambdas --cov-report=html
@echo "Coverage report: htmlcov/index.html"

# Lint code
lint:
ruff check lambdas/ tests/
mypy lambdas/shared/

# Format code
format:
ruff format lambdas/ tests/
ruff check --fix lambdas/ tests/

# Check all (lint + test)
check: lint test

# Clean build artifacts
clean:
rm -rf .pytest_cache/
rm -rf htmlcov/
rm -rf .coverage
rm -rf .mypy_cache/
rm -rf .ruff_cache/
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
