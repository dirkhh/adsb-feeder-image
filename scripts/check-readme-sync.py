#!/usr/bin/env python3
"""Check that every aggregator in data.py's netconfigs_list is mentioned in README.md.

data.py is parsed with ast (not imported), so no dependencies are needed.
An aggregator counts as mentioned if the README links to its website's domain.
"""
import ast
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA_PY = ROOT / "src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/utils/data.py"
README = ROOT / "README.md"


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return ".".join(host.split(".")[-2:])


def netconfigs(path: Path) -> list[tuple[str, str]]:
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "NetConfig":
            kw = {k.arg: k.value for k in node.keywords}
            if isinstance(kw.get("name"), ast.Constant) and isinstance(kw.get("website"), ast.Constant):
                found.append((kw["name"].value, kw["website"].value))
    return found


def main() -> int:
    configs = netconfigs(DATA_PY)
    if not configs:
        print(f"ERROR: no NetConfig entries found in {DATA_PY}")
        return 1
    readme = README.read_text().lower()
    missing = [(n, w) for n, w in configs if not domain(w) or domain(w) not in readme]
    for name, website in missing:
        print(f"MISSING in README.md: {name} ({website})")
    if missing:
        print(f"{len(missing)} aggregator(s) from data.py not mentioned in README.md")
        return 1
    print(f"OK: all {len(configs)} aggregators from data.py are mentioned in README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
