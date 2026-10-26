# WoW mock rendering library

`wowmock.py` is the shared offline renderer for WoW: Forever screenshot scenes. It fetches the pinned client's
BLP textures, atlas records, fonts and DB2 tables from wago.tools, caches them under
`~/.cache/wowmock/<build>/`, and provides the reusable widgets and compositing helpers used by addon scene
scripts. It does not know about any individual addon; scene data and addon-specific drawing belong in each
consumer repository.

The library is MIT licensed; see [LICENSE](LICENSE). The client art and data it fetches remain Blizzard's.
Pillow is the only Python dependency. The build number and asset lookup behavior are defined in
`wowmock.py`; do not duplicate its BLP decoding, atlas resolution, cache, or native UI widget logic in a
consumer.

## Use from an addon scene script

Set `FOREVER_CORE` to this repository checkout and import the library from its tools directory:

```python
import os
import sys
from pathlib import Path

core = Path(os.environ.get("FOREVER_CORE", "../forever-core"))
sys.path.insert(0, str(core / "tools" / "wowmock"))
import wowmock

ui = wowmock.Ui(scale=2)
```

Use `ui.atlas(...)` and `ui.texture(...)` for client art, `ui.font(...)` for the pinned client fonts, and the
shared widget/compositing helpers for native UI chrome. Keep the renderer path configurable so CI and local
checkouts can point at the same Core source. Do not add hand-drawn replacements for real client art.

Read [NOTES.md](NOTES.md) before changing asset lookup or a widget. It records client-specific behavior that
is easy to misrender, including atlas variants, BLP decoding and nine-slice margins.
