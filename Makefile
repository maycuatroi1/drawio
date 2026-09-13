PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: help install virtualenv fmt lint test build docs
help:
	@echo "Targets: virtualenv install fmt lint test build docs"

virtualenv:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[test]'

install:
	$(PYTHON) -m pip install -e '.[test]'

fmt:
	$(PYTHON) -m ruff check --fix drawio tests examples setup.py
	$(PYTHON) -m ruff format drawio tests examples setup.py

lint:
	$(PYTHON) -m ruff check drawio tests examples setup.py
	$(PYTHON) -m ruff format --check drawio tests examples setup.py

test:
	$(PYTHON) -m pytest --cov=drawio --cov-report=term-missing

build:
	$(PYTHON) -m build

docs:
	$(PYTHON) -m mkdocs build --strict
