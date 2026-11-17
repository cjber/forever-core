### Added

- **Simulator scenarios can read quest rewards and share quests, open the backpack and press override bindings.** The world map opens on a modelled map, edit boxes notify text changes on the next frame as the client does, and widget-method generation reads the annotation pin from `tools/toolchain.json`. (#632, #636, #643, #644, #668, #676)
- **Headless jobs can run in a private nested Hyprland for deskpilot**, with a bounded command and a return to gamescope before the slot is released. (#662)
- **A Forever addon's minimap button can register with LibDBIcon** so SexyMap and other minimap managers can show it on hover, move and hide it. The tooltip says it can be dragged. Thanks to Laddylucks, thirex, axejess, p1tu and Mirades96 for the reports. (#685)
- **Every Forever addon can check its translations against the game's fonts.** The glyph check ships to each addon with its own reviewed list of widgets and fonts. (#543)

### Changed

- **Headless jobs wait in arrival order**, with live queue positions and dead-waiter cleanup. Ended leases fail with their reason and cannot carry over to a replacement session. (#734, #719, #730)
- **Client commands require the shared in-game caller marker.** Jobs preserve it and the smoke queue sets its own marker. (#741)
- **Package diagnostics name the exclusion source**, distinguishing a matching `.pkgmeta` ignore rule from an untracked or Git-ignored runtime file. (#732)
- **Headless tooling refuses jobs and input while the character is dead, a ghost or in combat**, and stops when live safety cannot be confirmed. (#619)
- **Headless leases lock one command at a time**, exclusive jobs have a hard timeout, and a job can request session shutdown without waiting on its own lock. (#671)
- **Release tooling:** `changelog.py --check` fails on a bullet that appears twice in one section, an addon PR's package check no longer fails while a new ForeverCore awaits CurseForge moderation (the release workflow still requires the latest core), and a proof records a Lua flow as `sha256:<digest> <file>` so a file named with `api` or `key` no longer trips gitleaks. (#660, #661, #656)
- **A consumer whose `tools/typecheck.sh` does not run the client-call lint now fails the shared tooling check.** SkillUp vendored the lint without running it. (#539)
- **Native quest header clicks have a simulator regression** using the real tracker and chat utility; the quest-list scenario no longer replaces ChatFrameUtil. (#630)

### Fixed

- **The mouse wheel scrolls a tracker section over its text.** A quest taller than its space now scrolls a page at a time with overlap, so every objective stays reachable even in a short column. Stacked sections keep a readable row when space allows and show only their header otherwise. (#616, #615)
- **Headless proofs check their candidate links at capture and teardown**, and link recovery runs only under the exclusive job lock. Recovery specs use isolated client folders. (#723, #724)
- **Headless sessions restart when their helper addon changes**, and smoke, proof and dev builds fetch origin once for a missing full commit SHA. (#715, #692)
- **Headless startup stops when Battle.net needs the player to sign in.** Queued starts stay blocked until a manual launcher session reaches READY, and smoke posts nothing while blocked. (#731)
- **Headless sessions check live world state before reuse** and replace sessions that reached the login screen. (#705)
- **Headless slash input requires confirmed chat focus**, and clicks refuse the Game Menu. (#703)
- **Headless state writes survive reboot**, with automatic recovery of stale addon links and store backups. (#688)
- **Slash proof flows wait for their exact command to register** and fail with its name if it never becomes available. (#684)
- **The glyph check reads every English locale shape the addons use**: `ns.L["key"]` assignments and the fields of an `ns.L = { ... }` table, as well as `L["key"]`. A key whose value is client text, not a string literal, gets no English entry. (#543)
- **The glyph check accepts reviewed XML font producers with no bindings.** Their source digests still require review when a template changes, and Lua string literals are read only for phrase keys absent from enUS entries. (#543)
- **The glyph check covers the quest tracker's fonts** and reads an addon's English phrases from its code when its English locale file lists none. (#543)
- **Headless startup stops when Battle.net needs a game update.** It reports the launcher frame instead of clicking Play until the timeout, and stops after two Play clicks that start no game. (#316)
- **The simulator keeps native load-on-demand template initialization secure** while preserving the caller and addon template ownership. (#640)
