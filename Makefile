sync-py:
	rsync -av \
	--delete --exclude="*.pyc" --progress \
	src/modules/adsb-pi-setup/filesystem/root/usr/local/share/adsb-pi-setup/ \
	root@adsb-feeder.local:/usr/local/share/adsb-pi-setup/
	ssh adsb-feeder.local "sudo systemctl restart adsb-setup"
