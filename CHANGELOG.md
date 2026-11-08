# Changelog

## [Unreleased]

- **The leaderboards and quest log side tabs are real buttons.** They were frames carrying the side-tab template's mouse scripts, and with the gamepad interface on the client's navigation reads the mouse scripts of any focused frame that is not a button, inside its own protected call. The tabs are Buttons now, as the client builds its own side tabs, so that scan never reads a script a Forever addon created. `LEADERBOARDS_VERSION` is 3. (#253, cjber/skillup-forever#398)
- **The release gate reads the in-game selftest.** `tools/forever_errors.py` now reads the `!!DevSmoke` dev addon's `/forever selftest` runs from its SavedVariables, so a surface that failed to open or close counts as a live entry under `--since` like any journal or BugGrabber error. The publish skill gains the smoke step: link the build, `/reload`, `/forever selftest`, `/reload`, then the gate. (#207)
- **The simulator boots what an exercise reaches.** `forever_sim` now loads the client's alert frames at startup, so an addon that anchors to `AlertFrame` loads. A panel shown in combat gets the client's own refusal: `DisplayInterfaceActionBlockedMessage` prints "Interface action failed because of an AddOn" once, with no Lua error. `Enum.GameRule` carries the rules the Blizzard UI reads, so the world map opens at its own strata. A frame script now runs with its setter's taint only until it returns, as it does when the client calls it, so a secure caller after the script is no longer blamed on the addon that set it. (#203)
- **One shared step exercises an addon under the real Blizzard UI.** `forever_sim` adds `sim:exercise()`: it logs in, runs every slash command the addon registered (twice, so a toggle opens and closes), opens, zooms, pans and closes the world map, repeats that in combat, then `/reload`s into a fresh client with the saved variables and runs them again, failing on an error either client caused. `sim:slash`, `sim:slashCommands` and `sim:reload` are the steps it uses. An addon adopts it with a one-line `tests/sim/exercise_scenario.lua`, and ForeverCore exercises itself. (#203)

- **A new tracker setting no longer fails every consumer's typecheck.** The tracker contract's LuaLS classes (`ForeverTrackerSettings`, `ForeverTrackerHostAPI`, the lock, order and namespace fields) now live in `types/ForeverTracker.lua`, vendored with `UI/TrackerHost.lua` to the four tracker consumers, so each one stops keeping a hand copy that a sync could leave behind. `tools/sync_consumers.py` copies a `types/` file without waiting for a TOC line. (#247)

- **Field Guide and Commissions get the error journal.** The vendoring map sends `Core/SafeCall.lua`, `Core/Log.lua`, `UI/Report.lua` and their specs to all seven addons, so the drift checks cover Field Guide's and Commissions' copies once they adopt them (cjber/field-guide-forever#214, cjber/commissions-forever#103).

- **A bench script times 1,000 addon messages and 1,000 tooltip lookups through the leaderboards.** Speedpatrol runs it.

## [0.5.0] - 2026-11-08

- **Closing the world map no longer blocks the controller's interact action.** `UI/MapCanvas.lua` heard the map close through an `OnHide` script on its host frame, which runs inside `UIParentPanelManager`'s hide before the gamepad binding stack is cleared, so the addon's taint blocked `SetPreferredGamepadInteractTarget`. It now listens to the panel manager's `HideUIPanel` and `ForcePanelHide` callbacks, the same two the gamepad's own manager uses. (cjber/adventure-guide-forever#493)
- **A quest log tab's panel hears when the player can see it, without a frame script.** A panel under the world map must not set or hook `OnShow` or `OnHide`: the script runs inside the map's close path, before the gamepad binding stack is cleared, and addon taint there blocks the controller's interact action (cjber/shortest-path-forever#158). `Register` now takes an optional `shown(visible)`, called once per change: the selected tab is visible while the world map and its quest log side panel are both shown, followed through the panel manager's `ShowUIPanel`, `HideUIPanel` and `ForcePanelHide` callbacks and a secure post-hook on `WorldMapFrame:SetQuestLogPanelShown`, so collapsing the side panel or maximizing the map counts too. (#220)
- **The CurseForge watch lists every thread still waiting on the owner.** `docs/handoff/cfwatch.py --unanswered` now groups each reply into its thread at any depth and lists a thread when its latest post is not the owner's, printing the whole thread. Before, an owner reply to a reporter's own follow-up still left the thread listed, and a reporter's follow-up after the owner's answer never showed. (#240)
- **The shared tracker can wear a background.** An optional dark backdrop, drawn with the game's own tooltip background art and tinted like the tooltip, sits behind the whole Forever column so sections stay readable over bright terrain. Every section's right-click menu offers it under "Tracker background" at off, 25%, 50%, 75% or 100%, so no addon has to add a settings row; the choice lives in the tracker settings the host already saves, and it only recolours a texture, so it works in combat. Thanks to Darkwavez76 and Naburiel for asking. (#241, cjber/adventure-guide-forever#203)
- **A sync PR no longer carries a shared module before its addon can load it.** `tools/sync_consumers.py` now copies a new runtime module into a consumer only once that consumer's own TOC already loads it or the tool wires it itself (as it does `Core/Log.lua`), and copies a shared test only once the modules it names are loaded too; until then it skips them and says so, so a sync PR carrying the rest of the shared files passes that addon's checks. Files an addon already carries keep syncing. (#237)
- **The leaderboards window and `/forever debug` reach players whichever addon loads first.** Every installed Forever addon ships the same `UI/Leaderboards.lua`, but the first copy to load owned the window and `/forever`, so a change stayed invisible unless that copy happened to be new. `LEADERBOARDS_VERSION` is now 2, so a v2 copy takes over a v1 copy's window and `/forever` and `/flb` handlers, keeps every board registered before the takeover and uses the one tooltip hook, which makes `/forever debug` reach the shared log. A new core check pins each shared file whose version gates takeover to its version and exact bytes, so a change without a raised version fails CI. (#235)
- **Errors outside a protected call reach the report with BugGrabber installed.** BugGrabber v12 replaces `seterrorhandler` with a no-op and announces each grabbed error on the client's `EventRegistry`, so the shared error capture now subscribes there and resolves the object with `BugGrabber:GetErrorByID`; previously it waited for a `CallbackHandler` API that BugGrabber does not have. (#232)
- **Mock backpacks show their items.** `tools/wowmock/wowmock.py` drew the empty-slot atlas as a 64-unit overlay over every backpack slot, so item icons, quality borders and counts were hidden. An empty slot's art now fills the 37-unit icon texture, as `SetItemButtonTexture(nil)` does in `ContainerFrameItemButtonMixin`, and a filled slot draws only its item. (#211)
- **The CurseForge watch keeps its place and sees Field Guide.** `docs/handoff/cfwatch.py` stores its seen IDs under `${XDG_STATE_HOME:-~/.local/state}/forever-core/cfwatch-seen.json` instead of inside a checkout, includes `field-guide-forever`, prints each comment's own ID, and adds `--unanswered` to list top-level comments with no `cjber` reply by matching replies to their parentId. (#230)
- **The simulator records each error once.** `forever_sim`'s default error handler recorded an error a second time, under the addon's name, when an addon's handler saved it and passed the error on, as the shared error capture and BugGrabber do. It now records only errors that reach it first, and the settings pages' `GetModifiedClick` and `GetBinding` calls have stubs. (#225)
- **A bug report can now say what led to the error.** `Core/Log.lua` adds `ns.Log(level, topic, message, ...)`: a 200-line ring per addon kept in its saved variables, so a `/reload` keeps earlier sessions. `info`, `warn` and `error` are always kept; `debug` only while `/forever debug` is on for the character, and a dropped debug line skips all formatting. `/forever debug pin` keeps it on across sessions, `/forever debug off` turns it off and unpins, and `/forever debug show` opens the report window with every attached addon's latest lines under its name, selected for copying. The state is shared by every loaded Forever addon and the report's copy adds the newest lines that fit after the error journal, so the lines closest to the error survive a long journal. Nothing is written to chat. Consumers attach it with `ns.AttachLog(store)`. (#206)
- **Forever addons share one quest log side tab.** `UI/QuestLogTabs.lua` gives an addon panel its tab beside the world map's quest log: registering a key, the panel and an order creates the tab, selecting it shows that panel in place of the quest log's own pages, and the Quests tab puts them back exactly as the client left them. Tabs stack by order, not by load order, and the module never writes `displayMode`, resizes the map or touches a panel's children, so a panel's scroll position survives every switch. (#220)
- **Error journals can be filed without reading BugSack by hand.** `tools/forever_errors.py` reads every Forever addon's journal, BugGrabber's errors and `Logs/taint.log`, groups them by repository and signature, and prints a table or JSON (`--json`). A group last seen before its addon's installed TOC is marked stale: it is hidden, does not fail the gate and is not filed unless `--include-stale` asks for it. `--file` opens one issue per signature labelled `error-report` and only comments again when the count rose; `--dry-run` shows what it would do. `--since` and `--addon` turn it into the release gate. (#205)
- **Errors now survive a reload.** The shared error capture chains the game's error handler, so unwrapped errors from the addon's folder, blocked and forbidden actions and Lua warnings are recorded without hiding anything from BugSack or the default error frame. Once a consumer passes its saved table to `ns.AttachErrorJournal`, the journal keeps up to 50 signatures with their counts, first and last seen times, versions, build, locale and other loaded addons, and the report window lists earlier sessions under their own heading. (#204)

## [0.4.29] - 2026-11-07

- **A locked tracker grip draws no long sentence.** While Lock is on the grip stays blank until the pointer is over it, and the locked sentence lives only in the tooltip, so a column placed at a screen edge no longer has text running off screen or over the UI below. Unlocked behaviour is unchanged. Thanks to MrFIXlT. (#193)

## [0.4.28] - 2026-11-07
- **Peer stats read a player's name through the secret guard.** The shared PeerStats vendored into every addon called `UnitName` without the `Readable` guard in `UnitDisplayName`, so the consumer addons' secret lint failed. The read now goes through `Readable`, and the guard is declared above its first use.

## [0.4.27] - 2026-11-07
- **Peer stats share only their metrics.** `Instance:Shared()` returned the saved display name beside the metric tables, so an addon looping over a peer row hit a string. It returns the metrics alone again; board rows still draw the full name. (#186)

## [0.4.26] - 2026-11-07
- **Leaderboards show full names.** Rows and tooltips now draw a player's first name and surname with the space the client's own name formatting uses, taken from the sender and saved beside the compacted identity key so no saved data moves. A row saved before this change splits at its single inner capital; the next message from that player replaces it. (cjber/forever-core#179)
- **Banned art now fails a mock at render time.** `wowmock.Ui.texture` and `Ui.atlas` check every path, atlas name and resolved FileDataID against the shared blacklist and raise `BannedAsset` naming the art and why, so a render from a scratch script or an f-string-built name fails the same way the repo gate does. The blanket `interface/minimap/` exemption is gone: map content stays exempt, the three LibDBIcon minimap-button pieces stay allowlisted by name, and the 2004 tracking icons under `interface/minimap/tracking/` fail and point at the atlas of the same name (`Repair`, `Banker`, `Innkeeper`, and the rest). The empty equipment-slot art the client returns from `C_PaperDollInfo.GetInventorySlotInfo` is exempt, as the game's own character pane draws it. (cjber/forever-core#182)

## [0.4.25] - 2026-11-07
- **The Forever Leaderboards window opens.** `/flb` and `/forever` raised a Lua error on first open because the list's rows had no height; the rows now have a fixed height. (#174)

## [0.4.24] - 2026-11-07
- **Every Forever addon shares one Forever Leaderboards window.** `/forever` or `/flb` opens the overall standing and each installed addon's board, with a weekly or all-time scope, medal places, class-coloured names, the player's own highlighted row and a sharing switch. Each addon registers a small board callback, so one shared file serves them all. The unit tooltip gains the player's overall place and their per-addon places, or one line for someone who uses the addons without placing. Nothing goes to chat and nothing glows. Overall is cached per scope and rebuilt only when a board's revision, the registered board list or the current week moves, so a tooltip hover is one lookup.
- **Peer statistics can rank a week.** `Instance:WeekBoard` mirrors `Board` with each value measured from the first value heard since the weekly reset, taken from the client's reset countdown or a Tuesday 15:00 UTC fallback. The player's own baseline is saved in the same layout, so old saved tables still load and gain baselines. `Instance:Revision()` rises whenever a stored row or the player's snapshot changes, and no addon messages are sent in combat; a queued change waits for combat to end.
- **Peer sharing is opt-out.** A missing saved setting now means on, and only an explicit off stays off, so every Forever addon appears on the boards and in tooltips without a first visit to its settings. The window's "Share my progress" checkbox and the settings pages still turn it off.

## [0.4.23] - 2026-11-06
- **Peer stats recognise a two-part player name.** The self check uses the same normalisation as an incoming sender, so a Forever name like Hel Io no longer stores the player's own broadcast as a peer and each board lists the player once.

## [0.4.22] - 2026-11-06
- **The family block points players to GitHub.** Every addon's README and store page now has an Issues link beside its store link, and a line under the table says bug reports, feature requests and pull requests are welcome on GitHub and that everyone whose report or idea ships is thanked by name in the addon's credits and changelog. Nothing changes in game.

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
