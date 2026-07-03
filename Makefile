.PHONY: install dev api ui test lint typecheck clean

install:
	python -m pip install -e ".[dev]"

dev:
	@echo "Run 'make api' and 'make ui' in two terminals."

api:
	python -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000

ui:
	python -m streamlit run app/ui/streamlit_app.py

test:
	python -m pytest -q

lint:
	python -m ruff check app tests
	python -m ruff format --check app tests

typecheck:
	python -m mypy app

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
