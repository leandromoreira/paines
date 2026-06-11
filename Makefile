test:
	uv run --with pytest-cov pytest -s --cov=src/
	uvx ty check
enforce_hint:
	uvx ruff check . --select ANN --unsafe-fixes --fix
build:
	uv build
audit:
	uv audit