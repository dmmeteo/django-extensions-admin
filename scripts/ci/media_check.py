"""Check docs/media against its manifest: hashes, file types, and the UI files it was captured from.

python3 scripts/ci/media_check.py <repository root>
"""

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads((root / "docs/media/manifest.json").read_text())
SIGNATURES = {".gif": (b"GIF87a", b"GIF89a"), ".png": (b"\x89PNG\r\n\x1a\n",)}
problems = []


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for asset in manifest["assets"]:
    path = root / asset["path"]
    if not path.is_file():
        problems.append(f"{asset['path']} is missing")
        continue
    if sha256(path) != asset["sha256"]:
        problems.append(f"{asset['path']} differs from the captured file")
    if not path.read_bytes().startswith(SIGNATURES[path.suffix]):
        problems.append(f"{asset['path']} is not a {path.suffix} file")
for source, digest in manifest["ui_sources"].items():
    path = root / source
    if not path.is_file() or sha256(path) != digest:
        problems.append(f"{source} changed after the media were captured")
if problems:
    print("\n".join(problems))
    raise SystemExit(1)
assets, sources = len(manifest["assets"]), len(manifest["ui_sources"])
print(f"OK: {assets} media files match the {sources} UI files they show")
