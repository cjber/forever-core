# Changelog

## [Unreleased]

## [0.4.21] - 2026-11-06
- **The minimap button stays in front of the Minimap.** It took the Minimap's own layer, so the Minimap's border could draw over it. It now sits on LibDBIcon's layer, pinned so it never falls behind.
- **For addon authors:** the asset registry names the owner's approved exceptions (the Islands compass as a standalone navigation icon only, Shortest Path's zeppelin icon, the `adventureguide-ring` route stop, Field Guide's `loottoast-sheen` and its recoloured target-frame rarity art), and WFA-27 now forbids any non-uniform resize outside the axis the client's own template stretches.
- **The shared micro-menu button is now a minimap button.** Field Guide's and Adventure Guide's buttons sit on the Minimap rim instead of widening the micro menu, which left the menu out of line with the XP bar. `Core/MinimapButton.lua` draws the addon's icon on the rim, drags around it with the angle saved in the addon's settings, and honours a hide flag. The vendored copies share one registry, so two addons' buttons land on different angles by default. No Blizzard frame is hooked or resized.
- **The shared minimap button now matches LibDBIcon.** It uses LibDBIcon's own 31-unit construction, the tracking-border overlay, background and cropped icon that Questie, RXP and AtlasLoot already show, so ours reads as one of theirs on the rim instead of a separate plate under a round mask.
- **Old loose UI chrome is refused by asset age, not by name.** The shared asset checker now resolves every `interface/` texture path in Lua, XML and screenshot renderers through the pinned 1.60.1.70124 listfile and rejects a FileDataID below 1,000,000, so 2004 through Mists chrome is caught even when no family list knew about it. Content icons, maps, portraits, cursors and fonts are exempt, atlases are untouched, and a path the pinned listfile cannot resolve fails as unverifiable. `tools/gen_legacy_chrome.py` regenerates the committed data in `forever_tools/`, which `sync.py` now vendors with the modules; the few old pieces with no modern replacement, such as the raid target markers, are allowlisted with a reason.

- **For addon authors:** the shared asset checker rejects the profession crafting progress bar atlases (`Profession-ProgressBar-BG` and `Profession-ProgressBar-frame`). Reused as a generic progress bar they read as the crafting cast bar, so use a plain `StatusBar` filled with `common-stat-bar-white` over `common-stat-bar-BG`, the art of the client's `ColoredProgressBarTemplate`.

## [0.4.20] - 2026-11-06
- **The tracker column steps aside for EQ Objective Tracker.** EQ Objective Tracker hides the game's quest tracker and draws its own list in that same slot, so its quests and the Forever sections drew over each other and neither could be read. `UI/TrackerEqot.lua` reads EQOT's list through its public API and re-places after each of its layout callbacks, and reads EQOT's own frame the same way when that API is not there; `UI/TrackerHost.lua` consults EQOT before Questie and generalises the beside-a-list layout. Never hooks or moves a protected frame, so the same placement runs in combat. Turn EQOT off and the column goes back where it was.

## [0.4.19] - 2026-11-05
- **The tracker header menu uses the addon's own menu where it has one.** Adventure Guide draws its own context menu, so its tracker right click no longer calls `MenuUtil.CreateContextMenu`, which can assert in Forever 70009; the other addons keep Blizzard's menu.

## [0.4.18] - 2026-11-05
- **Right-click any tracker section to attach or detach the column.** Each section's header now opens a small menu with **Attach to quest tracker** and **Lock the tracker**, so the column can be moved or locked without opening Settings. A switch made in combat waits for combat to end, and each section's left click keeps doing what it did.

## [0.4.17] - 2026-11-05
- **Tall tracker sections stay under your quests.** A section that fills the room left below the quest tracker, such as a long guide step, now shows what fits there instead of the whole column jumping beside the tracker. Each section is given the room the ones above it left, less the gap under it, so the column never runs past the bottom of the screen. The column only moves above or beside the tracker when no section fits below it at all.
- **Addon micro-menu buttons stay inside the micro menu.** Blizzard's buttons used to slide aside past the menu's own edge, so the row ran over the action bar beside it, or off the edge of the screen. The menu and its Edit Mode frame now grow by the addon buttons, so the action bar and bags beside them move aside, as they do for Blizzard's own buttons. In combat the row waits for combat to end.
- **Pressing an addon micro-menu button no longer errors.** Blizzard's pressed highlight read a texture name the button never had, so every press logged "attempt to concatenate field 'textureName'".

## [0.4.16] - 2026-11-05

- **The Forever addons settings page ends with a Ko-fi row.** Its Copy link button shows the Ko-fi address (`https://ko-fi.com/cjber`) in the same small window as the addons' store links, ready to copy. Nothing is locked behind it, and it shows only when the player opens the page. For addon authors: `ShowSupport` opens that window, and `VERSION` is 5.

## [0.4.15] - 2026-11-05

- **The release workflow's packager action moves forward.** Releases are built and uploaded by a newer version of the packager action, so nothing a player sees changes.

## [0.4.14] - 2026-11-05

- **For addon authors:** `tools/check_menu_scroll.py` refuses a menu built from a list that can outgrow the screen. Blizzard's Menu API never clamps a submenu, so a description that takes its entries in a loop needs `SetScrollMode`, a `UIDropDownMenu_AddButton` loop is refused outright, and a loop known to stay short says why on a `-- menu-scroll-ok:` line. The check is vendored into every Forever addon and runs first in the shared-file drift job, and `SettingsPage.AddDropdown` is gone because no addon called it and its old dropdown could not scroll.

## [0.4.13] - 2026-11-05

- **Every addon's micro-menu button gets its own place.** Buttons of different Forever addons in the same slot sat on the same spot, so only one showed, and each covered the Blizzard button beside Game Menu or Collections. They now line up in creation order, one slot each, and Blizzard's buttons move aside to make room, growing away from the screen edge the menu sits against. The vendored copies share one registry and hook each function and script once. The module hooks only scripts, an event and `UpdateMicroButtons`, and no longer runs the menu's Layout from addon code.
- **The micro-menu button hooks the game's update once.** It hooked `UpdateMicroButtons` again on every refresh, so each update ran one layer deeper until the game menu, the map and the micro buttons threw "C stack overflow" errors and the frame rate dropped.
- **The shared settings page titles itself in a font the client has.** It asked for `GameFontLarge`, which the Forever client does not define, so every addon's settings page raised "Couldn't find inherited node" on login. It now uses `GameFontHighlightHuge`, the font Blizzard's own settings pages use.
- **For addon authors:** `tools/check_client_load.py` now fails when Lua or XML inherits a font object neither the client nor the addon defines, and when a TOC lists `Bindings.xml`. It is vendored into every addon and runs in the required core-shared job.

## [0.4.12] - 2026-11-05

- **The tracker column stays still through combat, quests first.** The column no longer moves the game's quest tracker: the All Objectives header and the quests keep their slot, and the Forever sections read below them, in combat and out. Out of combat the sections used to sit above the quests and swap below them as a fight began, and a redraw in combat could drop the last section's last line.

## [0.4.11] - 2026-11-04

- **Simulator panels can close the bags.** The sim loads the client's bag frames (`ContainerFrame`), so `ShowUIPanel` and closing a panel reach the real `CloseAllBags`. A top-level XML frame takes its template's `parent` attribute, and `IsInventoryItemProfessionBag` exists. Opening and closing SettingsPanel raises no errors under the mouse or the gamepad.
- **Simulator loadstring chunks keep their instrumentation under setfenv.** An addon's runtime chunk binds the taint marker as a local, so a data parser that gives the chunk an empty environment gets its table back, and functions the chunk defines still report the addon.
- **Simulator SetToDefaults clears anchors.** A region released to the menu compositor's pool no longer keeps its old points, so reopening a stock dropdown with checkboxes cannot raise "Cannot anchor to a region dependent on it".
- **Simulator gamepad interface matches the client.** The watched binding stack is `GamepadSharedUtility.InputBindingManager`'s, `FocusEnter` and `FocusExit` run `OnEnter` and `OnLeave` in the caller's taint, `SpellCanTargetItem` and `SpellStopTargeting` exist, and the producer's `fetch.py` and `sync.py` are executable.
- **Simulator setGamepad runs the interface transition.** Switching fires `INPUT_DEVICE_INTERFACE_TRANSITION` (new style, old style), and the gamepad map CVars it reads have values, so a pooled menu's gamepad setup runs and its submenus open clean.

## [0.4.10] - 2026-11-04

- **The suite's documents no longer list Hoard Forever as a consumer.** The boundaries and consumer lists name only the addons that ship against this core, so a reader is not pointed at an addon that has been retired.

## [0.4.9] - 2026-11-04

- **The shared asset checker reads XML, not only Lua.** Backdrop file attributes, inline script handlers, multiline attributes and texture markup inside XML text now go through the same blacklist as Lua paths, so legacy chrome cannot slip back in through a template, and the shared family module carries a new version so an older installed copy cannot stay active.

## [0.4.8] - 2026-11-04

- **Generated-data checks keep scratch on the cache filesystem.** Independent regeneration uses ignored cache storage by default, honours explicit temporary-directory settings and explains cache-copy failures without starting a generator.
- **Simulator map visibility follows the client API.** Opening a map synchronously reports the requested area through WORLD_MAP_OPEN, and closing or reopening it dispatches visibility callbacks without quest-map refresh errors.
- **Map drawings share a canvas that leaves Blizzard's map tables untouched.** Adventure Guide and Legacy can draw, scale and interact with their own pins through the same helper, including each pin's right-click policy.
- **Simulator startup avoids recursive scroll callbacks.** Scroll offsets notify handlers only when their value changes, preventing Blizzard's map legend from overflowing the Lua stack and triggering native crashes in the pinned CI runtime.

## [0.4.7] - 2026-11-03

- **Legacy dialog chrome cannot bypass the asset check through native names.** The shared checker rejects templates and backdrop globals that select the old loose textures, including Lua identifiers and XML backdrop values.
- **Simulator helpers pass consumer multi-value lint.** Explicit single-value argument counts preserve vararg behaviour when the simulator is vendored into an addon.

- **Native panel composition has one lockup and one chrome owner.** The shared guidance now records
  native edge ownership for map and portrait frames, source-backed side rails and top/bottom tabs, clipped artwork
  and unframed versus beveled icons, so addon mockups do not approve impossible tab placement or
  nested borders.
- **Peer-statistic readers coexist with the source addon.** A read-only subscription observes validated reports without replacing another addon's sender or relaying its messages. Aggregate counts and encounter difficulties have explicit subject schemas.
- **Peer sharing tolerates inaccessible roster names.** The transport checks both name and realm before building a group signature.
- **Buttons use the Forever gold border.** Shared buttons and previews use the set-1 red-button atlas. The shared asset checker rejects legacy loose chrome and templates that select it, including references inside art helpers.
- **Linting works in cached checkouts.** The multi-value scanner applies directory exclusions inside its requested root, so a parent cache directory cannot hide every Lua file.
- **Combat transitions have regression coverage.** Specs check combat and lockdown during and after events, including player and other-unit loss-of-control data.
- **Multiline mock text follows client alignment.** Each line now aligns independently within centered and right-justified text boxes, including the widest-line constraint.
- **Reports deduplicate BugGrabber errors consistently.** Long caught errors no longer repeat in the BugGrabber section, and its heading is omitted when every entry is already listed.
- **Shared checks validate consumer identity and renderer coverage.** Worktree drift checks normalize GitHub remotes and reject unknown consumers, while asset checks include every active gallery renderer.

## 0.4.6 - 2026-11-03

- **Addons share one peer-statistics transport.** The shared module validates and bounds guild and group rows, ranks cumulative totals and observed first completions, and cancels sends and hides peers immediately when sharing is switched off.
- **Simulator loading respects excluded game types.** Startup bootstrap files, explicit addon loads and partial loads all honour the Forever client's addon restrictions.

## 0.4.5 - 2026-11-03

- **Profession scenarios complete their page transitions.** The test client loads startup bootstrap files and the casting bar, supplies the skipped action-bar and micro-menu calls, and keeps native constants readable during addon-triggered calls.
- **Core's dead-code check works in feature worktrees.** It identifies the shared-source repository by its TOC rather than its folder name.

## 0.4.4 - 2026-11-03

- **Mock menus keep their transparent corners.** The renderer no longer paints an opaque rectangle behind the rounded native menu artwork, so map previews have no dark square around the popup.

## 0.4.3 - 2026-11-03

- **The suite's tools ignore fixture TOCs that never ship.** TOC runtime discovery walked every `.toc` under
  a consumer, including the ones `tools/` and `tests/` keep for their own fixtures, so a vendored simulator
  could report a runtime file the packager never ships. Explicit tools and tests roots are now excluded while
  nested child-addon TOCs outside those roots are still found, with a regression covering the simulator's
  Auctionator stubs. Nothing changes in game.
- **Release help and changelog ordering work again.** `tools/changelog.py --help` answered with a traceback
  instead of usage, and version headings were compared as text, so 0.10.0 sorted below 0.9.0 when the tool
  checked which tags still need an entry. Both are fixed; entries are ordered numerically.

## 0.4.2 - 2026-11-03

- **Vendoring keeps the exec bit.** `forever_tools/sync.py update` and `forever_sim/sync.py update` copied with
  `shutil.copyfile`, which never carries the file mode, so a vendored script with a shebang landed as 100644 and
  ruff failed the consumer with EXE001. Both copy through a helper that carries the source mode across. Nothing
  changes in game.

## 0.4.1 - 2026-10-27

- **The suite's newest-build lookup now sees Forever's own product key.** wago.tools publishes Forever under
  `wowf` as well as the older `wow_classic_beta` list, and `forever_tools.latest_build` read only the latter, so
  the addons' daily data refresh kept reporting the previous build (1.60.1.70532) after 1.60.1.70630 shipped.
  It now reads both products and takes the highest 1.6x build. Nothing changes in game.

## 0.4.0 - 2026-10-26

- **Draw the mock context menu's backing surface opaque.** `common-dropdown-bg`'s atlas centre is translucent, so a
  menu composited straight over a scene let the list underneath show through its rows; the renderer now fills the
  panel behind the atlas art. `docs/handoff/mock-migration.md` records the migration state for the consumer addons.


- **Give offline UI mocks one shared renderer.** `tools/wowmock/` now owns the MIT-licensed BLP decoder, client
  asset cache, atlas and font lookup, native widget drawing, and frame compositing used by addon screenshots.
  Addons keep their own scenes and can import this library through `FOREVER_CORE`; Core's asset-sheet tool no longer
  reaches into Field Guide for the renderer.

## 0.3.0 - 2026-10-26

- **Put text matching and settings-page chrome in Forever Core, for the addons to vendor.** `Core/Text.lua` folds case
  and Latin accents (`ELEPHANT`, `Sao Tome`, `AEgir`, `Strasse`) and ranks a match as exact, prefix, word start or
  substring, replacing the four addons' own copies that disagreed; `UI/SettingsPage.lua` is the settings canvas every
  addon hand-built (`Register` plus `AddCheck`, `AddSlider`, `AddDropdown` and `AddButton`), drawing labels through the
  addon's own `ns.L`. Neither file holds an addon's options. The consumer registry lists both files, and their specs,
  before the copies land: nothing changes in game until the addons' own PRs adopt them.

## 0.2.1 - 2026-10-26

- **The consumer drift check no longer fails on a repo it cannot read.** Field Guide Forever is private, so
  unauthenticated raw reads of its copies returned 404 and the registry reported two files as drifted when they were
  byte-identical. It moves to a documented private-consumer list that is named in the success output, and Field Guide
  gates those same copies from its own repo. The boundaries doc records the split.
## 0.2.0 - 2026-10-25

- **Add shared micro-menu buttons** with Blizzard's native button template and placement refresh handling.
- **The consumer registry names Field Guide Forever's repo as it is now called.** `bestiary-forever` became
  `field-guide-forever` on 24 October, so the vendored micro button copies are read from the current name.

## 0.1.2 - 2026-10-24

- Move shared error capture into `Core/SafeCall.lua`, vendor it to all five consumers, and add scheduled core-authoritative drift checks.

## 0.1.1 - 2026-10-24

- **Unify report and link UI** in Forever Core, fix report text selection, and map vendored files to their consumers.

## 0.1.0

- **The shared tracker column becomes a repo of its own.** `UI/TrackerHost.lua`, `UI/TrackerLock.lua`,
  `UI/TrackerOrder.lua` and `UI/TrackerQuestie.lua` move here as the single source, with the specs that pin them
  (`tests/tracker_host_spec.lua` against Blizzard's own tracker source, and the lock, order and Questie specs). The
  four addons that draw sections vendor these files at the same paths, so nothing changes in game until an addon
  moves to a new core version.
- **ForeverCore is installable on its own.** `Core.lua` keeps the column's settings in `ForeverCoreDB`, `Expose.lua`
  publishes `ForeverCore` and `/fcore`, and the TOC lists the five Forever addons as `OptionalDeps` so an addon that
  already owns the column loads first and core adopts it rather than starting a second one.
- **Drift is a gate now.** `tools/check_consumers.py` fails when any consumer's copy differs from this repo, and
  `tools/sync_consumers.py` is the one command that moves a fix out to them.
