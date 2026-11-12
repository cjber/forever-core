# Third-party inputs

ForeverCore ships no embedded library and copies no other addon's code. What it reads from another addon in game is
listed here, with the build-only sources, then the players who helped. The addon itself is GPL-3.0-or-later
([LICENSE](LICENSE)).

## Read in game, never bundled

| Input | Used for | Licence |
|---|---|---|
| Questie, if installed | The quest list the shared tracker column steps beside | QuestieDB carries no licence; nothing is copied |
| EQ Objective Tracker, if installed | Its quest list and layout API, which the shared column also steps beside | Read only through its public API and frames; nothing is copied |

## Build and test only

| Input | Used for | Pin | Licence |
|---|---|---|---|
| [Blizzard UI source](https://github.com/Gethe/wow-ui-source) | The native objective-tracker integration spec | `REVISION` in `tools/fetch_tracker_ui.py` | Blizzard Entertainment's; fetched, never committed |
| [Ketho's WoW API annotations](https://github.com/Ketho/vscode-wow-api) | lua-language-server types in `tools/typecheck.sh` | `revision` in `tools/typecheck.sh` | MIT |
| [FrameXML annotations](https://github.com/NumyAddon/FramexmlAnnotations) | FrameXML types, the Ketho checkout's `Annotations/FrameXML` submodule | The gitlink in that Ketho revision | MIT |
| [wago.tools](https://wago.tools) | The listfile and backdrop art facts behind `tools/legacy_chrome.txt` | `BUILD` in `tools/gen_legacy_chrome.py` | Blizzard Entertainment's game data |

CI tools (StyLua, ruff, luacheck, lua-language-server, actionlint, zizmor, gitleaks, the BigWigs packager) are pinned in
`.github/workflows/`, `.github/actions/lua-toolchain/` and `tools/typecheck.sh`; they check the addon and are never part
of it.

## Players

One row per shipped contribution: a player with five shipped items has five rows with the same `Who`, in table order.

| Who | What | Notes |
|---|---|---|
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

## Inspired by

| Who | What | Notes |
|---|---|---|
| The game's own objective tracker | The column's left edge, width and header spacing | Blizzard's UI; nothing copied |
| [Questie](https://github.com/Questie/Questie) | Keeping the shared column clear of a quest list drawn in its place | Read in game; no code copied |
| [EQ Objective Tracker](https://www.curseforge.com/wow/addons/eq-objective-tracker) | The same for its own quest list and layout API | Read in game; no code copied |
