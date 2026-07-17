"""python3 -m spell_sync …"""

import sys

from spell_sync.cli import main

if __name__ == "__main__":
    # Normalize argv[0] so `-m spell_sync` matches the pip console script.
    raise SystemExit(main(["spell-sync", *sys.argv[1:]]))
