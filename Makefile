.PHONY: test quality format-check compile lint

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests

format-check:
	python scripts/check_format.py

compile:
	python -m compileall -q src tests

lint:
	@if command -v ruff >/dev/null 2>&1; then ruff check src tests scripts; else echo "ruff not installed; skipping lint"; fi

quality: format-check compile lint test
