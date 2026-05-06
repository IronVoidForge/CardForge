.PHONY: test quality format-check compile

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

format-check:
	python scripts/check_format.py

compile:
	python -m compileall -q src tests

quality:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python scripts/quality_check.py
