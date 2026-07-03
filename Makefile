test:
	rm -f output.txt
	rm -f nes_test.log
	uvx ruff format .
	uvx ty check
	uvx ruff check . --select ANN --unsafe-fixes --fix
	uvx mypy .
	uv run --with pytest-cov pytest -s --cov=src/
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

nestest:
	uv run check_nes_test_log.py