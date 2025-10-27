HOST ?= adsb-feeder.local
SSH_CONTROL=/tmp/adsb-setup-ssh-control-${HOST}

export PATH := .venv/bin:$(PATH)

run-checks:
# run the Python linter checks locally
	@echo "Running Python linter checks..."
	@echo "=== Running flake8 ==="
	flake8 src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup --extend-ignore=E501,E203,E711,E721,F541 --show-source --statistics --count
	@echo "=== Running mypy ==="
	mypy src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup --config-file=pyproject.toml
	@echo "=== Running black ==="
	black --check --line-length 130 src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup
	@echo "=== Running ruff ==="
	ruff check src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup --config=pyproject.toml
	@echo "All linter checks completed successfully!"

create-venv:
# create virtual environment necessary to run linter checks
	python3 -m venv .venv
	pip3 install flask flake8 mypy black ruff requests types-requests shapely types-shapely


ssh-control:
# to avoid having to SSH every time,
# we make a SSH control port to use with rsync.
	ssh -M -S "${SSH_CONTROL}" -fnNT root@$(HOST)

sync-and-update-nocontainer:
# sync relevant files and update
	ssh -O check -S "${SSH_CONTROL}" root@$(HOST) || make ssh-control

	# sync over changes from local repo
	make sync-py-control

	# restart webinterface
	ssh -S "${SSH_CONTROL}" root@$(HOST) systemctl restart adsb-setup

	# restart the reovery service
	ssh -S "${SSH_CONTROL}" root@$(HOST) systemctl restart adsb-recovery

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

	# start webinterface back up
	ssh -S "${SSH_CONTROL}" root@$(HOST) systemctl restart adsb-setup

	# restart the reovery service
	ssh -S "${SSH_CONTROL}" root@$(HOST) systemctl restart adsb-recovery

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

run-loop:
# python3 app.py in a loop
	while true; do \
		python3 app.py; \
		sleep 1; \
	done
