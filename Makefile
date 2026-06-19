test:
	rm -f output.txt
	uvx ruff format .
	uv run --with pytest-cov pytest -s --cov=src/
	uvx ty check
	uvx ruff check . --select ANN --unsafe-fixes --fix
	uvx mypy .
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

tdd:
	uv run --with pytest-watcher ptw .