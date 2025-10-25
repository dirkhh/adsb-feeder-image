run-checks:
# run the Python linter checks locally
	@echo "Running Python linter checks on src/tools..."
	@if [ -d ../../.venv/bin ]; then \
		echo "Using .venv virtual environment"; \
		export PATH=../../.venv/bin:$$PATH; \
		FLAKE8=flake8; MYPY=mypy; BLACK=black; RUFF=ruff; \
	else \
		echo "Using uv run"; \
		FLAKE8="uv run flake8"; MYPY="uv run mypy"; BLACK="uv run black"; RUFF="uv run ruff"; \
	fi; \
	echo "=== Running flake8 ==="; \
	$$FLAKE8 . --extend-ignore=E501,E203,E711,E721,F541 --show-source --statistics --count --exclude=venv,__pycache__,.git; \
	echo "=== Running mypy ==="; \
	$$MYPY . --config-file=../../pyproject.toml --exclude venv --exclude __pycache__; \
	echo "=== Running black ==="; \
	$$BLACK --check --line-length 130 . --exclude venv --exclude __pycache__; \
	echo "=== Running ruff ==="; \
	$$RUFF check . --config=../../pyproject.toml --exclude venv --exclude __pycache__; \
	echo "All linter checks completed successfully!"
