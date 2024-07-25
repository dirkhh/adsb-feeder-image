systemctl stop systemd-journald
rm -rf /var/log/journal
sed -i -e 's/.*Storage=.*/Storage=persistent/' "/etc/systemd/journald.conf"
systemctl restart systemd-journald
