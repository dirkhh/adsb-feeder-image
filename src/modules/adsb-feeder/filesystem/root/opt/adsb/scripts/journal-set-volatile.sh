systemctl stop systemd-journald
rm -rf /var/log/journal
sed -i -e 's/.*Storage=.*/Storage=volatile/' "/etc/systemd/journald.conf"
sed -i -e 's/.*RuntimeMaxUse=.*/RuntimeMaxUse=10M/' "/etc/systemd/journald.conf"
systemctl restart systemd-journald
