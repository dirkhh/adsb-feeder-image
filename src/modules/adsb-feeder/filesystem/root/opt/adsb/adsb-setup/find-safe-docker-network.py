# call with cidr notation of the physical networks that the host is connected to
# e.g.: python3 find-safe-docker-network.py 192.168.2.178/24 10.84.2.18/16

import ipaddress
import sys

in_use = []
for arg in sys.argv[1:]:
    try:
        cidr = ipaddress.ip_network(arg, strict=False)
        in_use.append(cidr)
    except:
        print(f"skipping {cidr}")
        pass

# start with three of the usual suspects and then for good measure add a few more dozen in the 10.x.x.x range
cidr_choices = ["172.17.0.0/16", "172.18.0.0/16", "172.19.0.0/16"]
for b in range(172, 240):
    cidr_choices.append(f"10.{b}.0.0/16")
for block in cidr_choices:
    cidr = ipaddress.ip_network(block)
    useable = True
    for lcidr in in_use:
        if lcidr.overlaps(cidr):
            useable = False
            break

    if useable:
        print(block)
        exit(0)
exit(1)
