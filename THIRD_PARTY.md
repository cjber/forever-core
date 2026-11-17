# Third-party inputs

ForeverCore ships no embedded library, copies no other addon's code and reads no other addon in game. Its build-only
sources are listed here, then the players who helped. The addon itself is GPL-3.0-or-later ([LICENSE](LICENSE)).

## Made for these addons

| Input | Used for | Source | Licence |
|---|---|---|---|
| AI-assisted originals | The step markers in `media/Numbers/`: numbers 1 to 25, the empty `Ring.tga` and the pin's diamond on `Diamond.tga` | `tools/marker_source/` and `tools/export_markers.py` | This addon's own; no Blizzard art |

The marker art is original work made for these addons with AI assistance, as Adventure Guide Forever and Shortest
Path Forever describe the same numbered markers for their own use. None of it is Blizzard art. Only the exported
textures ship; `tools/marker_source/` holds the sources and `tools/export_markers.py` keys and exports them.

## Build and test only

| Input | Used for | Pin | Licence |
|---|---|---|---|
| [Blizzard UI source](https://github.com/Gethe/wow-ui-source) | The native objective-tracker integration spec | `REVISION` in `tools/fetch_tracker_ui.py` | Blizzard Entertainment's; fetched, never committed |
| [Ketho's WoW API annotations](https://github.com/Ketho/vscode-wow-api) | lua-language-server types in `tools/typecheck.sh` | `tools.annotations.commit` in `tools/toolchain.json` | MIT |
| [FrameXML annotations](https://github.com/NumyAddon/FramexmlAnnotations) | FrameXML types, the Ketho checkout's `Annotations/FrameXML` submodule | The gitlink in that Ketho revision | MIT |
| [wago.tools](https://wago.tools) | The listfile and backdrop art facts behind `tools/legacy_chrome.txt` | `BUILD` in `tools/gen_legacy_chrome.py` | Blizzard Entertainment's game data |
| [Blizzard client fonts and font definitions](https://wago.tools) | Offline Unicode glyph coverage and exact FontObject member mappings in `font_glyphs.json`; no font binaries ship or are committed | `FONT_BUILD`, `UI_REVISION` and `XML_FILES` in `tools/gen_font_glyphs.py`; generated JSON records each XML and TTF sha256 and download URL | Blizzard Entertainment's game data; build only |
| [websockets](https://github.com/python-websockets/websockets) | Local DevTools transport for the disposable manager lifecycle harness; never shipped | `tools/pyproject.toml` and `tools/uv.lock` | BSD-3-Clause |
| [fontTools](https://github.com/fonttools/fonttools) | Reads Unicode cmap tables when regenerating font coverage; not needed by the offline gate | Generator dependency in `tools/gen_font_glyphs.py`; generator environment must supply fontTools | MIT; build only |

CI tools (StyLua, ruff, luacheck, lua-language-server, actionlint, zizmor, gitleaks, the BigWigs packager) are pinned in
`tools/toolchain.json`, `tools/pyproject.toml` and `tools/uv.lock`, the `uses:` SHAs in `.github/workflows/`, and
`.github/actions/toolchain/`; they check the addon and are never part of it. Dependabot moves the `uses:` SHAs and the
`uv` group, the `bump-toolchain` workflow moves `tools/toolchain.json`, and a major version either one proposes waits
for review. The action reads the calling repository's `tools/toolchain.json`, so a SHA move and a manifest sync that
land in either order install the pins that checkout's own tools check for.

## Players

One row per shipped contribution: a player with five shipped items has five rows with the same `Who`, in table order.

| Who | What | Notes |
|---|---|---|
| [moshoutegong](https://github.com/moshoutegong) | Simplified Chinese translation | GitHub; cjber/adventure-guide-forever#801 |
| [moshoutegong](https://github.com/moshoutegong) | Traditional Chinese translation | GitHub; cjber/adventure-guide-forever#802 |
| TechnoHunter | Quest tracking stays safe when leveling | CurseForge; thread 8734322; #608 |
| user_efwsfml273dlvfm5 | Quest tracking stays safe when leveling | CurseForge; threads 8730123, 8716634, 8724252; #608 |
| serb1tar | Quest item icons and progress bars fit the quest list | CurseForge; #743 |
| tommyekholm | Quest item icons and progress bars fit the quest list | CurseForge; #743 |
| Crypa7 | Quest item icons and progress bars fit the quest list | CurseForge; #743 |
| [Shuro](https://github.com/Shuro) | Quest objective bars stay aligned inside the column | #735 |
| dokiz | Quest list steps aside for a UI suite's tracker | CurseForge; thread 8733295 under 8732171; #736 |
| user_vyffn82yvmu3bflh | Quest list steps aside for EllesmereUI | CurseForge; thread 8733334; #736 |
| user_8vheexbirr5v6h4a | Quest list switch in every section's Tracker menu | CurseForge; thread 8734900; cjber/shortest-path-forever#949 |
| Laddylucks | Minimap button under SexyMap's control | CurseForge; thread 8729503; #685 |
| thirex | Minimap button under SexyMap's control | CurseForge; thread 8729648; #685 |
| axejess | Minimap button under SexyMap's control | CurseForge; thread 8729935; #685 |
| p1tu | Minimap button under SexyMap's control | CurseForge; thread 8730902; #685 |
| Mirades96 | Minimap button under SexyMap's control | CurseForge; thread 8731392; #685 |
| silhouetteone | The game's tracker stays hidden in combat | CurseForge; thread 8731206; #686 |
| [kowakowa93](https://github.com/kowakowa93) | Forever sections follow Kaliel's Tracker | Contributor integration branch; #602 |
| xh43k | Reported clipped tracker rows and quest item art | CurseForge; thread 8715086; #603 |
| cotijelucie | Shared settings retained across embedded core copies | Reported uninstalling a bundled core on Discord; #448 |
| [iPulse](https://github.com/iPulse) | Forever sections under the objective tracker | Asked on CurseForge (#335) |
| _spada | Hide a tracker section from its menu | Asked on Discord (#292) |
| Darkwavez76 | A darker tracker background | Asked on CurseForge (#241) |
| Naburiel | A background option behind the tracker | Asked in cjber/adventure-guide-forever#203; #241 |
| MrFIXlT | Hide the locked tracker's hint until hovered | #193 |
| deathmvp1 | Tracker clear of Questie's quest list | CurseForge; cjber/shortest-path-forever#214 |
| berserkerlxl | Found the overlap with Questie's list | CurseForge; cjber/shortest-path-forever#214 |
| Alex21xx | Tracker lock | CurseForge; cjber/shortest-path-forever#238 |
| Torpdotorgx | Stopped the tracker erroring with another Forever addon loaded | CurseForge; cjber/shortest-path-forever#250 |
| dryzee | Fixed the tracker's nil-order crash | CurseForge; cjber/shortest-path-forever#253 |
| procque | Questie's quest tracker can be moved again | CurseForge |
| Fareed | Questie's quest tracker can be moved again | CurseForge |
| [ZiiMs](https://github.com/ZiiMs) | Tracker column follows EllesmereUI's custom quest tracker | cjber/shortest-path-forever#621; #332 |
| Bolton_wow | Map arrows open the destination map again | Asked on CurseForge (#486) |

## Inspired by

| Who | What | Notes |
|---|---|---|
| The game's own objective tracker | The column's left edge, width and header spacing | Blizzard's UI; nothing copied |
| [Questie](https://github.com/Questie/Questie) | Keeping the shared column clear of a quest list drawn in its place | Read in game; no code copied |
| [EQ Objective Tracker](https://www.curseforge.com/wow/addons/eq-objective-tracker) | The same for its own quest list and layout API | Read in game; no code copied |
