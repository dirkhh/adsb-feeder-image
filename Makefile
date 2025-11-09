HOST ?= adsb-feeder.local
SSH_CONTROL=/tmp/adsb-setup-ssh-control-${HOST}
SET_VERBOSE=7

export PATH := .venv/bin:$(PATH)

run-checks:
# run the Python linter checks locally
	@echo "Running Python linter checks..."
	@if command -v uv >/dev/null 2>&1; then \
		echo "Using uv run"; \
		FLAKE8="uv run flake8"; MYPY="uv run mypy"; BLACK="uv run black"; RUFF="uv run ruff"; \
	elif [ -d .venv/bin ]; then \
		echo "Using .venv virtual environment"; \
		export PATH=.venv/bin:$$PATH; \
		FLAKE8=flake8; MYPY=mypy; BLACK=black; RUFF=ruff; \
	else \
		echo "ERROR: Neither 'uv' command nor .venv/bin found!"; \
		echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo "Or create venv: make create-venv"; \
		exit 1; \
	fi; \
	echo "=== Running flake8 ==="; \
	$$FLAKE8 src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup --extend-ignore=E501,E203,E711,E721,F541 --show-source --statistics --count || FAILURES="$$FAILURES flake8 in adsb-setup,"; \
	$$FLAKE8 src/tools --extend-ignore=E501,E203,E711,E721,F541 --show-source --statistics --count --exclude=venv,__pycache__,.git || FAILURES="$$FAILURES flake8 in tools,"; \
	echo "=== Running mypy ==="; \
	$$MYPY src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup --config-file=pyproject.toml || FAILURES="$$FAILURES mypy in adsb-setup,"; \
	$$MYPY src/tools --config-file=pyproject.toml --exclude venv --exclude __pycache__ || FAILURES="$$FAILURES mypy in tools,"; \
	echo "=== Running black ==="; \
	$$BLACK --diff --check --line-length 130 src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup || FAILURES="$$FAILURES black in adsb-setup,"; \
	$$BLACK --diff --check --line-length 130 src/tools --exclude venv --exclude __pycache__ || FAILURES="$$FAILURES black in tools,"; \
	echo "=== Running ruff ==="; \
	$$RUFF check src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup --config=pyproject.toml || FAILURES="$$FAILURES ruff in adsb-setup,"; \
	$$RUFF check src/tools --config=pyproject.toml --exclude venv --exclude __pycache__ || FAILURES="$$FAILURES ruff in tools,"; \
	echo "=========================================="; \
	if [ -z "$$FAILURES" ]; then \
		echo "All tests passed"; \
	else \
		SUMMARY=$${FAILURES%,}; \
		echo "Errors found with: $$SUMMARY"; \
		exit 1; \
	fi

run-tests:
# run the Python unit tests locally
	@echo "Running Python tests..."
	@if command -v uv >/dev/null 2>&1; then \
		echo "Using uv run"; \
		PYTEST="uv run pytest"; \
	elif [ -d .venv/bin ]; then \
		echo "Using .venv virtual environment"; \
		export PATH=.venv/bin:$$PATH; \
		PYTEST=pytest; \
	else \
		echo "ERROR: Neither 'uv' command nor .venv/bin found!"; \
		echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo "Or create venv: make create-venv"; \
		exit 1; \
	fi; \
	echo "=== Running pytest on tests/unit/ ==="; \
	$$PYTEST tests/unit/ -v || FAILURES="$$FAILURES pytest,"; \
	echo "=== Running selenium framework tests ==="; \
	$$PYTEST src/tools/automated-boot-testing/tests/ -v || FAILURES="$$FAILURES selenium-tests,"; \
	echo "=== Running automated-boot-testing tests ==="; \
	(cd src/tools/automated-boot-testing && $$PYTEST test_serial_console_reader.py test_metrics.py -v) || FAILURES="$$FAILURES automated-boot-testing,"; \
	echo "=========================================="; \
	if [ -z "$$FAILURES" ]; then \
		echo "All tests passed"; \
	else \
		SUMMARY=$${FAILURES%,}; \
		echo "Tests failed: $$SUMMARY"; \
		exit 1; \
	fi

run-lab-tests:
	python3 src/tools/automated-boot-testing/run_tests_with_artifacts.py

create-venv:
# create virtual environment necessary to run linter checks
	python3 -m venv .venv
	pip3 install flask flake8 mypy black ruff requests types-requests shapely types-shapely types-pyserial selenium humanize fastapi slowapi uvicorn kasa pytest


ssh-control:
# to avoid having to SSH every time,
# we make a SSH control port to use with rsync.
	ssh -M -S "${SSH_CONTROL}" -fnNT root@$(HOST)

sync-and-update-nocontainer:
# sync relevant files and update
	ssh -O check -S "${SSH_CONTROL}" root@$(HOST) || make ssh-control

	# sync over changes from local repo
	make sync-py-control

	# restart webinterface and recovery service
	ssh -S "${SSH_CONTROL}" root@$(HOST) systemctl restart adsb-setup adsb-recovery

sync-and-update:
# sync relevant files and update
	ssh -O check -S "${SSH_CONTROL}" root@$(HOST) || make ssh-control

	# stop webinterface
	ssh -S "${SSH_CONTROL}" root@$(HOST) systemctl stop adsb-setup
	# sync over changes from local repo
	make sync-py-control

	# update config
	ssh -S "${SSH_CONTROL}" root@$(HOST) python3 /opt/adsb/adsb-setup/app.py --update-config || true

	# docker pull / docker compose on the yml files
	ssh -S "${SSH_CONTROL}" root@$(HOST) /opt/adsb/docker-update-adsb-im

	# restart webinterface and recovery service
	ssh -S "${SSH_CONTROL}" root@$(HOST) systemctl restart adsb-setup adsb-recovery

sync-py-control:
# check if the SSH control port is open, if not, open it.
	ssh -O check -S "${SSH_CONTROL}" root@$(HOST) || make ssh-control

	rsync -av \
	--delete --exclude="*.pyc" --progress \
	-e "ssh -S ${SSH_CONTROL}" \
	src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/ \
	root@$(HOST):/opt/adsb/adsb-setup/

	rsync -av \
	--exclude="*.pyc" --progress \
	-e "ssh -S ${SSH_CONTROL}" \
	src/modules/adsb-feeder/filesystem/root/opt/adsb/ \
	root@$(HOST):/opt/adsb/

	mkdir -p src/modules/adsb-feeder/filesystem/root/usr/bin
	rsync -av \
	--exclude="*.pyc" --progress \
	-e "ssh -S ${SSH_CONTROL}" \
	src/modules/adsb-feeder/filesystem/root/usr/bin/ \
	root@$(HOST):/usr/bin/

	rsync -av \
	--exclude="*.pyc" --progress \
	-e "ssh -S ${SSH_CONTROL}" \
	src/modules/adsb-feeder/filesystem/root/etc/ \
	root@$(HOST):/etc/

# For good measure, copy this Makefile too
	rsync -av \
	-e "ssh -S ${SSH_CONTROL}" \
	Makefile \
	root@$(HOST):/opt/adsb/adsb-setup/Makefile

	ssh -S "${SSH_CONTROL}" root@$(HOST) '\
		rm -f /opt/adsb/.cachebust_done; \
		bash /opt/adsb/scripts/cachebust.sh Makefile;\
	'

	ssh -S "${SSH_CONTROL}" root@$(HOST) "echo ${SET_VERBOSE} > /opt/adsb/verbose"

run-loop:
# python3 app.py in a loop
	while true; do \
		python3 app.py; \
		sleep 1; \
	done
