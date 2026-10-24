# W7: Hoard Forever - "where is it?" across every container you can see

New addon. Repo `cjber/hoard-forever` does **not** exist yet and `gh repo create` returns 403 for the workspace
GitHub App (that is how `forever-core` is still unpublished). So:

- Stage the whole tree at `staging/hoard-forever/` on `cjber/skills`, branch `hoard-forever-staging`, following
  the layout in `../new-forever-addon.md` (also a Nebula skill: read it).
- Do **not** create, push to or force anything at `cjber/hoard-forever`. Report the staging path and the exact
  publish commands (create repo, add remote, push `main`, tag `v0.1.0`) so the coordinator can publish in one
  step once the owner has a repo.
- The tree must be complete and green **as if** published: `.toc`, `Core.lua`, `API.lua`, `Model.lua`,
  `Settings.lua`, `Locales/`, `Data/`, `UI/`, `tests/`, `tools/`, `types/`, `media/`, `docs/screenshots/`,
  `README.md`, `CHANGELOG.md`, `AGENTS.md`, `LICENSE`, `.pkgmeta`, `.luacheckrc`, `stylua.toml`, `.styluaignore`,
  `.luarc.json`, `ruff.toml`, `.gitattributes`, `.gitignore`, `.gitleaks.toml`, `.github/workflows/ci.yml`,
  `.github/workflows/release.yml`, `.github/dependabot.yml`, all copied verbatim from a sibling and renamed.

## Why, and what it is not

The owner wants a bank/alt inventory companion. SkillUp already reads **reagents** from other characters through
Syndicator (`skillup-forever/UI/Shopping.lua`, `ns.AltCounts`) and Tweaks owns bag UI fixes and vendor selling, so
a second reagent counter or a bag-feature grab-bag would duplicate both. What nothing owns is the **arbitrary
item question**: "where is my Arcanite Bar - which bag, which bank, which alt, which mailbox?" That is the scope.

## Scope for v0.1.0

An index over every container the client lets an addon read, and a search over it.

Containers, in this order of confidence:

1. backpacks and bags - `C_Container.GetContainerNumSlots` / `GetContainerItemInfo`, cached per bag and
   invalidated on `BAG_UPDATE` / `BAG_UPDATE_DELAYED`;
2. bank and bank bags - only after the bank has been opened (`BANKFRAME_OPENED`); the snapshot is saved per
   character with the time it was taken, and the UI says "as of <date>" rather than pretending it is live;
3. warband / account bank **only if** the pinned client types expose it - check `.types/` from a sibling before
   writing a line of code for it;
4. guild bank - only while the frame is open, same last-seen rule;
5. mail attachments - only while the mailbox is open (`MAIL_SHOW`), from `GetInboxItem`;
6. other characters - through Syndicator's public API when it is installed (`Syndicator.API`,
   `GetInventoryInfoByItemID`, `IsReady`), exactly as SkillUp does it, but for any item, not just reagents.

Public API (`HoardForever.API`, `version = 1`, `minor = 1` - and annotate it in `types/API.lua` the way
`shortest-path-forever/types/API.lua` documents its own):

```lua
API.Ready() -> boolean
API.Count(itemID) -> number                     -- everything currently readable plus saved snapshots
API.Where(itemID) -> { container, character?, count, slot?, map?, takenAt? }[]
API.Search(text, limit?) -> { itemID, name, count, link?, where }[]
API.Snapshot(character?) -> { takenAt, containers }[]?   -- what the saved index holds
```

UI: one window (`UI/Window.lua` + `UI/List.lua`), a search box, results with the item link, the total count and
where each stack is, grouped by container and character; a `/hoard <text>` and `/hoard <itemlink>` slash command
that opens it pre-filtered. Native client look - read `../wow-retail-ui-style.md` and match a sibling window
(`bestiary-forever/UI/Window.lua` is the cleanest small one). **No Blizzard tooltip additions** - tooltips belong
to Tweaks; the addon draws its own window and its own tooltip lines only.

Data honesty: only report what the client exposes. Secret/unreadable values (the client hands some counts over
as secret) must read as "unknown", never as 0 - copy the `ns.Readable` / last-seen-count pattern from
`skillup-forever/UI/Shopping.lua`. Never sum a snapshot into "you have N" without labelling it a snapshot.

SavedVariables `HoardForeverDB`: flat, serialisable, per-character snapshots keyed by character+realm, an
option set, and nothing else. No item links, frames, functions or userdata persisted; links are rebuilt from the
item ID.

Options: search across characters (default on, needs Syndicator), include saved bank/mail snapshots (default on),
window scale, and reset snapshots.

## Tests and gate

- `tests/model_spec.lua`: the index model (add/remove/move a stack, snapshot merge and expiry, total counts,
  unknown-vs-zero), `tests/search_spec.lua` (substring and exact matching, item link input, limit, ordering by
  total then name), `tests/api_spec.lua` (version, ready gating, copies not internals).
- The repo has no CI history, so copy `ci.yml` from a sibling exactly and make it pass locally for real:
  `luacheck .`, `stylua --check .`, every `tests/*_spec.lua` with `luajit`, `ruff check tools`,
  `python3 tools/check_generated.py` if you ship generated `Data/`, `python3 tools/changelog.py --check`,
  `python3 tools/check_screenshots.py`.
- Screenshots: mocked scenes for the window (empty, results, snapshot labels) rendered through the sibling
  `tools/wowmock` approach, in `docs/screenshots/`, referenced from the README - and looked at by eye.

## Out of scope for v0.1.0

Craft-from-horde, mailing items between characters, auction house integration, Tooltip lines, bag sorting. Note
them in the README's roadmap section instead of half-building them.

## Report

Staging path, the full gate output, the mocked screenshots you rendered (paths), the publish commands, and any
client capability you could not verify (say which and how the honest fallback behaves). No repo creation.
