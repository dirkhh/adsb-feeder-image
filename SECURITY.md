# Security Policy

This is intentionally insecure software.

When run as an image, it provides remote root access to the host it is running
on by design. Do not make web access to this software available to untrusted
users. Do not run it exposed to the internet.

There are some attempts to allow the user to make the image slightly less
vulnerable, and with some effort the UI can be protected behind a login, but
that's outside of the scope that we expect most users to be comfortable with.

In general, please do not report security issues for the image (it is
fundamentally insecure and that can't be fixed without breaking the key use
case for it - making things easier for non-technical users). However,
functional bugs that allow an attacker to get access to a "secured" system and
especially that work in "app" mode can be reported to adsb@adsb.im.

Please don't allow AI agents to simply spray low quality "security reports" at
the maintainers of this software.
