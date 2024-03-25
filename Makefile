HOST=adsb-feeder.local

ssh-control:
# to avoid having to SSH every time,
# we make a SSH control port to use with rsync.
	ssh -M -S /tmp/adsb-setup-ssh-control -fnNT root@$(HOST)

sync-and-update-nocontainer:
# sync relevant files and update
	ssh -O check -S /tmp/adsb-setup-ssh-control root@$(HOST) || make ssh-control

	# sync over changes from local repo
	make sync-py-control

	# restart webinterface
	ssh -S /tmp/adsb-setup-ssh-control root@$(HOST) systemctl restart adsb-setup

sync-and-update:
# sync relevant files and update
	ssh -O check -S /tmp/adsb-setup-ssh-control root@$(HOST) || make ssh-control

	# stop webinterface
	ssh -S /tmp/adsb-setup-ssh-control root@$(HOST) systemctl stop adsb-setup
	# sync over changes from local repo
	make sync-py-control

	# update config
	ssh -S /tmp/adsb-setup-ssh-control root@$(HOST) python3 /opt/adsb/adsb-setup/app.py --update-config || true

	# docker pull / docker compose on the yml files
	ssh -S /tmp/adsb-setup-ssh-control root@$(HOST) /opt/adsb/docker-update-adsb-im -no-fetch

	# start webinterface back up
	ssh -S /tmp/adsb-setup-ssh-control root@$(HOST) systemctl restart adsb-setup

sync-py-control:
# check if the SSH control port is open, if not, open it.
	ssh -O check -S /tmp/adsb-setup-ssh-control root@$(HOST) || make ssh-control
	rsync -av \
	--delete --exclude="*.pyc" --progress \
	-e "ssh -S /tmp/adsb-setup-ssh-control" \
	src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/ \
	root@$(HOST):/opt/adsb/adsb-setup/

	rsync -av \
	--exclude="*.pyc" --progress \
	-e "ssh -S /tmp/adsb-setup-ssh-control" \
	src/modules/adsb-feeder/filesystem/root/opt/adsb/ \
	root@$(HOST):/opt/adsb/

	mkdir -p src/modules/adsb-feeder/filesystem/root/usr/bin
	rsync -av \
	--exclude="*.pyc" --progress \
	-e "ssh -S /tmp/adsb-setup-ssh-control" \
	src/modules/adsb-feeder/filesystem/root/usr/bin/ \
	root@$(HOST):/usr/bin/

	rsync -av \
	--exclude="*.pyc" --progress \
	-e "ssh -S /tmp/adsb-setup-ssh-control" \
	src/modules/adsb-feeder/filesystem/root/etc/ \
	root@$(HOST):/etc/

# For good measure, copy this Makefile too
	rsync -av \
	-e "ssh -S /tmp/adsb-setup-ssh-control" \
	Makefile \
	root@$(HOST):/opt/adsb/adsb-setup/Makefile

run-loop:
# python3 app.py in a loop
	while true; do \
		python3 app.py; \
		sleep 1; \
	done
