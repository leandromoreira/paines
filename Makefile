test:
	uvx ruff format .
	uv run --with pytest-cov pytest -s --cov=src/
	uvx ty check
	uvx ruff check .
	uvx mypy .
enforce_hint:
	uvx ruff check . --select ANN --unsafe-fixes --fix
build:
	uv build
audit:
	uv audit
cover_html:
	uv run --with pytest-cov pytest -s --cov=src/ --cov-report=html

complexity:
	uvx radon mi .

complexity_details:
	uvx radon cc . -a -s