# Embedded ForeverCore

Every Forever addon carries ForeverCore inside its own zip, under `Libs/ForeverCore/`, and names `ForeverCore` in its
TOC's `## OptionalDeps`. The standalone ForeverCore stays an optional download that gets every release. This page is
the source for that layout: how the embed works, how the zip and store relation are packaged, and, as history, the
standalone-dependency bridge it replaced.

## How the embed works

Each consumer carries its own copy of core at `Libs/ForeverCore/`, so it runs whether or not the standalone folder is
installed ([#801](https://github.com/cjber/forever-core/issues/801)). Nothing is committed for it: a consumer opts in
with `## X-Forever-Core-Embed: 1` in its root TOC, and `python3 -m tools.forever_tools.embed` rewrites the disposable
checkout right before the packager, in the release workflow, the CI package job and `forever_client.py build-dev`.
`tools/check_consumers.py` fails an opted-in consumer whose workflow runs a packager with no embed step before it.

The step plans the copy with `tools/build_embedded_core.py` from a ForeverCore checkout at the consumer's pin (`--core`,
else `$FOREVER_CORE`), so every addon on one pin ships byte-equal copies and one digest. It wraps each Lua file the TOC
loads, directly or through an XML `Script`, as a deferred chunk on the file's first line, so error line numbers stay
the source's, and orders the TOC as the copy, `ForeverCoreHost.lua`, the addon's files, `ForeverCoreRun.lua` and
`ForeverCoreReady.lua`.

- With an older standalone folder installed (every standalone up to 1.15.4 shipped unwrapped and publishes its table at
  file load), the loader adopts it
  for the session, since a second runtime cannot start beside it, and the addon's files run inline during its own file
  load, exactly as before. When it is older than the newest embedded copy, the player sees an on-screen notice once per
  installed standalone version, naming both versions and saying to update or disable ForeverCore.
- Without it, the highest sealed embedded copy is elected at PLAYER_LOGIN, with no install prompt. The addon's files run then, and each frame they
  registered receives the addon's `ADDON_LOADED` and the `PLAYER_LOGIN` it missed.
- `ForeverCoreDB` carries over in both directions: the standalone mirrors its store into every offered consumer table,
  and an elected copy reads those mirrors, keeping a newer embedded change over a stale standalone table.
  `tests/generated_bundle_spec.lua` covers install, update and removal in either order.

## Packaging

The owner chose the accepted community method in [#787](https://github.com/cjber/forever-core/issues/787), the way
Ace3 and LibStub libraries ship:

- **Embedded only:** each addon's zip carries core only under `Libs/ForeverCore/`. Its `.pkgmeta` drops the top-level
  ForeverCore external and `move-folders` rule. No zip writes a shared `AddOns/ForeverCore/` folder any more, which
  ends [#448](https://github.com/cjber/forever-core/issues/448): removing or downgrading one addon can no longer delete
  or roll back core under the others.
- **Embedded relation:** `.pkgmeta` lists `forevercore` under `embedded-libraries`, not `required-dependencies`. The
  CurseForge app links core on the project page and never installs it as required.
- **Optional standalone:** the standalone ForeverCore project stays on CurseForge as an optional download that gets
  every core release, so the newest standalone available matches the newest embedded copy. A player who does not update
  an installed standalone can still run an older one, as described above.

The manager results in the bridge history below no longer block this. A manager that deletes the old shared folder
during an update leaves the updated addon running on its embedded copy. `tools/check_consumers.py` holds every consumer that opts in with
`## X-Forever-Core-Embed: 1` to this layout. A consumer that has not opted in keeps the bridge bundle (externals and
`move-folders`) until its embed release. `core_pin.embeds` is the one reader of that field: the last
`## X-Forever-Core-Embed:` line decides, and only the value `1` opts in, so every check agrees with the embed step.

The embed releases go out together. While any addon still ships the shared top-level `ForeverCore/` folder, removing
or downgrading that addon rolls core back under the others. Two holds enforce this:

- **At every release:** each opted-in addon's own `release.yml` runs `python3 -m tools.forever_tools.fleet` before its
  packager, and `tools/check_consumers.py` fails a release workflow without that step. It fails until every addon in
  `forever_tools.fleet.EMBED_FLEET` sets the field on its own `main`, so a hand-run release or a pushed tag holds too.
- **As one batch:** once all have opted in, `tools/release_consumers.py` dispatches none of the embed releases until
  every fleet addon is ready to release in the same run or already has an embedded release published.
The embed step also refuses a TOC whose `## SavedVariables` does not name exactly one account global: core mirrors
its account store into that one global, and a per-character global or a choice of several cannot hold it.

An already-released standalone (any 1.14.x and 1.15.x up to 1.15.4) that is enabled publishes its table while it loads.
Releases after 1.15.4 package the standalone wrapped (`build_embedded_core.py --standalone`), so it joins the election
as mode `standalone` instead, and `tools/check_release_archive.py` refuses a standalone zip without the
`X-Forever-Core-Loader` header. A consumer still guards any facade member newer than 1.15.3, the oldest standalone a
player may keep. The loader
adopts it for that session if it serves the embedded consumers, and otherwise fails naming its version. Each release
proof shows the addon working with no standalone installed and with an old standalone enabled. `forever_client.py
proof` compares the installed build with the checkout after the same embed step at the same pin, and records the
checkout's own digests, whose pin binds the embedded copy.

## Check the built consumer ZIP

The existing CI package job runs `python3 tools/check_package.py` after BigWigs builds the folders with
`args: -d -z`. It compares each installed ForeverCore copy with `tools/forever-core.txt`. An opted-in addon
must ship its embedded copy and cannot ship a top-level ForeverCore folder.

In the consumer's `release.yml`, keep the pin check and, where applicable, the embed and fleet steps before
BigWigs. In the same job, build the ZIP with `args: -d`, then validate it and upload that exact file:

```yaml
- name: Build the release ZIP
  uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812 # v2.7.0
  with:
    args: -d
- name: Check packaged ForeverCore
  id: validated
  env:
    GH_TOKEN: ${{ github.token }}
  run: python3 -m tools.forever_tools.core_archive --release-dir .release --latest
- name: Verify the release ZIP checksum
  env:
    ARCHIVE: ${{ steps.validated.outputs.archive }}
    ARCHIVE_SHA256: ${{ steps.validated.outputs.sha256 }}
  run: printf '%s  %s\n' "$ARCHIVE_SHA256" "$ARCHIVE" | sha256sum --check --status
- name: Upload the validated ZIP
  uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812 # v2.7.0
  with:
    args: -c -z
  env:
    archive: ${{ steps.validated.outputs.archive }}
    archive_name: ${{ steps.validated.outputs.archive_name }}
    archive_label: ${{ steps.target.outputs.tag }}-forever
    archive_version: ${{ steps.target.outputs.tag }}
    CF_API_KEY: ${{ secrets.CF_API_KEY }}
    GITHUB_OAUTH: ${{ github.token }}
```

Use the tag from the release job's target step. `tools/check_consumers.py` checks the build, validation, checksum
and upload order. The version comes from the shipped TOC for a bridge copy and the stamped bundle for an embedded
copy. The audit checks the player downloads on both stores after publication and updates one issue on failure.

[BigWigs packager v2.7.0](https://github.com/BigWigsMods/packager/blob/v2.7.0/release.sh)

## History: the standalone dependency bridge

The steps below were the plan before the owner chose embedding
([#787](https://github.com/cjber/forever-core/issues/787)). They are kept as the record of the manager evidence; none of
them is a current instruction.

At the time, every consumer already named `ForeverCore` in its TOC's `## OptionalDeps`. The bridge was to establish
independent manager ownership before removing the shared folder from consumer archives. It addresses
[#448](https://github.com/cjber/forever-core/issues/448): uninstalling the consumer that a manager considers the
folder's owner can delete core from underneath other addons. Adding metadata alone does not resolve that issue.

### 1. Declare the dependency and retain the fallback

The shared consumer sync adds `required-dependencies: - forevercore` to consumers that bundle core, preserving other
relations, the pinned GitHub ZIP external, `move-folders`, the TOC optional dependency and `X-Forever-Core` field.
Existing bundle-only consumers remain accepted during adoption. Consumer PRs need their normal checks and a published
release before the relation reaches users. No consumer bundle is removed in this phase.

Verify the published CurseForge file relation is `requiredDependency` for project 1796337, not `embeddedLibrary`.
BigWigs packager v2.7.0 automatically overrides relations for an external with a CurseForge slug. Our external is a
GitHub release ZIP without `curse-slug`, so retain that form and inspect the actual uploaded relation.

Sources: [CurseForge pkgmeta](https://support.curseforge.com/support/solutions/articles/9000197952-preparing-the-packagemeta-file),
[packager v2.7.0 source](https://github.com/BigWigsMods/packager/blob/v2.7.0/release.sh).

### 2. Prove manager ownership with a canary

Use disposable addon installations with saved variables backed up. Record manager version, provider, old and new
file IDs, archive hashes, actions taken, resulting folder ownership and the exact in-game smoke commit. Test each
supported path independently: CurseForge app, WowUp with CurseForge provider, wowaddon and
manual ZIP installation. Keep a channel bundled if it cannot establish standalone ownership automatically.

For each manager/provider, prove:

- Fresh install of one consumer installs standalone core without another manual selection.
- Ordinary update from a pre-transition release acquires standalone core without reinstalling the consumer.
- Direct update from that old release to the proposed unbundled release also works. A player can skip every bridge
  release, so a waiting period or download count cannot establish this gate.
- Two consumers at mixed release versions work through both update orders and a consumer downgrade. An old bundled
  consumer must not silently downgrade the standalone runtime below what the other needs.
- Uninstall either consumer, including the last one updated and the historical shared-folder owner. Core and the
  remaining consumer still work. Updating or repairing the remaining consumer also works.
- Disable and re-enable core, reload, restart and update standalone core while preserving saved variables.

Run the real headless client smoke against the resulting exact addon set. Archive and metadata checks supplement
that proof; they do not establish a manager's ownership behavior. Keep #448 open until its uninstall reproduction
passes. If a manager removes core despite the dependency relation, retain the fallback and fix or report that manager
path before continuing.

### Phase 2 results

The disposable-installation runs in [#650](https://github.com/cjber/forever-core/issues/650) cover CurseForge app
1.326.0-42377 and WowUp-CF 2.25.5 with the CurseForge provider. The bundled Macro Assist Forever and Field Guide Forever
archives contain ForeverCore v1.12.1. The unbundled canary is Macro Assist Forever v0.7.2-alpha.1, CurseForge file
9648139, with `RequiredDependency forevercore`.

Deleting either bundled consumer deletes `ForeverCore/` in both apps, regardless of the delete-dependencies setting.
A separate installed record for core does not protect its folder. This reproduces
[#448](https://github.com/cjber/forever-core/issues/448).

| Scenario | CurseForge app and WowUp-CF results |
| --- | --- |
| U1: update A to the alpha while B stays bundled | Updating A deletes the core folder in both apps. |
| U2: update A alone to the alpha | Core is deleted. Rescan, app restart and Update All do not restore it. |
| U6: restore the missing core | WowUp restores it by installing core or reinstalling A. CurseForge app restores it only with Reinstall on core's own row. |
| U3: fresh install of alpha A | Both apps install core as its own record and folder. |
| U4: delete alpha A, then bundled B | Core survives deletion of A. Deleting B removes core. |
| U5: delete alpha A alone | Core stays unless WowUp's remove-dependencies prompt is accepted or CurseForge's Delete orphaned libraries is enabled. |

Every tested update that drops the bundled folder deletes core once, and neither manager reinstalls it by itself.
Neither CurseForge app nor WowUp-CF passes the ordinary-update-acquires-standalone-core gate. Once no bundled consumer
remains, fresh install and uninstall behave according to the dependency settings. Keep the bundled fallback and #448
open. These results are partial evidence for #650, not completion of its lifecycle matrix.

The remaining checks are wowaddon, manual ZIP installation, two consumers at mixed versions in both update orders,
a consumer downgrade, and a headless client smoke for each resulting addon set. The WowUp Wago provider also needs
independent evidence before its channel can pass the gate.

#### Run the manager harness

`tools/manager_lifecycle/` contains the repeatable UI drivers and JSON/Markdown report builder. It needs Linux,
`dbus-run-session`, `xvfb-run`, extracted CurseForge and WowUp-CF application directories, and the Python dependencies
in `tools/uv.lock`. It opens isolated manager profiles under Xvfb and never starts the game client. Run only one copy
at a time, with no other process using its disposable folder or debugging ports 9301, 9302 and 9312.

Prepare a dedicated scratch folder and mark it as disposable:

```sh
export MANAGER_LIFECYCLE_ROOT="$HOME/.cache/agent-scratch/manager-lifecycle"
mkdir -p "$MANAGER_LIFECYCLE_ROOT"
keeper claim "$MANAGER_LIFECYCLE_ROOT"
touch "$MANAGER_LIFECYCLE_ROOT/.manager-lifecycle-disposable"
```

Place the extracted apps at `dl/wux/squashfs-root/wowup-cf` and `dl/cfx/squashfs-root/curseforge` beneath that root,
or set `MANAGER_LIFECYCLE_WOWUP_BIN` and `MANAGER_LIFECYCLE_CF_BIN` to their executable paths. Keep each executable
beside its extracted resources. Copy the installation metadata fixtures `.build.info`, `.product.db` and
`_forever_/.flavor.info` into `metadata/` beneath the root. These fixtures identify the disposable installation to the
managers; do not point the harness at a live client. The harness creates an empty `Wow.exe` placeholder.

From the repository root:

```sh
bash tools/manager_lifecycle/run-all.sh
bash tools/manager_lifecycle/run-updates.sh
# One scenario, with the same options accepted by the matrix scripts:
uv run --project tools --frozen --group dev python -m tools.manager_lifecycle.run --app wowup --scenario U2
```

Use `--a`, `--b`, `--a-name`, `--b-name` and `--channel` to choose consumers and release channels. The update matrix
selects the newest alpha offered by the manager, so verify its file ID in the report before comparing it with these
results. U1 and U2 include the U6 recovery steps. `--remove-deps yes` enables dependency removal; CurseForge also
accepts `--cf-libs-separate yes`.

Paths default beneath the scratch root: `fakewow/World of Warcraft` for the disposable client, `state/` for app
profiles, `logs/`, `archives/`, `reports/` and `metadata/`. Override them with `MANAGER_LIFECYCLE_CLIENT`,
`MANAGER_LIFECYCLE_STATE`, `MANAGER_LIFECYCLE_LOGS`, `MANAGER_LIFECYCLE_ARCHIVES`, `MANAGER_LIFECYCLE_REPORTS` and
`MANAGER_LIFECYCLE_METADATA`. Reset targets must remain beneath the marked scratch root and outside the repository.
Each run deletes and recreates the disposable client and the selected app's profile. Reports record manager version,
archive hashes, installed records, folder contents and screenshots after each action. App processes are stopped on
exit; a nonempty `processes_left` or a recorded action error makes the command fail. Keep those reports with the
issue evidence. Pure tests run as part of the tools unittest discovery without launching an app.

### 3. Remove bundles only on proven channels

Start with one consumer on one verified channel, then expand after its update and uninstall evidence passes.
The unbundled artifact keeps the TOC's `## OptionalDeps: ForeverCore` and store relation. Retire its external, move rule
and bundle-only version diagnostics together; update the checker, sync producer, release automation and publishing
skills in the same reviewed effort. Independent core releases then replace suite-wide rereleases for core-only changes,
with the WFA-39 gate (core's `released-consumers` check and `headless-smoke` on the released consumer zips) keeping
every consumer release on the stores working.

If providers need different archives, add explicit channel-specific packaging and tests before rollout. Keep a
self-contained fallback for channels that cannot resolve dependencies, including manual ZIP users, until a supported
automatic migration exists. Explain the installation behavior on each store page without asking existing users to
reinstall. Do not publish one globally unbundled ZIP on the assumption that every manager resolves dependencies.

### Rollback

Stop expansion at the first failing lifecycle check. Publish a higher patch version restoring the pinned bundle
on the affected channel, retain the required relation and preserve saved variables. Test rollback as an ordinary
update from the failed canary; do not overwrite releases or tags. If uninstall has already removed core, verify the
manager's repair or dependency installation path and communicate that precise recovery. Rollback availability does
not replace proving the migration first.
