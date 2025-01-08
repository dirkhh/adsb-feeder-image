#!/usr/bin/env python3

import sys

if (len(sys.argv) - 1) % 2 != 0:
    print("ERROR: even number of search replace pairs required!")
    sys.exit(1)

pairs = int((len(sys.argv) - 1) / 2)
sr = []
for i in range(pairs):
    sr.append((sys.argv[2 * i + 1], sys.argv[2 * i + 2]))
    #print(f"{sr[-1][0]} {sr[-1][1]}")

for line in sys.stdin:
    for search, replace in sr:
        line = line.replace(search, replace)
    sys.stdout.write(line)

