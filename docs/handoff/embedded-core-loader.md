# Embedded ForeverCore loader, schema 1

**Status:** first contract slice implemented on `cb/embedded-core-448`, off `2e2f53c`. Consumers are unchanged, no
release has shipped and the runtime modules are not wrapped yet. This is groundwork: the loader is TOC-loaded in the
standalone addon, but no copy registers a candidate there, so embedded ForeverCore does **not** work yet and no
acceptance is claimed.
**Lives at:** cjber/forever-core, `Core/Loader.lua` and `tests/embedded_loader_spec.lua`.
**Read it before:** wrapping core files for a consumer, changing loader schema 1, or adding saved-variable election.

## What this slice implements

`Core/Loader.lua` is the one registry every embedded ForeverCore copy shares. It is loaded first in
`ForeverCore.toc`, before `Core.lua`, and a consumer ships it as a plain file before `Begin.lua`, never wrapped. The
global is `ForeverCoreLoader`, and `ForeverCoreLoader.schema` is `1`.

A consumer release will generate this shape:

```lua
-- Begin.lua, after the unwrapped Core/Loader.lua
local addonName, ns = ...
local copy = ForeverCoreLoader.Begin(addonName, BUILD, DIGEST)
ns.ForeverCoreCopy = copy
```

```lua
-- each wrapped core file, in today's TOC order; the body stays byte for byte unchanged
select(2, ...).ForeverCoreCopy:Define(function(...)
	-- the file's body: local _, ns = ... / local coreName, ns = ... see ("ForeverCore", ns)
end)
```

```lua
-- End.lua
select(2, ...).ForeverCoreCopy:Seal()
```

The contract:

- `Begin(folder, build, digest)` registers one copy and creates the one `PLAYER_LOGIN` frame. It runs no runtime code.
  `build` is `major * 1000000 + minor * 1000 + patch`; a value outside that shape is rejected. `digest` is the
  packager's content digest as a non-empty string. It is required by the final packaging contract; while this
  groundwork still allows it to be absent, a missing digest is **not** evidence that two copies have equal bytes.
- `copy:Define(chunk)` appends one chunk, in TOC order. It has no side effects. A copy created by an invalid or late
  `Begin` accepts definitions but never runs them. Boot calls each chunk with the fixed identity `"ForeverCore"` and
  the namespace: `chunk("ForeverCore", namespace)`, so a converted file's `local coreName, ns = ...` and
  `select(1, ...)` are core's own identity, never the consumer's folder.
- `copy:Seal()` marks a complete package. An unsealed or empty copy is never elected, so a truncated package is
  detected exactly. A second `Seal` is rejected.
- The winner's namespace carries `folder`, `root`, `copy` and `mode` (`"standalone"` or `"elected"`) before the first
  chunk runs. Converted files define `namespace.Start`; Boot calls it after the chunks and **before** publishing the
  facade, so a failed Start leaves no facade. They also define `namespace.Login`; the loader calls it exactly once
  after activation on the `PLAYER_LOGIN` event, never in legacy mode and never after a failed boot.
- `ForeverCoreLoader.OnReady(fn)` queues `fn(core, selected)` until activation, or runs it at once after activation.
  Callbacks run in registration order. A callback that registers another `OnReady` queues it behind the callbacks
  already waiting. A callback that fails goes through the client's `geterrorhandler()` (BugSack and the script-error
  display) and is recorded in `CallbackError()` without stopping the next callback; a boot failure stays in `Error()`.
- `ForeverCoreLoader.Selected()` returns
  `{ mode = "elected"|"standalone"|"legacy", build?, folder?, root?, core? }`, or nil before activation and after a
  failed activation.
- `ForeverCoreLoader.Activate()` is the one activation, run by the `PLAYER_LOGIN` handler or by the standalone
  copy's own `ADDON_LOADED` handler. It is idempotent and stops listening for `ADDON_LOADED` once it has run.
- `ForeverCoreLoader.OfferStore(folder, globalName)` is the saved-variable seam, present from schema 1 so a later
  release can change storage without another protocol change. It validates only a non-empty folder and a non-empty
  account SavedVariables global name string; it never captures the table, accepts a getter, resolves the name or
  applies migration policy. A registration before SavedVariables arrive is valid, and a later replacement of that
  global is seen by name at reconciliation. Offers stay open until `PLAYER_LOGIN`, because a standalone copy activates
  at its own `ADDON_LOADED` before consumers offer.
- `ForeverCoreLoader.Offers()` returns `{ folder, globalName }` entries in offer order. The runtime resolves each
  name with `rawget(_G, globalName)` when it reconciles. Revision, merge, conflict and write policy belong to the
  replaceable elected runtime (`Core/Store.lua`), not to this frozen loader. Nothing here inspects or writes a store.
- Diagnostics: `Error()`, `CallbackError()`, `LoginError()`, `Rejections()`, `Offers()`, `Namespace()` and
  `Facade()`. `LoginError()` is the runtime's login failure, separate from a boot or consumer-callback error.

### Runtime conversion contract (converted chunks)

A file is converted when its namespace carries `ns.copy`, which the loader injects. Converted files read the one
authoritative settings table through `ns.Store()`, which returns `ns.store`; `Core.lua` is the only owner of that seam
and of the global `ForeverCoreDB`.

- `Core.lua` defines `ns.Start()`. An elected copy requires a supplied `ns.store` table and refuses to start when it
  is absent, rather than inventing one or reading the global. The converted standalone adopts `ForeverCoreDB` in
  `Start`, at its own `ADDON_LOADED`, after SavedVariables have loaded; a pre-start read returns defaults and caches
  no placeholder. `Start` normalizes the tracker settings, attaches core's journal and log, then runs the tracker
  migration, in that order.
- `Core.lua` defines `ns.Login()` as a lifecycle no-op for this slice. The loader still calls it exactly once after
  activation; store reconciliation will replace the body later.
- `Expose.lua` assigns `ns.ForeverCore` only for a converted copy, so Boot is the sole global publisher. The unwrapped
  standalone keeps its old global publication and `ADDON_LOADED` handler until packaging conversion; that path is
  transitional, not the embedded contract.
- `UI/TrackerHost.lua`, `UI/TrackerQuests.lua` and `UI/Leaderboards.lua` read and write `ns.Store()`, never the
  global. Isolated specs supply their own `ns.Store()` fixture.
- No store election, merge, preference or write policy exists yet. `OfferStore`/`Offers` carries only the explicit
  account SavedVariables global name; resolving that name and reconciling its table is the replaceable runtime's job.

### Activation modes

1. **legacy** — a `ForeverCore` table whose `loaderSchema` is not `1` is adopted unchanged. It is activated at the
   first `Begin`, so a consumer's `OnReady` runs inside its own file load, where 1.8's `Register` and
   `TrackerSection` use already works. No embedded copy runs beside it. This is the only safe treatment of a 1.8
   runtime: its `seterrorhandler`, `hooksecurefunc`, frame names and saved-variable key cannot be undone, so there is
   no automatic neutralisation. A legacy table that appears only later, with no `OptionalDeps` load, is still adopted
   at `PLAYER_LOGIN`.
2. **standalone** — a copy whose folder is `ForeverCore` seals at its `End.lua` and activates at its own
   `ADDON_LOADED`, after its SavedVariables and before a dependent consumer's files load. Its root is
   `Interface\AddOns\ForeverCore`, the top-level addon layout its TOC and media use. It suspends newest-wins for the
   session; an embedded copy loading afterwards is late and only registers. This eager selection is **transitional
   groundwork**, not the final embedded contract: it exists so unmigrated consumers keep finding `ForeverCore` at
   their file load. Final embedding removes eager selection once every active consumer has migrated.
3. **elected** — with no legacy table and no standalone copy, the highest sealed `build` wins at `PLAYER_LOGIN`.
   Two copies at that highest build with different `digest` values are a real conflict: the loader records
   `tie-conflict` for **every** candidate at that build (including two that share one digest) and boots nothing
   rather than choosing by folder name or load order. The same build and digest is one package, so the first
   registration is stable. The final packaging contract requires the digest; in this groundwork two copies that both
   lack one are not authenticated as equal bytes, they only have nothing to compare. Only the winner's chunks run,
   into one fresh namespace with `folder`, `root`, `mode` and the copy handle. Its facade is published as
   `ForeverCore` once, and Boot publishes only when no other table is already there. Converted files must assign
   `ns.ForeverCore`. Today's `Expose.lua` still writes the global inside its own chunk, so the real conversion has to
   move that assignment onto the namespace first: until then a chunk error after that line leaves the facade
   published, and the loader cannot undo it (F4).

`folder`, the media root and the digest are per copy: an embedded copy is `Interface\AddOns\<folder>\Libs\ForeverCore`
and the standalone is `Interface\AddOns\ForeverCore`. Losers are never run and their namespaces are never created. A
duplicate folder, a late `Begin`, an invalid build or digest, an empty seal and a chunk that is not a function are
rejected deterministically and recorded in `Rejections()`.

A failed winner is terminal. Its chunks may already have installed hooks, so the loader records the error, publishes
nothing of its own and never retries or starts a lower copy over it. A failed `namespace.Start` is the same terminal
boot failure. A `namespace.Login` failure is terminal for the session too: the booted facade stays published and the
failure is recorded in `LoginError()` and reported to the client handler, but the loader never falls back to another
runtime after hooks exist. Until `Expose.lua` is converted to the namespace, a failing real Expose chunk may already
have set the global (F4); the synthetic spec chunks do not.

## What is deliberately not implemented

- No saved-variable write, merge, revision increment or migration. The loader retains only `{ folder, globalName }`
  offers; revision, version-vector, conflict and write policy belongs to the replaceable elected runtime
  (`Core/Store.lua`), not to frozen schema 1. The runtime is the only reader of the global by name. When that
  reconciliation lands it must preserve the live `errors` and `log.lines` table identities that the error journal and
  log already hold. Only active consumers participate in that later design; the archived `work-orders-forever`
  checkout stays read-only and is not migrated.
- No automatic neutralisation of legacy 1.8 hooks. A participant release is required before consumer migration.
- No consumer repository, `.pkgmeta`, TOC, vendor or store change.
- No runtime module wrapping. The source files now support converted chunks and the one `ns.Store()`/`ns.Start()`
  contract, but `ForeverCore.toc` still loads them unwrapped for the transitional standalone path.

## Integration needs before wrapping all runtime modules

1. **Wrapper generation.** Each consumer release needs `Begin.lua`, the wrapped core files in today's order, the XML
   file and `End.lua` under `<Addon>/Libs/ForeverCore/`. `Core/Loader.lua` runs unwrapped, before `Begin.lua`: it is a
   plain file that defines the `ForeverCoreLoader` global, never a `Define(function(ns) ... end)` body, because
   `Begin.lua` calls `ForeverCoreLoader.Begin`. The consumer's TOC keeps `## OptionalDeps: ForeverCore`, drops
   `## Dependencies: ForeverCore` and drops the top-level bundled folder.
2. **Chunk conversion.** Every runtime file must become one `Define(function(...) ... end)` body that leaves the
   existing body byte for byte. Boot passes `("ForeverCore", namespace)`, so `local _, ns = ...`,
   `local coreName, ns = ...` and `select(1, ...)` keep core's fixed identity instead of the consumer's folder. The
   converted set must define `namespace.Start` and `namespace.Login`. That includes `Core.lua`'s `ADDON_LOADED`
   work, `Core/SafeCall.lua`'s one error handler and login attachment, `UI/TrackerHost.lua`'s hooks and named frame,
   the settings categories, slash commands and the PeerStats prefix. Nothing may run at file load.
3. **Consumer call sites.** Every consumer's `ForeverCore.Register`, `APIKit` capture, `TrackerSection.Create`,
   `Family.Register`, `MinimapButton.Create` and `Require` gate moves into `OnReady`. A consumer's own
   `ADDON_LOADED` stores its DB and offers it; it does not touch Core.
4. **Saved variables.** Each consumer keeps its own account DB and calls
   `OfferStore(folder, "<AccountSavedVariablesGlobal>")`. `Offers()` hands the runtime the folder/name pairs; the
   runtime resolves the current global with `rawget(_G, name)` at reconciliation and owns writing. The loader itself
   neither looks a name up nor chooses a winner, and the later merge must preserve the `errors`/`log.lines` table
   identities and cover only the active consumer set.
5. **Legacy adoption and staging.** Ship a standalone participant that keeps today's eager consumer path working,
   prove it on the client, then release consumers with embedded copies, then make the standalone non-eager. The eager
   path now in the loader is transitional and is removed in that last step. Do not run an embedded copy beside an
   installed 1.8 table.
6. **Freeze schema 1.** A schema change uses `ForeverCoreLoader2`, never an in-place upgrade. An older copy must not
   call a newer loader's methods or the reverse.
7. **Diagnostics.** The existing `/fcore` tracker-debug fallthrough and a consumer-startup failure can stop an
   addon's own report registration (core#509). Keep that fix in the integration plan; it is not part of this slice.

## Client proofs still missing

- Whether a frame created during an addon's file load receives `PLAYER_LOGIN` on Interface 16001. The loader avoids
  depending on a redispatch, but the election itself depends on that event.
- Whether the standalone copy's own `ADDON_LOADED` arrives after its SavedVariables and before a dependent consumer's
  files load on this client, as the load order assumes. The loader waits for that event; the wrapped `Core.lua` must
  still defer any DB read that must not happen twice.
- Whether `## OptionalDeps: ForeverCore` loads an installed legacy copy before the consumer on this client, and what
  happens when it is missing.
- What the client does with the same virtual XML template name defined by several embedded copies.
- Whether WowUp and the CurseForge app remove the old top-level `ForeverCore/` when a consumer update no longer ships
  it.
- The memory and load cost of N parsed but unchosen copies, measured on the headless client.
- A load-on-demand Forever addon that first loads after `PLAYER_LOGIN`: the loader has no post-login election rule
  yet, so that copy would register and never activate. This needs an explicit rule before any consumer is LoD.

## Test evidence

`tests/embedded_loader_spec.lua` is focused and client-free. It was red before `Core/Loader.lua` existed (the spec
failed to load it) and now passes 330 checks:

- all six registration orders of builds for minors 5, 7 and 6 elect minor 7;
- upgrade and uninstall sessions remove the winner and elect the surviving newest copy;
- one `PLAYER_LOGIN` frame, one boot, an idempotent `Activate`, and one stable facade;
- duplicate, empty, invalid-build, invalid-digest, late and unsealed copies never run or replace the runtime;
- same-build conflicts with differing digests are `tie-conflict`: every candidate at that build is diagnosed
  (including a repeated digest in `A,A,B` and both registration orders), no copy boots and no facade is published,
  while the same build and digest keeps a stable first registration;
- legacy is activated at the first `Begin`, adopted by identity and never run beside, with no namespace Login; a
  legacy table that appears later is still adopted at `PLAYER_LOGIN`;
- standalone Seal waits for its own `ADDON_LOADED`, ignores another addon's event, activates once with the top-level
  `Interface\AddOns\ForeverCore` root, stops listening for `ADDON_LOADED`, keeps `PLAYER_LOGIN`, and blocks a newer
  embedded copy; its store offers stay open until `PLAYER_LOGIN` (transitional eager path);
- a failed winner records its error, publishes no facade and is not retried;
- the runtime contract: every wrapped chunk gets the fixed identity `"ForeverCore"` and the namespace, `mode` is set
  before the first chunk, `Start` runs once before publication, `Login` runs exactly once at `PLAYER_LOGIN` (and only
  then, not in legacy and not after a failed boot);
- a missing or failing `Start` is a terminal boot failure; a `Login` failure reaches `geterrorhandler()`, is kept in
  `LoginError()` even when the handler returns nothing, leaves the boot `Error()` empty and never falls back to
  another copy;
- `OnReady` runs in order, queues a callback registered from inside a callback behind the ones already waiting, sends
  a callback failure to `geterrorhandler()`, records it in `CallbackError()` (the original message survives a handler
  that returns nothing) and leaves the boot `Error()` empty;
- `OfferStore` retains non-empty `{ folder, globalName }` offers only: it rejects wrong folder/name types, an empty
  name, a duplicate folder and a post-login offer, never resolves or indexes the named global, accepts a name before
  SavedVariables exist, and keeps the registered name across a later global replacement; `Offers()` returns those names
  with no captured table or write.

Focused companions also pass: `tests/converted_runtime_spec.lua` (30 checks), `tests/toc_reader_spec.lua`,
`tests/core_spec.lua`, `tests/api_spec.lua`, `tests/expose_subset_spec.lua`, `tests/api_kit_spec.lua`,
`tests/tracker_adopt_spec.lua`, `tests/leaderboards_window_spec.lua` and the tracker host/section specs. No full local
suite or gate was run, and no game, Wine or store run was made.

`tests/converted_runtime_spec.lua` loads the real TOC sources as converted chunks with a supplied elected store and
asserts: `Expose.lua` leaves `_G.ForeverCore` nil and publishes only `ns.ForeverCore`; `Start` normalizes, attaches the
real journal/log and migrates in order while keeping the supplied history table identities; `_G.ForeverCoreDB` stays
nil; an elected `Start` without a supplied store is refused; the converted standalone adopts an injected
`ForeverCoreDB` after a pre-start default read; and `TrackerQuests` writes the namespace store. The same spec fails
against the pre-change `Core.lua`/`Expose.lua` (Expose publishes the global first).
