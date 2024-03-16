HOST=adsb-feeder.local

ssh-control:
# to avoid having to SSH every time,
# we make a SSH control port to use with rsync.
	ssh -M -S /tmp/adsb-setup-ssh-control -fnNT root@$(HOST)

setup-sync:
# used for updating a running server - only update the setup app, don't delete things
	ssh -O check -S /tmp/adsb-setup-ssh-control root@$(HOST) || make ssh-control
	rsync -av \
	--exclude="*.pyc" --progress \
	-e "ssh -S /tmp/adsb-setup-ssh-control" \
	src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/ \
	root@$(HOST):/opt/adsb/adsb-setup/
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
