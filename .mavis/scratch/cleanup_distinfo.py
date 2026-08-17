"""Side-task: clean up stale dist-info directories that uv left behind.

The .broken suffix directories and the partial 2.2.6 dist-info confuse
importlib.metadata (transformers' version check fails on the None version).
"""

import shutil
from pathlib import Path

# Stale dist-info directories to remove (uv marked them broken or partial).
stale = [
    ".venv/Lib/site-packages/numpy-2.2.6.dist-info",
    ".venv/Lib/site-packages/numpy-2.2.6.dist-info.broken",
    ".venv/Lib/site-packages/numpy-2.4.6.dist-info.broken",
    ".venv/Lib/site-packages/websockets-13.1.dist-info",
]

for p in stale:
    path = Path(p)
    if path.is_dir():
        print(f"removing {path}")
        shutil.rmtree(path, ignore_errors=True)
    else:
        print(f"skipping (not present): {path}")

print("done")
