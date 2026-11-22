# Changelog

## [1.17.0] - 2026-11-22

<!-- discord-image: docs/screenshots/tracker.png -->

### Added

- Turn on **Always stay under the quest tracker** in the Tracker position menu to keep the Forever column below your quests when space is short. Scroll the sections to see the rest.

### Fixed

- On a short screen or with an enlarged minimap, the attached Forever tracker column starts below the minimap and its zone name bar instead of drawing over them, and its sections fit the room left.
- Dragging the Forever tracker into combat now ends the move and saves its position before combat lockdown.
- `/fcore quests` now explains that ForeverCore has no quest list of its own and never hides or moves the game's or Questie's quest tracker, instead of printing a tracker diagnostic. `/fcore tracker` prints that diagnostic, and any other word prints the commands; thanks to Wavebreaker90 for the report.

### For addon authors

- Simulator exercises start with a secure execution context after a scenario calls addon code directly.
- Simulator scenarios can deliver Edit Mode layout updates and apply the tracker anchor from a layout.
- The simulator allows the game's Create button to craft after reading recipe data from an addon.
- Visual proof can verify addon builds that bundle ForeverCore, including the bundled files and the addon code the loader runs.
- The simulator identifies which addon file LuaJIT could not compile and stops loading that addon before related errors pile up.
- The consumer sync inserts missing bare TOC version steps before named BigWigs packager builds. The consumer check and sync both skip packager steps that reuse an existing ZIP with `-c -z`.
- **Release-prep pull requests check that the ForeverCore pin is current before tagging.** `forever_tools.core_pin --latest-if-release-prep --base <ref>` requires core's latest published release only when `CHANGELOG.md` adds a new version heading against the base branch, leaving normal pull requests unaffected. `tools/sync_consumers.py` and `tools/check_consumers.py` keep this step in every published consumer's CI workflow. (#858)
- A Forever addon loaded on demand after world entry now gets `PLAYER_ENTERING_WORLD` replayed with `false, false` (neither a login nor a reload) instead of nil arguments, so a saved debug capture resumes or stops correctly.
- **Manual releases refuse commits that already carry another tag.** The `Tag a manual release` workflow step now checks the target commit before creating a tag on GitHub and fails if another tag already points to it, so BigWigs packager cannot attach the validated ZIP to the wrong release. Consumers receive the guard through `tools/sync_consumers.py`. (#940)
- wowmock renders the client's own StaticPopup button: `UI-DialogBox-Button-Up`, `-Down`, `-Disabled` and `-Highlight` pass the asset gate instead of failing as pre-Legion loose chrome. `Blizzard_StaticPopup_Game/GameDialog.xml` still sets all four by file on `StaticPopupButtonTemplate` and the pinned build has no atlas for that art, so any mock of a StaticPopup, including the outdated-ForeverCore notice (#942), could not be rendered before this.

## [1.16.3] - 2026-11-21

### Fixed

- Moving Questie's tracker no longer leaves the Forever column on top of it or at the game tracker's old place: the column follows Questie's list to where you drop it, and gives way when a list is dropped onto a column that holds its place, locked or not; thanks to Zerkuleez for the report.

## [1.16.2] - 2026-11-21

### Fixed

- With no quest tracked, the Forever column stays in one place instead of moving when the hidden Objective Tracker's position shifts: it keeps the place the tracker had when it last showed.

## [1.16.1] - 2026-11-21

### Fixed

- Dragging the Objective Tracker in Edit Mode no longer throws a Lua error on every frame or makes the tracker disappear: the Forever column now places itself from the tracker's position instead of hanging off it, and follows when the drag ends; thanks to hknylmz and Flangemuffler for the reports.

## [1.16.0] - 2026-11-21

<!-- discord-image: docs/screenshots/tracker.png -->

### Added

- **Move the world map tabs.** Drag a Forever tab up or down to move the column out of the way of other addons. Right-click a Forever tab and choose Reset tab position to move it back. (cjber/shortest-path-forever#1056)

### Fixed

- **The tracker column no longer draws over your action bars.** It only ever clamped itself to the screen, so with a short screen and the quest tracker up it laid out down into the main bar, and with action bars down the right side it grew into them. It now reads the bars your own layout put on screen and stops above a bar under it, or left of one beside it, the same way it stops at the tracker's line; a hidden bar, or one parked where the column never reaches, takes no room. (#987, cjber/shortest-path-forever#1139)

### For addon authors

- **Packaging checks no longer fail under a stray `.git` folder.** A `.git` folder in a parent directory that git itself does not accept as a repository, such as an empty one in the temp directory, no longer makes the package file checks report that git cannot read the work tree. (#826)
- **One addon's sync error no longer stops the sync for the rest.** A consumer that cannot sync is reported against that addon only, and every other addon still gets its shared files. (#976)
- **A vendored core file no longer fails your typecheck.** When the sync copies `Core/ForeverRequire.lua` into an addon, it refreshes that file's pinned digest in `tools/font_bindings.json`, so a core change to a file the addon cannot review stops failing its font-binding check. (#998)

## [1.15.8] - 2026-11-20

### Fixed

- **Per-character settings save on Forever realms.** A Forever realm has no name, so a key built from the realm was empty or shared between characters with the same first name. `ForeverCore.CharacterKey()` gives every addon one key: `Name-Realm` on a named realm, as before, and the full name with the server number on a Forever realm. (#999)

### For addon authors

- **`ForeverCore.CharacterKey()` is the one per-character key (core minor 3).** Use it for every per-character saved table instead of a key built from `GetRealmName` or `UnitName`'s second return, which is the surname on Forever. It is `Name-NormalizedRealm` on a named realm, so existing saves keep matching, and `Name Surname-<server>` from `UnitGUID("player")` on a Forever realm. It is nil until the client knows the character, so ask again later; check `(ForeverCore.minor or 0) >= 3` first. (#999)
- **`forever_sim` and the fake client play on a Forever realm.** They answer no realm name, realm ID 0 and the surname as `UnitName`'s second value, as the live client does; a scenario sets `sim.world.player.realm` for a named realm. After syncing, a scenario that relied on a realm name fails until its addon uses `CharacterKey`. (#997)

## [1.15.7] - 2026-11-20

### Fixed

- **An addon that carries its own ForeverCore no longer loses what it does at login.** Since 1.15.6 such an addon's files run at login even with the separate ForeverCore installed, after the game's login event, and a file waiting for that event with `EventUtil.ContinueAfterAllEvents` was never called back: Adventure Guide Forever stayed on "Loading quest data..." with no route and did not pick up RestedXP guides. Files now wait with `ns.AfterEvents`, which waits only for the events still to come, and the package step refuses a file that waits the old way. (#980, cjber/adventure-guide-forever#892)
- **Tracker sections and the error grabber start when an addon's own ForeverCore runs after login.** A tracker section created after the world loaded, and the error grabber's login hook, no longer wait on loading events that already fired. (#984)

## [1.15.6] - 2026-11-20

### Fixed

- **Addon versions read without a leading v.** A packaged TOC now carries `## Version: 1.2.3` instead of the release tag `v1.2.3`, so every Forever addon's "updated to" line, report and saved version match the version they compare with. Release and CI builds write the version before packaging and fail a package whose version still starts with v. (#855)
- **An addon that carries its own ForeverCore finishes loading before its saved settings are applied.** With no separate ForeverCore installed the addon's files run at login, and a file waiting for its own addon to load was called back at once, before the files after it: Adventure Guide Forever 1.12.2 raised `Core.lua:1306: attempt to index field 'QuestieOptions'`. Files now wait with `ns.OnFilesLoaded`, which calls back after the last file, and the package step refuses a file that waits the old way. A package with a file the game did not load stops with its usual line instead of a Lua error. (cjber/adventure-guide-forever#886)
- **Clickable tracker lines work with the ForeverCore an addon carries.** `ForeverCore.TrackerLine.template` now names the clickable line template whichever ForeverCore runs, including an older separate ForeverCore install, and the embed step refuses an addon file that writes the template's name out instead of reading it there. SkillUp's trainer and vendor lines raised "Couldn't find inherited node" without a separate ForeverCore install. (#964)
- **An older separate ForeverCore no longer holds back newer addons.** The ForeverCore download now loads the same way as the copy each Forever addon carries, so when both are installed the newest one runs. Before, an installed ForeverCore always ran even when an addon carried a newer one, and that addon could raise a Lua error at login. (#946)
- **The outdated ForeverCore notice no longer blocks gamepad interactions.** The notice now closes with its OK button only, not with Escape or the gamepad confirm button. (#942)

### For addon authors

- **The API kit shares world map markers and two more not-ready reasons.** `APIKit.RegisterMapMarkers(addonName, read)` and `APIKit.MapMarkers(map, except?)` replace the `ForeverMapMarkers` global each addon copied. `NotReady` also takes `"combat"` and `"unreachable"`, and `docs/api-conventions.md` says to answer anything else with `"none"`. `check_api_docs.py` now fails a hand-written `return nil, "invalid"` and any literal reason outside that set. (cjber/forever-core#961)
- **ForeverCore publishes its own API.** It is the `"ForeverCore"` entry of `APIKit.Addons()`; `ForeverCore.API` stays a number.
- **`ForeverCore.Journey` is removed.** No addon called it.
- **Addon releases check the ForeverCore they carry.** Each consumer ZIP's ForeverCore version is checked before upload, and published GitHub and CurseForge files are audited hourly.

## [1.15.4] - 2026-11-19

### Fixed

- **The attached Forever tracker sits under Questie's quest tracker.** With Questie's tracker on, the column now goes under Questie's list and follows it as quests are added or finished, instead of covering it at the game tracker's place. (#866)
- **Attach to quest tracker reads the same in every Forever addon.** ForeverCore now provides the setting, with one label and tooltip in every language, so each addon that draws in the shared Forever tracker can show it in its own settings. The tooltip now says what the setting does: on keeps the tracker under the quest tracker, off moves it to the left of it. (#910)
- **An addon carrying its own ForeverCore starts it in every case.** It also starts when the addon is turned on after you log in, and in a session where the game's login event did not reach it. Before, it could stay waiting with no error, leaving no Forever tracker column or settings page. (#837)
- **An outdated ForeverCore install is named.** If the separate ForeverCore you have installed is too old for the addons that carry their own copy, the error now names its version and says to update it or delete its folder, since your addons carry their own copy, instead of the addons failing one by one. (#837)
- **Search ranking no longer builds a blanked copy of every title it ranks.** Ranking a name in a search list (Adventure Guide Forever) rebuilt the title with punctuation blanked, and a word list for the query, on every call. It now scans the title's own word starts directly, at the same ranking.
- **Contribution counts in the credits are translated.** German, Spanish, French, Korean, Portuguese and Russian showed "contributions" in English.

## [1.15.3] - 2026-11-19

### Fixed

- **Right-click menus open at the cursor.** The tracker's block and section menus opened below the section's bottom-right corner, far from the click. (#868)
- **Right-click menus look like the game's own.** Every Forever right-click menu now uses the same font, row height, spacing, divider, submenu arrow and hover as the quest tracker's menu, and its last row is no longer cut off at the bottom. (#875)
- **Lock the tracker is on every tracker right-click menu.** It was only inside the Tracker submenu, so a locked tracker can now be unlocked from any section or entry. (#875)
- **Right-clicking a tracker line opens its entry's menu.** A right-click on a line such as a journey step or a reagent did nothing; it now opens the same menu as the entry's title, with Lock and the entry's end action. (#875)
- **Submenus open beside the menu.** Resting on a row with an arrow opens its submenu next to it, as the game's own menus do, and the menu above stays open; there is no Back row to step through. (#875)
- **The tracker column follows the game's quest tracker as it changes.** Collapsing the quest tracker moves the column under its header, and expanding it puts the column back. When the quest tracker hides with nothing left to list, the column takes its place at once, as a reload would, instead of keeping its old spot until something else moved it. (#883, #885)

## [1.15.2] - 2026-11-18

### Added

- **The Forever tracker column sits under the quest tracker.** By default the column now starts on the last line of the game's quest list and follows it as quests are accepted, completed or collapsed, without redrawing its sections. When the column no longer fits between that line and the bottom of the screen, it sits left of the quest tracker instead, and returns under it once there is room. Right-click any Forever section and pick **Tracker position** to keep it under or left of the quest tracker; dragging the column still places it anywhere, and a locked column holds the place it has, moving left only when it no longer fits under the quest list. The "Attach to quest tracker" checkbox in Forever addons' settings works again: on keeps the column under the quest tracker, off puts it left of it, and the choice stays after a reload. During combat the column holds its place and catches up when combat ends. (#850, Refs #792, #802)

### Fixed

- **The profession side tabs stay under the game's profession tabs.** A frame another addon places at the bottom right of the Professions window no longer pulls the SkillUp and Commissions tabs to the window's bottom or off screen. (#862, Refs cjber/skillup-forever#807)

### For addon authors

- `ForeverCore.TrackerHost.GetPlacement()` and `SetPlacement("under" | "left")` read and set the column's place. Setting one releases a dragged position. `SetAttached(true)` picks Under and `SetAttached(false)` picks Left. `IsAttachedToQuestTracker()` and `GetSettings().attached` are true while the column follows the quest tracker under it, undragged, and `OnAttachmentChanged` callbacks hear each change, so an existing "Attach to quest tracker" checkbox keeps working.

## [1.15.1] - 2026-11-18

### Fixed

- **Every Forever tracker section fits its lines.** A line that gets shorter in place, such as a route's distance or a step's text, no longer leaves empty space under the section. The column also lays itself out again when Edit Mode places or moves the game's quest tracker, so text measured before then no longer clips the last line. (#827)

## [1.15.0] - 2026-11-18

<!-- discord-image: docs/screenshots/tracker.png -->

### Changed

- **The Forever quest list is gone.** Your quests show in the game's own quest tracker, or in your quest addon's. No Forever addon hides, replaces or reorders the game's tracker any more. The `/fcore quests` and `/fcore profile` commands, the profile code and the Forever addons page are gone too. (#792)
- **The Forever tracker sits to the left of the game's quest tracker,** top edges level, and follows it when you move that tracker in Edit Mode. Drag any section's header to move it, and turn on **Lock the tracker** in the header's right-click menu to keep it there. The bar above the column is gone. A position you dragged before is kept, and an older placement moves beside the game's tracker once, keeping your Lock choice. (#792, #793)
- **The minimap buttons are gone.** Open each addon from its slash command, the AddOns menu on the minimap, the game's settings or its tracker section. Map pins on the minimap stay. (#799)
- **Updates are published on CurseForge and GitHub.** Wago publishing has ended. (#649)

### Fixed

- **The Forever tracker no longer jumps** while a route loads, when you move, or when you change zone. A /reload, a quest update or a flight path no longer moves the column or redraws every section: only the section whose content changed is rebuilt, and the column settles in one frame. Section text keeps the same width whether or not it scrolls. (#795)
- **A turned-off ForeverCore is named as the problem.** An addon stopped because ForeverCore is turned off now says so, instead of naming every other Forever addon as out of date. (cjber/shortest-path-forever#996)
- **An addon that cannot start says why when you try to open it.** Its slash commands and its entry in the addon compartment now repeat the line naming the fix, such as turning ForeverCore back on, instead of doing nothing or raising a Lua error. (cjber/shortest-path-forever#996)

## [1.14.5] - 2026-11-17

### Changed

- **The Forever quest list is off by default unless you use Adventure Guide.** Players who installed ForeverCore because SkillUp, Shortest Path or another Forever addon needs it keep the game's own quest tracker, with the Forever sections next to it. Adventure Guide players keep the list. Your own choice always wins: turn it on or off with `/fcore quests`, the Tracker menu, or Options > AddOns > Forever Core. Thanks to Dayliiiiight, cheeq, reirebecca, tommyekholm and serb1tar for the reports. (#776)

## [1.14.4] - 2026-11-17

### Fixed

- **ForeverCore no longer touches the game's quest tracker when you use Questie's tracker.** With Questie's tracker on, the Forever quest list steps aside from the start, so the game's tracker no longer flashes at login or pops up over Questie's list when a quest updates. Players on the game's own tracker still get the Forever quest list, and the switch to turn it off is unchanged. Thanks to kirbs.xyz, anarchly, vladsnz, noenken and c0res1ash for the reports. (#774)
- **The shared changelog tool passes a consumer's lint on a Python 3.11 target.** It reads the UTC release date with `time.gmtime()`, which every supported Python has, instead of `timezone.utc`, which ruff's UP017 flags there. (#751)

## [1.14.3] - 2026-11-17

- **The Forever quest list steps aside for your UI suite's tracker**, including EllesmereUI. Turn the list off or on from the Tracker menu on any Forever section. (#736, cjber/shortest-path-forever#949) Thanks to dokiz, user_vyffn82yvmu3bflh and user_8vheexbirr5v6h4a for the reports.
- **Quest item icons are visible and the quest list fits the screen.** Consecutive objectives and progress bars stay aligned inside the column, and a column placed beside the game's tracker scrolls within the room below its anchor. Thanks to serb1tar, tommyekholm, Crypa7, Shuro and xh43k for the reports. (#743, #735, #603)
- **The mouse wheel scrolls a tracker section over its text.** A quest taller than its space now scrolls a page at a time with overlap, so every objective stays reachable even in a short column. Stacked sections keep a readable row when space allows and show only their header otherwise. (#616, #615)
- **Headless jobs wait in arrival order**, with live queue positions and dead-waiter cleanup. Ended leases fail with their reason and cannot carry over to a replacement session. (#734, #719, #730)
- **Headless proofs check their candidate links at capture and teardown**, and link recovery runs only under the exclusive job lock. Recovery specs use isolated client folders. (#723, #724)
- **Headless sessions restart when their helper addon changes**, and smoke, proof and dev builds fetch origin once for a missing full commit SHA. (#715, #692)
- **Headless startup stops when Battle.net needs the player to sign in.** Queued starts stay blocked until a manual launcher session reaches READY, and smoke posts nothing while blocked. (#731)
- **Client commands require the shared in-game caller marker.** Jobs preserve it and the smoke queue sets its own marker. (#741)
- **Package diagnostics name the exclusion source**, distinguishing a matching `.pkgmeta` ignore rule from an untracked or Git-ignored runtime file. (#732)
- **Headless tooling refuses jobs and input while the character is dead, a ghost or in combat**, and stops when live safety cannot be confirmed. (#619)
- **Simulator scenarios can read quest rewards and share quests, open the backpack and press override bindings.** The world map opens on a modelled map, edit boxes notify text changes on the next frame as the client does, and widget-method generation reads the annotation pin from `tools/toolchain.json`. (#632, #636, #643, #644, #668, #676)
- **Headless jobs can run in a private nested Hyprland for deskpilot**, with a bounded command and a return to gamescope before the slot is released. (#662)
- **Headless leases lock one command at a time**, exclusive jobs have a hard timeout, and a job can request session shutdown without waiting on its own lock. (#671)
- **A Forever addon's minimap button can register with LibDBIcon** so SexyMap and other minimap managers can show it on hover, move and hide it. The tooltip says it can be dragged. Thanks to Laddylucks, thirex, axejess, p1tu and Mirades96 for the reports. (#685)
- **Release tooling:** `changelog.py --check` fails on a bullet that appears twice in one section, an addon PR's package check no longer fails while a new ForeverCore awaits CurseForge moderation (the release workflow still requires the latest core), and a proof records a Lua flow as `sha256:<digest> <file>` so a file named with `api` or `key` no longer trips gitleaks. (#660, #661, #656)
- **Headless sessions check live world state before reuse** and replace sessions that reached the login screen. (#705)
- **Headless slash input requires confirmed chat focus**, and clicks refuse the Game Menu. (#703)
- **Headless state writes survive reboot**, with automatic recovery of stale addon links and store backups. (#688)
- **Slash proof flows wait for their exact command to register** and fail with its name if it never becomes available. (#684)
- **The glyph check reads every English locale shape the addons use**: `ns.L["key"]` assignments and the fields of an `ns.L = { ... }` table, as well as `L["key"]`. A key whose value is client text, not a string literal, gets no English entry. (#543)
- **The glyph check accepts reviewed XML font producers with no bindings.** Their source digests still require review when a template changes, and Lua string literals are read only for phrase keys absent from enUS entries. (#543)
- **Every Forever addon can check its translations against the game's fonts.** The glyph check ships to each addon with its own reviewed list of widgets and fonts. (#543)
- **The glyph check covers the quest tracker's fonts** and reads an addon's English phrases from its code when its English locale file lists none. (#543)
- **A consumer whose `tools/typecheck.sh` does not run the client-call lint now fails the shared tooling check.** SkillUp vendored the lint without running it. (#539)
- **Headless startup stops when Battle.net needs a game update.** It reports the launcher frame instead of clicking Play until the timeout, and stops after two Play clicks that start no game. (#316)
- **The simulator keeps native load-on-demand template initialization secure** while preserving the caller and addon template ownership. (#640)
- **Native quest header clicks have a simulator regression** using the real tracker and chat utility; the quest-list scenario no longer replaces ChatFrameUtil. (#630)

### Added

- **Addon panels share opening refusals and journeys share one owner.** Addon authors can register an opener for `ForeverCore.Open` and claim, end or subscribe to `ForeverCore.Journey`. (#381)
- **Settings pages can group controls beneath localized section headings.** Canvas pages share the native heading style and reserve room for wrapped labels without changing saved options. (#488)
- **Simplified Chinese reads naturally throughout**, with ForeverCore's lines translated by hand by moshoutegong. (cjber/adventure-guide-forever#801)
- **Traditional Chinese reads naturally throughout**, with ForeverCore's lines translated by hand by moshoutegong. (cjber/adventure-guide-forever#802)

### Changed

- **Change notes live in separate files.** Parallel addon changes can merge without conflicting over the changelog. Release tooling assembles their notes in section order. (#751)
- **The Forever quest list tells you how to switch it off** the first time it replaces the game's tracker, and its Quests menu says so plainly. (#765)

### Fixed

- **Fixed an error when leveling with the Forever quest list on.** Thanks to TechnoHunter and user_efwsfml273dlvfm5 for the reports. (#608)
- **The goal marker centres its gold diamond face in the ring**, keeping the drop shadow from shifting the face up and left. (#733)
- **A tracker menu stays where it opened while its block moves**, so a click lands on the entry you aimed at, and block menus offer Hide this section too. The tracker menu builder's Primary slot returns its description so addons can attach warning tooltips. (#754, #717, #718)
- **The attached tracker column starts below an enlarged minimap when they overlap** and the room there still shows every section, with its sections sized to that room. On a shorter screen it keeps its usual place. (#720)

### For addon authors

- **Simulator profession searches filter recipe names and refresh visible rows**, with case-insensitive matching, clearing and list-update events. (#762)

## [1.14.2] - 2026-11-16

- **The Forever quest list is now on by default and replaces the game's tracker.** Turn it off in settings, with `/fcore quests`, or from the section menu. A saved choice to turn it off is kept. (#693, refs cjber/adventure-guide-forever#468)

## [1.14.1] - 2026-11-16

- **The game's tracker stays hidden in combat while the Forever quest list is on.** Quest updates no longer make it appear over your quest list, and turning the Forever list off leaves Questie in control of its tracker. Thanks to silhouetteone for the report. (#686)
- **A ForeverCore release is checked against the addons already on the stores.** Every release candidate now loads
  with each addon's latest published release, in the simulator on every change and in the headless client, so a core
  that would break an addon players already have fails before it ships. A consumer that refuses to start on the
  candidate, which shows one error line and raises no Lua error, fails the same way, and a run that finds no released
  consumer at all is an error rather than a pass on core alone. (#666)

## [1.14.0] - 2026-11-16

- **Scenario and Maw tracker errors from ForeverCore are fixed.** With the Forever quest list on, the game's own objective tracker is hidden, as Questie does, including non-quest sections such as scenarios and bonus objectives. It comes back when the list is off. Thanks to the CurseForge player who reported it. (#608)
- **A watched quest the game reports twice draws once.** The quest list reads the client's watch list by index, and a
  repeated quest ID made it lay that quest's block out twice in one pass, which the client refuses with "Cannot anchor
  to a region dependent on it" while the tracker lays itself out. Each unique quest now gets one record and one block.
  Thanks to a player on CurseForge for the report. (#609)
- **A Forever addon now tells you when ForeverCore is missing or turned off.** Each addon loads even without ForeverCore
  and shows one line naming the fix: install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge
  app, because the app does not restore ForeverCore from the other addon's row. If ForeverCore is installed but
  disabled, the line asks you to enable it in the AddOns list. (#659)

## [1.13.0] - 2026-11-16

- **A different addon named ForeverCore no longer breaks every Forever addon.** If another addon installs its own folder named ForeverCore over ours, each Forever addon now shows one line naming that addon, asking you to remove it and install ForeverCore from CurseForge, instead of saying it could not start. (#610)

- **Tracker sections can change their height cap.** Addons can update a registered section through Core while keeping shared scrolling, responsive bounds and combat deferral. (#618)

- **Release zips are exercised before upload.** The release gate loads the extracted package through the shared simulator and refuses missing files, runtime errors and a package folder that differs from the tested archive. (#203)

- **Quest headings keep their own quests.** On-map class and zone quests stay under their quest-log headings as distances change. (#177)

- **Forever tracker sections follow Kaliel's Tracker.** They sit below its visible quest list and follow its font and collapse controls. Thanks to kowakowa93 for the contribution (#602).
- **Tracker rows keep their full width and quest item art.** Long headers fit the section width, and scrolling leaves room for quest markers and item buttons. Thanks to xh43k for the report (#603).

- **The journey marker's diamond sits in the centre of its ring.** Its placement now preserves the half-pixel
  position needed to centre the artwork without shifting it left or right. (#611)

### For addon authors

- **The embedded-core loader is ready for consumer packaging work.** Consumer packaging must adopt the embedded
  copies before an installation can use this runtime path; this release does not change existing consumer packages.
  (#448)
- **Developer profession proof flows open securely.** `/devsmoke prof` offers a visible secure Cooking opener and
  selects the requested tab after the window opens, without calling a protected API from chat. (#613)
- **Proof startup failures keep their real cause.** A failed client startup no longer holds its own session lock while
  the proof classifies the error as another session, so authentication and timeout failures remain distinguishable.
  (#573)

## [1.12.1] - 2026-11-14

- **The Professions tab of your Forever addons no longer hides under another addon's tab.** If another addon also put
  a side tab on the Professions window, its tab could sit exactly where SkillUp's or Commissions' tab was, so our tab
  looked missing or could not be clicked. The Forever tabs now start below whatever is already in that column and move
  out of the way when another addon's tab appears. Thanks to Da_Tronic, tazrulez and contrabiscuit for the reports.

## [1.12.0] - 2026-11-14

<!-- discord-image: docs/screenshots/profile.png -->

- **`/forever profile` gives your character a card you can share.** It gathers what your Forever addons have
  recorded for this character (quests turned in, distance travelled, recipes learned, creatures met and more) into one
  link, already selected for Ctrl+C. Open it in a browser to see the card. Nothing is sent and nothing is saved: the
  card is drawn from the link itself, so sharing the link is sharing the card. Addons you do not use are left out.
  (#443)

- **The Forever quest list reads like the game's tracker and scrolls.** Turn it on with `/fcore quests`: every unfinished count gets a thin progress fill, clicking a zone heading folds it and keeps its count ("Darkshore (2)"), the quest menu folds one quest and can route an objective with Shortest Path, and the Quests header counts what is tracked. Quest item buttons sit on their quests, and a list taller than the column scrolls under its header; combat freezes the view so every button stays beside its quest. The game's own Quests and Campaign sections leave the tracker while the list is on, so its own header is the only one above it. (#177)

### For addon authors

- **A quest log tab can be hidden without losing its panel.** `ForeverCore.QuestLogTabs.SetTabShown(key, false)` takes
  an addon's tab out of the column and the buttons above and below close the gap in the same order, and
  `SetTabShown(key, true)` puts it back in its slot. `Select(key)` still opens the panel of a hidden tab, and hiding the
  tab whose panel is open leaves that panel open until another tab or the quest log is chosen, so an addon can drop its
  tab when it has nothing to show without taking the page away. An unknown key does nothing and returns false; a known
  one returns true. (#583)

- **A tracker section can cap its own height.** `TrackerSection.Create` takes `maxHeight`: 200 UI units when omitted, or `"remaining"` for what the column's other sections leave. A taller section scrolls under its header with the client's minimal scrollbar, keeps the top block in place across updates, moves one block per wheel step, and freezes in combat. (#177)

- **A Lua proof flow reports its own snippet's result, not the session before it.** `--flow NAME=file.lua` and
  `forever_client.py eval` reload once to run a snippet and then read `DevSmokeDB.eval`, but SavedVariables reach disk
  only at the next reload, so the file still held the previous eval: a snippet that raised passed the proof on an
  earlier run's success, and a clean one failed on an earlier run's error. `tools/devsmoke/eval.py` now stamps every
  generated `Eval.lua` with a fresh run token, `!!DevSmoke` copies it into `DevSmokeDB.eval.run`, and the reader reloads
  once more and answers only the record carrying that token. A failed flow fails the proof with the snippet's own
  error, before any gist or `.visual-proof.json` exists. (#580)
- Native settings pages can register section headings through `SettingsSections.Register`, using Blizzard's row layout and focus handling (#488).

## [1.11.0] - 2026-11-13

### For addon authors

- **Step markers numbered 1 to 25, an empty ring and a ring with a diamond, for every Forever addon.**
  `ForeverCore.Art.Marker(number)` answers the gold numbered marker for a step, `ForeverCore.Art.Ring()` the empty ring
  a place a route visits twice stacks behind its marker, and `ForeverCore.Art.Diamond()` that ring with the goal pin's
  diamond in it for a step that has no number next, all drawn from core's `media/Numbers`. The numbered files and the
  ring are byte for byte the ones Adventure Guide Forever and Shortest Path Forever ship, so an addon can drop its own
  copy and read core's instead; `ForeverCore.Art.minor` is 2. `tools/export_markers.py` writes them from
  `tools/marker_source`, and its `--check` fails when a committed marker differs. (#570)
- **A visual proof is one command, on a release prep or a Core pin bump.** `tools/headless/forever_client.py proof
  --repo <repo> --ref <sha> --checkout <tree> --flow "update notice=<slash command or Lua file>"` builds and links the
  commit as `smoke` does, reloads once, runs each named flow (a Forever addon's own slash command, or a Lua file
  through `!!DevSmoke`), screenshots each and uploads the PNGs to a new secret gist. It writes
  `<checkout>/.visual-proof.json` from `visual_proof --digests` with full-SHA raw URLs and each image's sha256, then
  checks the installed build with `visual_proof --compare`; every AddOns slot is put back and the checkout is never
  committed or pushed. A release preparation and a sync pull request that moves the ForeverCore pin run it, so the
  required `visual-proof` check passes without `--admin`; `tools/sync_consumer_prs.py` prints the command for a sync
  pull request whose changed files need a proof, because it cannot drive the client itself. ForeverCore has no shared
  opener for an addon's update notice, so the flow is always named. (#563)
- **A sync PR that merges while the sync runs no longer fails it.** The run looked up the open `forever-core-sync`
  pull request, and when that PR merged and its branch was deleted before the commit, the commit failed with "Branch
  not found". The sync now opens a fresh branch and pull request from the new `main` instead. (#559)
- **An addon whose CI lives outside core's can install its tools from the shared toolchain action.** The action's `lua`
  set also installs the PUC Lua 5.1.5 interpreter as `lua5.1`, beside the `luac5.1` compiler it already built, and
  `verify.sh` checks both against the manifest. Every cache key now hashes the action's own `build.sh` and `install.sh`
  as well as the tool's pins, so an edited script no longer restores a cache it did not build. Kiln Forever now
  receives `tools/toolchain.json`, `tools/pyproject.toml` and `tools/uv.lock` under `addon/KilnForever/`, as the
  published addons do, so its CI reads the one pin manifest and the one `uv` group.
- **A sync PR keeps the commits added to it.** `tools/sync_consumer_prs.py` rebuilt every consumer's
  `forever-core-sync` branch from `main` on each push to core `main`, so a commit pushed to an open sync pull request (a
  recorded visual proof, say) was dropped without a word. The sync now runs on the open pull request's own head and
  adds its commit on top, so those commits stay, and a pull request it cannot update in place is left exactly as it is
  with a comment saying why. (#531)
- **The client-call lint reaches every addon.** `tools/lint_client_calls.py` is now vendored into every published
  addon through the sync, so `tools/check_core_shared.py` fails a copy that is missing or differs from core. Add
  `python3 tools/lint_client_calls.py` to the addon's own `tools/typecheck.sh`, and declare a global an optional
  dependency provides in `tools/client_optional.txt`, one `Name  OwningAddonFolder` line per function with the folder
  in the root TOC's `## OptionalDeps`. The lint refuses a call of a client function the Forever client does not have,
  which type-checks against the retail annotations and then fails in game with `attempt to call a nil value`. (#539)
- **A stopped smoke no longer leaves its AddOns links behind.** A smoke that is killed where no Python handler runs
  (SIGKILL, or a signal aimed at the shell around it) used to leave the build linked over `ForeverCore` and the store
  install at `<folder>.smoke-backup` until someone noticed. The record `~/.local/state/forever-client/smoke-links.json`
  now names the session that wrote it, by pid and start time, and the next `up`, `run`, `smoke` or `build-dev` replays
  it through the one `restore_links` teardown before it touches AddOns, then says what it put back. A record whose
  session is still running, including the smoke's own `up`, is left to that session, and a record it cannot read
  refuses instead of guessing. SIGTERM, SIGHUP and SIGINT all restore in-process, and `up` handles a hangup like the
  others. (#555)

## [1.10.0] - 2026-11-13

- **A bug report can ask for the client's debug logs without a developer's addon.** `/forever debug on` saves the
  client's current taint log, advanced combat log, chat log and combat log settings, turns each on, and keeps the
  originals in ForeverCore's saved variables across a reload. The report window and the settings pages built on
  ForeverCore's page (its own and Field Guide's) say debug capture is on and how to stop it, the report names the client's `Logs` folder, and `/forever debug off` or the
  next login puts the client's settings back. Nothing is sent anywhere. (#534)
- **Bug reports now carry a performance table.** The report window reads the client's own add-on profiler once when
  it opens: every loaded addon that depends on ForeverCore gets its average, current, peak and last frame time, its
  counts over 1, 5, 10, 50 and 100 ms, and its memory, with the all-addon and whole-application figures above them.
  A client without those APIs gets one line saying so, and nothing is sampled while playing. (#535)
- **Bolton_wow is on the Thanks page** for the report that map arrows would not switch maps. (#486)

### For addon authors

- **A smoke can click Play itself.** `smoke --manual-launcher` passes the flag through to `up`, so while launcher OCR
  is not finding Play an agent starts the smoke in the background, takes `shot` and left-clicks Play, exactly as with
  `up --manual-launcher`; the default and `tools/smoke_queue.py` still click Play by OCR. (#547)
- **A manual release can waive a failed visual proof.** `tools/release_check.py --skip-visual-proof` accepts a
  completed full CI run on main whose only failed job is `visual-proof`; every other job must still pass and the
  `headless-smoke` gate still applies. An addon's Release workflow passes it from a `skip_visual_proof` dispatch input.
  (#552)
- **A release needs a green `headless-smoke` on its exact commit.** `tools/release_check.py` reads the newest commit
  status in that context beside the full CI run, so a commit the client never loaded is not released: a missing or
  pending one waits and names the command that fills it in, and a failed one prints what it found.
  `python3 tools/headless/forever_client.py smoke --repo <repo> --ref <sha>` builds that commit, runs
  `/forever selftest` and `errors --addon` for each of its addon folders in the headless client, and posts the status;
  exit 3 means the player's client or another session holds it, so nothing is posted. `tools/release_consumers.py`
  reports such a commit as waiting rather than failed, and `tools/smoke_queue.py` with its `forever-smoke` timer fills
  the status in for every commit a release would ship. (#540)
- **The simulator exercises every addon with no scenario file, and clicks the addon's own widgets.** `run.lua` runs
  `sim:exercise()` after the declared scenarios, so an addon no longer needs `tests/sim/exercise_scenario.lua`; a
  declared scenario still passes the exercise its own commands and saved variables. An addon that depends on
  ForeverCore gets that checkout loaded for the exercise, from `FOREVER_CORE` or `../forever-core`, so its UI is
  really built. The exercise hovers, left-clicks and leaves every shown Button the addon created, in and out of
  combat, so a refused call in a button handler fails the run. `C_TradeSkillUI.OpenTradeSkill` and `C_UI.Reload` are
  modelled as the client enforces them, and `fetch.py --refresh-restrictions --probe` merges every block a live
  client recorded into `restrictions.txt`. (#538)
- **An addon's `ty` run passes over the vendored simulator.** `forever_sim/fetch.py` gives a probe hit a `ProbeHit`
  dataclass and reads it by attribute, and core's `forever-tools` job type-checks `forever_sim` with `ty` beside
  `forever_tools`, so an addon whose CI checks its `tools/` with `ty` no longer fails on the vendored file.

## [1.9.0] - 2026-11-12

### For addon authors

- **A Cooldown Manager icon frame is one core call.** `ForeverCore.Art` (minor 1) publishes `Icon` and the new
  `CooldownIcon`, which draws an icon with the client's own `UI-HUD-CoolDownManager-Mask` and
  `UI-HUD-CoolDownManager-IconOverlay` atlases and returns the overlay. The mask and overlay are built once per
  texture, so a refresh moves the same pair instead of stacking another. See `docs/api.md`. (#525)
- **Mock renders draw `|T` icons given by FileDataID.** `tools/wowmock` looked such an escape up as a path, which
  never matched and stalled the render; it now reads the ID directly, as the client does. (#524)

## [1.8.2] - 2026-11-12

- **Forever Leaderboards and stats sharing are gone from every Forever addon.** Nothing is sent to other players, and
  the short hitch some players saw every 10 seconds is gone. (#443, #512)
- **The Forever quest list draws one heading per zone.** When some of a zone's quests were on your map and others were tracked from elsewhere, the zone's heading was built twice, once per group, which could throw an interface action failure while the tracker laid itself out. Each zone now draws one heading with all its quests under it. Thanks to user_efwsfml273dlvfm5 on CurseForge for the report. (#521)

### For addon authors

- **`ForeverCore.API` is 2.** `ForeverCore.Leaderboards` and `ForeverCore.PeerStats` remain only as inert stand-ins, so an older release that still calls them loads without errors: they return empty boards, store nothing and send nothing. Remove those calls. See `docs/api.md`. (#443)
- **Every addon repo carries the same `.github/FUNDING.yml`.** It is now a vendored file, so `tools/check_core_shared.py` fails an addon that lacks it or differs from core, and `tools/sync_consumers.py` copies it in. (#517)

## [1.8.1] - 2026-11-12

- **Addons no longer bring an older ForeverCore with them.** Every Forever addon's zip now carries the newest ForeverCore release, so updating one addon can no longer downgrade the shared code another one needs.

### For addon authors

- **A stale ForeverCore pin fails CI and the release before anything uploads.** `python3 -m tools.forever_tools.core_pin --latest` requires `tools/forever-core.txt` to equal cjber/forever-core's latest published GitHub release and fails closed when that release cannot be read. The package job runs it in every consumer through `tools/check_package.py`, and the sync inserts the same step directly above the packager in each consumer's `release.yml`, so a core release that lands between CI and the upload is still caught. The `.pkgmeta` ForeverCore external and the TOC `## X-Forever-Core:` must name the same tag; an addon with no ForeverCore external is exempt from the bundle comparison but still gets the pin gate. (#514)
- **`ForeverCore.ProfessionTabs.minor` is 2.** Minor 2 means the native profession pages are hidden beneath a selected addon page and restored when the window is handed back to the client. Require `minor >= 2` before relying on that, and see `docs/api.md`. (#514)
- **The suite's name is ForeverCore, one word.** `tools/check_core_name.py` fails a change that adds the two-word spelling in any text file, while shipped changelog history is left alone. It is vendored with the other project rules and runs in every consumer's `core-shared` job. (#514)

## [1.8.0] - 2026-11-12

<!-- discord-image: docs/screenshots/tracker.png -->

- **Addon settings open cleanly.** Opening a settings page no longer shows an interface action failure message.
- **Map arrows open the destination map again.** Clicking the tram connection switches between Stormwind and Ironforge without asking you to turn the map yourself (#486).

### For addon authors

- **Tracker menus have one declarative contract.** Pass `menu` and optional `click` to `TrackerHost.Attach` for section and block targets with fixed Title, Primary, Action, Open, End and Tracker slots. The old section hook remains compatible for one migration release, and combat-only actions are visibly disabled.

## [1.7.4] - 2026-11-12

- **Profession tabs hide the native controls cleanly.** Switching to a Forever profession page no longer leaves the game's crafting controls visible underneath it, and returning to a native page restores the controls and their original transparency.
- **Profession tabs keep their intended size.** SkillUp and Commissions share one stable width, including when opened straight from the overview. Returning to the game's profession pages restores their native size.

## [1.7.3] - 2026-11-11

- **ZiiMs is on the Thanks page** for the EllesmereUI tracker support that started in cjber/shortest-path-forever#621.

### For addon authors

- **A consumer's CI can build its Lua toolchain without apt.** `.github/actions/lua-toolchain` in this repository builds LuaJIT 2.1 at the v2.1 commit Ubuntu packages and luacheck 1.1.2 with argparse 0.7.2 and luafilesystem 1.9.0, all from pinned GitHub sources, caches the installed prefix with `actions/cache`, and adds `luajit` and `luacheck` to `PATH`, so a runner whose Ubuntu mirror cannot resolve no longer fails the job. Adopt it after `actions/checkout` with `uses: cjber/forever-core/.github/actions/lua-toolchain@<sha>`, pinned to the commit the consumer's other ForeverCore tooling comes from, and drop its `apt-get install` step. (#450)
- **A widget's own client method that takes parameters can no longer be passed straight as a script handler.** `edit:SetScript("OnEditFocusGained", edit.HighlightText)` hands the client's method to the client, which calls it with the handler's arguments, so `HighlightText` reads `true` as its first parameter and raises; it broke four addons in #269 and SkillUp Forever's shopping list in skillup-forever#622. `forever_tools/widget_handlers.py` now fails a `SetScript` or `HookScript` whose handler is exactly a field read of a widget method that declares a parameter (`edit.HighlightText`, `edit["HighlightText"]`, `frame.StartMoving`), and passes a wrapping closure, a function the addon wrote, any other field read, or a method that declares none: `frame:SetScript("OnDragStop", frame.StopMovingOrSizing)` and `edit:SetScript("OnEscapePressed", edit.ClearFocus)` ignore the handler's arguments and are correct as they stand. The package job every addon already runs enforces it with no addon edit. The method set comes from `forever_tools/widget_methods.txt`, generated by `tools/gen_widget_methods.py` from the Ketho API annotations at the revision `tools/typecheck.sh` pins, never a hand list. (#449)
- **`wowmock` can measure an atlas without downloading its sheet.** `Ui.atlas_size(name)` returns the width and height in UI units that `Ui.atlas(name)` reports for the member the client draws, or `None` when the element is unknown or has no member, reading only the atlas tables.
- **A core release re-releases every addon, even when its newest sync entry was already released.** `tools/sync_consumer_prs.py` treated any marked `CHANGELOG.md` entry as pending, so after a consumer's sync entry was tagged and released, the next core release moved its pin but added no new entry for `tools/release_consumers.py` to dispatch. A marked entry is now pending only while its own `vX.Y.Z` tag is missing from the consumer's remote, and an entry is added whenever the consumer's latest released tag bundles a core different from the new pin, so a re-run repairs a consumer whose `main` already pins the new core while its latest release ships an older one. (#471)

## [1.7.2] - 2026-11-11

- **The Professions overview is its own width again.** Since SkillUp's wide recipe list, the overview page with every profession's bar took the widened crafting width, leaving a wide empty strip to the right of its panels. The overview now keeps the game's own width, and the recipe list and every Forever addon's tab keep the one wide width as before. Thanks to qwertzyxc on Discord for the report (cjber/skillup-forever#636).

### For addon authors

- **A consumer can take core's tooling fixes through `sync.py update` again.** `forever_sim/sync.py update` judged the producer's `MANIFEST.json` with the running copy's own file walk, so a consumer whose vendored `sync.py` predated a data file such as `restrictions.txt` refused with a false "the producer's MANIFEST.json is stale". It now judges the producer by the names its own manifest lists, exactly as `forever_tools/sync.py` has since #366, so a consumer carrying the older updater still takes the new files. (#467)

## [1.7.1] - 2026-11-11

### For addon authors

- An addon spec that loads core without `UI/Credits.lua` no longer fails in `Expose.lua`. (#461)
- **The vendored client slash word list no longer trips an addon's file-size rule.** `tools/client_slash_words.txt` now carries a `file-size-no-growth` ignore marker in its header, so a consumer's `tools/repo_rules.py` stops failing the generated list for growing past 1000 lines while `tools/check_slash_words.py` still skips those header lines when it loads the words.
- **An addon's simulator gets the restriction classes it reads.** `forever_sim/sync.py` now carries `restrictions.txt` with the code, so a consumer sync no longer leaves `docs.lua` failing with "no restrictions.txt beside docs.lua". A consumer whose vendored `sync.py` predates this takes the new `sync.py` before its first update.

## [1.7.0] - 2026-11-11

<!-- discord-image: docs/screenshots/tracker.png -->

- **The tracker column keeps its size with a replacement quest tracker.** It now follows the scale of the frame it actually sits beside: Blizzard's tracker only while that frame is visible and not transparent, another tracker's list, or the screen when detached. A UI that hides or shrinks Blizzard's tracker no longer shrinks every Forever section with it. (#383)
- **The tracker column follows EllesmereUI's custom quest tracker.** With its Custom Quest Tracker on, the column sits below the filtered list the player sees instead of the hidden native quests, and moves with it as it grows, shrinks or is dragged. EQOT still wins above it and Questie is consulted after it. Fixed on GitHub by ZiiMs. (#332)

### For addon authors

- **A slash command the client already owns fails the gate.** `tools/check_slash_words.py` compares every addon `SLASH_<KEY><n>` word with the client's own GlobalStrings in all shipped locales (`tools/client_slash_words.txt`) and names the file, line, word and client key, so a `/ma` that the chat box runs as main assist never ships unnoticed. `sim:slash` refuses such a word too, so an addon whose command the client shadows fails its exercise run. (#323)
- **The simulator boots the client's Escape handler registry and presses Escape.** `Sim:pressEscape()` runs `ToggleGameMenu` as fresh input, `sim:exercise()` presses it in and out of combat, and `Blizzard_GameMenuEsc` is loaded at startup, so an addon handler registered there is reported with `Blizzard_GameMenuEsc.lua`, the slot it wrote and the writing addon. (#315)
- **A restricted function is refused by its wiki class, not combat alone.** `forever_sim/restrictions.txt`, generated by `fetch.py --refresh-restrictions` from warcraft.wiki.gg and committed, gives every documented `HasRestrictions` function and widget method one of `nocombat`, `hwevent` or `always`; `hwevent` is allowed only inside a hardware input such as `sim:input` or `sim:click`, and an untagged name keeps the old combat-only rule. Observed client behaviour overrides the wiki class in one table, each entry naming its issue. (#297)

## [1.6.1] - 2026-11-11

- **The tracker column stops flashing and rebuilding when the quests reach the bottom of the screen.** It no longer lays the sections out in the room below the tracker just to measure it, so a quest update no longer replays every header's add animation and rebuilds every block. The column moves above or beside the tracker only when it has to, and returns below as soon as the quests leave room for the whole column. (#438)

### For addon authors

- **A changed family block reaches every addon.** The consumer sync runs the addon's `tools/check_family.py --fix` after the phrase template, so its README.md and docs/curseforge.md family block matches `forever_tools.family` and its typecheck job no longer fails when core changes that text. (#454)

## [1.6.0] - 2026-11-11

<!-- discord-image: docs/screenshots/thanks.png -->

- **The Forever addons page has a Thanks page.** Every player who reported a bug, asked for a feature or translated an addon is named once, ranked by how many contributions they gave, with a count after the name and the addons they helped; hovering a row lists what they did for each in full, beside a short **Inspired by** list. A dropdown filters the page to one addon, an addon's own settings page opens it already filtered to that addon, and the choice survives closing and reopening it. Anyone who asks not to be credited is left off. An addon's own settings page can also show a one-line thanks for its players. (#419)

### For addon authors

- `ForeverCore.Credits` (minor 1) draws the **Thanks** page. `Register(addonTitle, credits)` takes the addon's generated `ns.Credits` under its `Family.ADDONS` name, `Line(addonTitle)` returns the short "Thanks to ..." line for its settings page, `Players()` and `Inspired()` return the merged rows, and `Open(addonTitle?)` shows the page filtered to one addon or every addon. `tools/forever_tools/credits.py` writes `Data/Credits.lua` from THIRD_PARTY.md's new `## Players` and `## Inspired by` tables, one row per shipped contribution, and keeps the one-sentence thanks in README.md's `## Credits` and docs/curseforge.md; `--check` fails a stale file or block. A name in `credits_opt_out.txt` beside the tool makes the run fail until that row is removed, so a player who asked not to be credited is never written. WFA-31 and WFA-33 document the tables, the opt-out, and that the addon's author is never listed. (#419)
- **A core release re-releases every addon.** Each consumer's zip carries ForeverCore in the same folder, so the latest release of every addon must ship the same core. A moved pin now also rewrites that addon's `.pkgmeta` ForeverCore external and its `## X-Forever-Core:` TOC field, and adds a release entry to its `CHANGELOG.md`: the next patch, dated today, marked `<!-- forever-core-sync -->`, with the notes under `## [Unreleased]` kept above it. `tools/release_consumers.py`, run every 20 minutes, dispatches each addon's own `release.yml` for that entry once its tag is missing, no release is queued or running, and full CI on main is green.
- **The out-of-date warning survives an English-only phrase table.** An addon whose `ns.L` maps each English phrase to `true` no longer throws inside the warning's `string.format` and hides the warning behind a load error: `tools/consumer/ForeverRequire.lua` now takes a phrase only when it is a string and falls back to the key otherwise.
- **`tools/check_consumers.py` checks the TOC's core tag.** An addon whose root TOC lists ForeverCore in `## Dependencies` now also fails when `## X-Forever-Core:` is missing or differs from `tools/forever-core.txt`, the field a sibling addon reads to name an out-of-date core.

## [1.5.0] - 2026-11-11

<!-- discord-image: docs/screenshots/tracker.png -->

### For addon authors

- `ForeverCore.ProfessionTabs.SetMinWidth(key, width)` lets a registration change its `minWidth` after it registered. It recomputes and enforces the one window width across tabs and professions, `nil` clears it, and in combat the change waits with the module's other frame work. `ForeverCore.ProfessionTabs.minor` is now 1. (#433)

## [1.4.1] - 2026-11-11

### For addon authors

- **Each addon's ForeverCore pin follows core's releases.** The consumer sync moves `tools/forever-core.txt` to the latest release tag in the same PR as the tooling, and the drift gate fails a consumer whose pin lags, whose `.pkgmeta` ships ForeverCore as an `externals:` entry, or that requires core without `- forevercore` under `required-dependencies:`, so an addon's specs and CI no longer test against a core no player runs. (#420)
- **Core no longer declares the client global `ProfessionsFrame`.** An addon that declares it with its own window type no longer gets the union of both, so a typecheck that assigns its frame to its own type passes. (#427)

## [1.4.0] - 2026-11-11

<!-- discord-image: docs/screenshots/tracker.png -->

### For addon authors

- `tools/forever_sim/toc.lua` reads a TOC the way the client does: `files(root, tocName)` lists Lua files and expands each XML's `Script` and `Include` children in order, and `templates(path)` lists its virtual templates, so a consumer's spec loader can load `UI/TrackerSection.xml` and move its ForeverCore pin past v1.1.0. (#412)
- `ForeverCore.ProfessionTabs.Register(key, spec)` adds a side tab under the client's own Professions tabs, in registration order. `spec` is `{ icon, tooltip, page, minWidth?, onSelect?, safeCall? }`, `minWidth` raises the one width the window keeps, and `Select(key)`, `ShowNative()` and `Selected()` drive and read the same state. (#382)

## [1.3.2] - 2026-11-11

### For addon authors

- **The performance report stops overstating SavedVariables.** `tools/forever_perf.py` summed every account's and character's copy of a file into one figure and printed it as the size the client parses at login. Each row now reports what one login actually reads, the account file plus the largest per-character file, and the across-character total is labelled as disk use. (#385)
- **`sync.py update` no longer fails a consumer with a false "manifest is stale".** It took the file list from the running copy's `DATA_FILES`, so a consumer whose vendored `sync.py` predated a new data file saw a mismatch and refused to update even though the producer's manifest was correct. It now takes the file list from the producer's `MANIFEST.json` and names the missing, unlisted and changed files on a genuine mismatch. (#366)

## [1.3.1] - 2026-11-11

<!-- discord-image: docs/screenshots/tracker.png -->

- **Right-click menus show real checkboxes and arrows.** A checkbox row now puts the game's own tick box beside its label, a radio row puts the game's radio dot, and a submenu row shows the game's arrow on the right instead of a ">" in the text. (#379)

## [1.3.0] - 2026-11-11

<!-- discord-image: docs/screenshots/leaderboards.png -->

- **Forever Core is listed as a library.** The addon list files it under Libraries, and its description says there is nothing to set up. Every Forever addon's **Forever addons** settings page also has a **Forever Leaderboards** row, to open the leaderboards and see where you stand. (#390)
- **Forever Leaderboards fits the board it shows.** The window grows with the list instead of leaving empty space, with separate **This week**/**All time** and guild/players menus, a Total column and a gold bar on every row, your own row pinned below a gold rule when it falls outside the top ten, and plain words on an empty board. (#387)
- **The leaderboards reach further.** Each addon now passes on the freshest rows from up to 500 players you have met in the last 30 days, spread over the normal send budget so nothing is sent too fast, and a passed-on row keeps the player and time it came from. A row is never sent back to the guild or group it was heard from. The board also opens on **Players you've met**, the widest reach, and remembers a narrower choice if you pick one. (#389)

### For addon authors

- `ForeverCore.APIKit` (minor 2) gains the error answer and suite discovery. `Invalid()` returns `nil, "invalid"` for a read that refuses its argument, so `NotReady` keeps taking only `"loading"`, `"disabled"` and `"none"`; `ForeverCoreAPIAnswer` is the type for a read that can answer either. `Publish(addonName, api)` hands core an addon's public API table once at load (a non-empty name and an integer `version`, or a programming error), and `Addons()` returns a fresh list sorted by name of `{ name, version, minor, api }` with `version` and `minor` read at call time. `docs/api-conventions.md` documents the new members and `docs/api.md` is ForeverCore's own page for third-party authors: the members they may rely on and the examples that list and subscribe to every published API. Check a minor 2 member with `(ForeverCore.APIKit.minor or 1) >= 2`. (#392, #398)

## [1.2.0] - 2026-11-10

<!-- discord-image: docs/screenshots/tracker.png -->

- **The Forever sections line up with the quest tracker.** Their headers and bars no longer start a little to the left of the game's own sections: they now begin and end on the tracker's edges at any scale. Thanks to iPulse for the report. (#335)
- **One client icon per addon.** Every Forever addon now declares its in-game identity icon once, in `## X-Forever-Icon`, so its minimap button, Professions or side tab, window portrait, leaderboard tab and addon compartment cannot drift apart. The shared check fails an addon TOC that omits the field, a value the pinned client build does not have, or the same path repeated in shipped Lua. (#331)

### For addon authors

- Add `## X-Forever-Icon: Interface\Icons\<name>` to the TOC, read it with `C_AddOns.GetAddOnMetadata(addonName, "X-Forever-Icon")`, and pass that value to every identity surface. `forever_tools.identity` runs in the assets check, and `docs/asset-registry.md` records each addon's icon. The TOC `## IconTexture` stays the drawn `media/Icon`.
- `ForeverCore.TrackerSection.Create(name, mixin, opts)` builds and attaches a tracker section, with `UpdateText`, `Room` and `AddMore` for its lines. `ForeverCore.TrackerLine.SetInteractive` and `SetHeaderTooltip` wire clickable objective lines and block header tooltips through `ForeverTrackerInteractiveLineTemplate`. The column now records one section's layout error in its own journal and still lays out the sections below it, and calls `module.OnHeaderClick(button)` for a header click other than the right-click menu. `docs/adoption.md` names each call.
- `forever_tools.specs` runs every `tests/*_spec.lua` in parallel, prints each spec's output in glob order with its time, and names every failure; `python3 -m tools.forever_tools.specs` replaces the shell loop in `check`. The generated-data gate (`forever_tools.generated`) now runs its fresh and offline passes at the same time, rerunning the offline pass after the first only when that pass changed its inputs. Pull-request workflows cancel a PR's superseded runs and every job sets `timeout-minutes` (WFA-15).

## [1.1.0] - 2026-11-10

- **One tracker column again.** With an older Forever addon still installed, its tracker section no longer draws on top of the others.

### For addon authors

- `ForeverCore.APIKit` (minor 1) is the shape every addon's own API follows. `Hub(addonName, channels, ready)` returns `{ Subscribe, Queue }`: one dispatch on the next frame per burst of changes, a fresh `{ change = true }` table naming only the changed channels, idempotent unsubscribe, and each callback under the addon's `SafeCall`. `NotReady(reason)` returns `nil, reason` for `"loading"`, `"disabled"` and `"none"`. `docs/api-conventions.md` states the conventions every addon API follows, and `tools/check_api_docs.py` checks an addon's `Core/API.lua` against its `docs/api.md`.

<!-- discord-image: docs/screenshots/tracker.png -->

## [1.0.0] - 2026-11-10

<!-- discord-image: docs/screenshots/tracker.png -->

- **The Forever addons lists cover all eight published addons.** The README and store family block, the Discord digest and the in-game Forever addons page now name Field Guide, Commissions and Macro Assist too, the digest takes its addon order and names from the one family table, and a test fails when the lists disagree. The digest also has emblems for Commissions and Macro Assist. (#363)
- **Forever Core is now its own addon on CurseForge and Wago.** Every Forever addon requires it, and the stores install it automatically, so there is nothing to choose or configure. It is the one copy of the shared code: the tracker column, the report window, the leaderboards, the error journal and debug log, the minimap button, the quest log tabs and the settings chrome.
- **Every Forever addon shares one tracker column.** Scale, Lock and position are one setting for the whole suite: change the tracker in one addon and every section moves together, instead of one addon's slider moving only its own part.
- **Your tracker settings carry over.** The first Forever addon to load offers its old saved tracker table, and Forever Core copies the scale, lock, attachment, background and position into its own settings once. Nothing needs setting up again.
- **The world map and the settings panel open through the client, not through the addon.** `C_Map.OpenWorldMap` and `C_SettingsUtil.OpenSettingsPanel` are restricted client functions: called directly from addon code, the client refuses them and blames the addon, which is what the nightly Suite load saw in Shortest Path, Legacy, Tweaks and SkillUp. The shared `Core/OpenMap.lua` and `Core/OpenSettings.lua` run each request through `CreateSecureDelegate`, so it executes as the client, never in combat, and reports false when nothing opened so the caller can say why. On a build without the delegate both stay closed instead of erroring. (#333)
- **The asset check follows a `BACKDROP_*` global to the art it draws.** A backdrop constant was only an identifier to the checker, so `SetBackdrop(BACKDROP_TOAST_12_12)` passed while the two loose toast files it names are pre-Legion chrome. Each backdrop's `bgFile` and `edgeFile` now comes from the pinned build's `Blizzard_SharedXML/Backdrop.lua` through a generated `backdrops.txt` beside `legacy_chrome.txt`, and those paths get the same FileDataID age rule as a literal path. (#320)
- **`run --wait` queues until the Wine prefix is free.** The waiter took the session lock and checked the prefix once, so a wineserver still winding down from the previous session, or another waiter taking the lock first, made it give up without running its command. It now holds the lock and keeps checking until the prefix is empty, or exits non-zero with a message when `--timeout` passes. (#317)
- **A consumer sync PR no longer closes itself, and carries its phrase template.** `tools/sync_consumer_prs.py` pointed `forever-core-sync` at the consumer's `main` head before creating the sync commit, so between the two calls the PR's head equalled its base and GitHub closed it; the commit is now built on a scratch branch from `main` and the sync branch moves once to that commit. A consumer with `tools/phrases.py` also gets its `Locales/phrases.txt` regenerated in the same commit, so its locale spec passes; the extractor runs with the consumer's root importable, so one that imports `tools.forever_tools` as a package (Tweaks) works too. (#330)
- **A consumer sync installs the updater it runs.** `tools/sync_consumer_prs.py` ran each consumer's own vendored `forever_tools/sync.py` and `forever_sim/sync.py`, so a core release that adds a vendored data file (`backdrops.txt` in #339) was checked by an updater whose `DATA_FILES` does not list it: it hashed 27 files against a 28-file manifest and refused, failing every consumer's sync with "the producer's MANIFEST.json is stale". The producer's `sync.py` is now copied over the consumer's before `update` runs, so a release that adds a vendored file reaches consumers still carrying the older updater. (#341)
- **forever_sim closes the Professions window the client way and records table-constructor taint.** `C_TradeSkillUI.CloseTradeSkill()` clears the open trade skill and fires `TRADE_SKILL_CLOSE`, so the window's own handler hides it, and a field a table constructor names (`{ x = value }`) carries the writer's taint exactly as `t.x = value` does. A secure delegate still starts secure while an addon-authored body taints as it runs, as the client's tainted function closure does; a spec now pins that. (#343, #349)
- **With the gamepad interface on, the Forever addons settings page no longer makes the game refuse a controller action.** The page built its checkbox and Copy link rows in addon execution, so the row data Blizzard reads in its secure row build carried the addon's taint and tainted the gamepad binding stack as the page closed. Those builders now run through `CreateSecureDelegate`, as the client's own settings code does, or directly on a build without it. (cjber/tweaks-forever#446)

### For addon authors

- ForeverCore is now a required addon: declare `## Dependencies: ForeverCore` in the TOC and list it under `required-dependencies` in `.pkgmeta`. Do not vendor a runtime file any more.
- The public surface is `ForeverCore` with `API = 1`, its modules, and `ForeverCore.Register(addonName, spec)`. `Register` returns the addon's `SafeCall`, `RecordError`, `CaughtErrors`, `CutText`, `Log`, `LogLines`, `DebugEnabled`, `DebugCommand`, `Report`, `MapCanvas` and `Attach(db)`. The old `ns.AttachErrorJournal`, `ns.AttachLog`, `ForeverTrackerHost`, `ForeverFamily`, `ForeverLeaderboards`, `ForeverPeerStats`, `ForeverQuestLogTabs`, `ForeverErrorJournal`, `ForeverDebugLog`, `ForeverMinimapButtons` and `ForeverMapMarkers` globals are gone.
- `UI/SettingsPage.lua`'s `Register(name, build, L)` takes the caller's L. A tracker section offers its old settings with `module.legacySettings`.
- `Core/OpenMap.lua` adds `ns.OpenMap(mapID?)` and `Core/OpenSettings.lua` adds `ns.OpenSettingsPanel(categoryID?, element?)`. Each returns true when the client opened it, and false in combat, without `CreateSecureDelegate`, or when the client function is missing. Load each after `Core/SafeCall.lua`; the sync tool adds its TOC line and the globals luacheck reads. Call these instead of `C_Map.OpenWorldMap` and `C_SettingsUtil.OpenSettingsPanel`.

## [0.5.4] - 2026-11-10

- **Guild members keep their class on the Forever Leaderboards window.** `GetNumGuildMembers` returns the member count and the online count, and the second value reached `tonumber`'s base argument, so building the guild part raised "base out of range" and no guild row got a class colour or icon. (#587)

## [0.5.3] - 2026-11-10

- **Right-click a tracker section to hide it.** A section whose addon has its own show switch now offers **Hide this section** in its header menu, and the entry's tooltip says where to turn it back on. SkillUp's profession reagents or Shortest Path's journey steps can be removed without hunting through settings, and a section without a switch keeps the menu it has. Thanks to _spada for the report. (#292)

### For addon authors

- `ForeverTrackerHost.Attach(module, show)` takes an optional show setting: `get`, `set` and the `where` phrase naming the place the player turns it back on. The host adds **Hide this section** to that section's header menu and writes only the addon's own setting.


## [0.5.2] - 2026-11-09

- forever_sim: frames answer `GetHighestFrameLevel`, the highest level of a frame and its children (or every descendant with `true`), as the client does.

## [0.5.1] - 2026-11-09

- **`/reload` and `errors` reach the chat box when the Forever copy-link box has focus.** The Return and the typed command used to go into that box, so the world never reloaded and the verb timed out after 120 s. `slash` now sends Return, Escape, Return before typing: from a clean frame that opens, closes and reopens chat, and with a focused box the Escape closes its window first. (#266)
- **An optional Forever quest list in the tracker column.** Turn on "Forever quest list" in Forever Core's settings or type `/fcore quests`: your tracked quests then show at the top of the Forever column in the game's own tracker style, quests ready to turn in first, then the ones in this zone, then every other zone, each nearest first with its distance in yards from the game's quest data. Left-click super-tracks a quest, right-click opens the game's quest menu. The game's own quest and campaign lists are collapsed while it is on, and it stays off while Questie's tracker, Kaliel's Tracker or EQOT show the quests. (#177)
- **A hidden EQ Objective Tracker list is no longer read on every tick.** The tracker's EQOT watcher reports the list hiding or fading out once, then reads no geometry until it shows again; its show and hide hooks still reflow at once. (#268, cjber/skillup-forever#412)
- **Agents can test the addons in the real client without touching the player's desktop.** `tools/headless/forever_client.py` runs the WoW: Forever client under gamescope's headless backend on the GPU, waits until it is in the world, and gives screenshot, click, key, slash command, `/reload`, SavedVariables and Lua error verbs on that private display. One lock and a check of the Wine prefix keep it to one client, and it will not start while the player is in game. The tool keeps to the interface (slash commands only from the Forever addons, a fresh screenshot before each click, no free typing), spaces inputs out, caps a session at 30 minutes and logs the character out at every ending. The standard is `wow-forever-addon/in-game.md`.
- **Every Forever addon is exercised together.** `tools/suite_load.py` checks out each published addon's main and runs `sim:exercise()` with all of them and ForeverCore in one client, so a clash between two addons fails before a release; the Suite load workflow runs it daily and on demand. The simulator now boots the client's secure templates and its error frame (`UIErrorsFrame`), and answers the achievement natives from `sim.world.achievements`. (#203)
- **The leaderboards reach players you have not grouped with.** Each Forever addon now passes on the rows it has heard to its own guild and group, so a player's progress spreads through everyone who groups across guilds. A passed-on row keeps the player it came from and the time it was made, replaces only an older passed-on row, and never a row heard from the player directly. The window's menu adds "Players you've met" beside "Your guild and group"; values stay player-reported. Up to 400 such players are kept, the least recently active dropped first, and rows older than 30 days expire. (#170)
- **The leaderboards and quest log side tabs are real buttons.** They were frames carrying the side-tab template's mouse scripts, and with the gamepad interface on the client's navigation reads the mouse scripts of any focused frame that is not a button, inside its own protected call. The tabs are Buttons now, as the client builds its own side tabs, so that scan never reads a script a Forever addon created. `LEADERBOARDS_VERSION` is 3. (#253, cjber/skillup-forever#398)
- **The leaderboards' period menu works with a gamepad.** With the gamepad interface on, the menu beside the board no longer opens a game menu, which took the gamepad's focus under the addon's taint and later had the client refuse `SetPreferredGamepadInteractTarget()`. A press steps through the four choices instead: this week or all time, for your guild and group or for players you've met. `LEADERBOARDS_VERSION` is 6. (#267, cjber/skillup-forever#398)
- **The release gate reads the in-game selftest.** `tools/forever_errors.py` now reads the `!!DevSmoke` dev addon's `/forever selftest` runs from its SavedVariables, so a surface that failed to open or close counts as a live entry under `--since` like any journal or BugGrabber error. The publish skill gains the smoke step: link the build, `/reload`, `/forever selftest`, `/reload`, then the gate. (#207)
- **The simulator boots what an exercise reaches.** `forever_sim` now loads the client's alert frames at startup, so an addon that anchors to `AlertFrame` loads. A panel shown in combat gets the client's own refusal: `DisplayInterfaceActionBlockedMessage` prints "Interface action failed because of an AddOn" once, with no Lua error. `Enum.GameRule` carries the rules the Blizzard UI reads, so the world map opens at its own strata. A frame script now runs with its setter's taint only until it returns, as it does when the client calls it, so a secure caller after the script is no longer blamed on the addon that set it. (#203)
- **The simulator boots the quest frame, and a script's error stays inside its dispatch.** `forever_sim` now loads the client's `QuestFrame`, `QuestInfo` and quest session files, so closing the world map with the quest log panel shown runs `QuestFrame_HideQuestPortrait` instead of raising, and an error in a frame script is reported to the error handler while the code that triggered the script carries on, as it does in the client. (#259)
- **One shared step exercises an addon under the real Blizzard UI.** `forever_sim` adds `sim:exercise()`: it logs in, runs every slash command the addon registered (twice, so a toggle opens and closes), opens, zooms, pans and closes the world map, repeats that in combat, then `/reload`s into a fresh client with the saved variables and runs them again, failing on an error either client caused. `sim:slash`, `sim:slashCommands` and `sim:reload` are the steps it uses. An addon adopts it with a one-line `tests/sim/exercise_scenario.lua`, and ForeverCore exercises itself. (#203)

- **A new tracker setting no longer fails every consumer's typecheck.** The tracker contract's LuaLS classes (`ForeverTrackerSettings`, `ForeverTrackerHostAPI`, the lock, order and namespace fields) now live in `types/ForeverTracker.lua`, vendored with `UI/TrackerHost.lua` to the four tracker consumers, so each one stops keeping a hand copy that a sync could leave behind. `tools/sync_consumers.py` copies a `types/` file without waiting for a TOC line. (#247)

- **Field Guide and Commissions get the error journal.** The vendoring map sends `Core/SafeCall.lua`, `Core/Log.lua`, `UI/Report.lua` and their specs to all seven addons, so the drift checks cover Field Guide's and Commissions' copies once they adopt them (cjber/field-guide-forever#214, cjber/commissions-forever#103).

- **A bench script times 1,000 addon messages and 1,000 tooltip lookups through the leaderboards.** Speedpatrol runs it.
- **The Forever addons page opens with a gamepad.** With the gamepad interface on, `Family.Register` builds the page from the client's own settings rows, which the Options window's navigation can enter; the canvas page left the cursor on a hidden row. Each addon registers the page through it. `VERSION` is 7. (cjber/tweaks-forever#382)

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
