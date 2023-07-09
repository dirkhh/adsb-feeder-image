ssh-control:
# to avoid having to SSH every time,
# we make a SSH control port to use with rsync.
	ssh -M -S /tmp/adsb-pi-setup-ssh-control -fnNT root@adsb-feeder.local

sync-py-control:
# check if the SSH control port is open, if not, open it.
	ssh -O check -S /tmp/adsb-pi-setup-ssh-control root@adsb-feeder.local || make ssh-control
	rsync -av \
	--delete --exclude="*.pyc" --progress \
	-e "ssh -S /tmp/adsb-pi-setup-ssh-control" \
	src/modules/adsb-pi-setup/filesystem/root/usr/local/share/adsb-pi-setup/ \
	root@adsb-feeder.local:/usr/local/share/adsb-pi-setup/

# For good measure, copy this Makefile too
	rsync -av \
	-e "ssh -S /tmp/adsb-pi-setup-ssh-control" \
	Makefile \
	root@adsb-feeder.local:/usr/local/share/adsb-pi-setup/Makefile

run-loop:
# python3 app.py in a loop
	while true; do \
		python3 app.py; \
		sleep 1; \
	done
