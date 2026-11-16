# Standalone ForeverCore dependency

Every consumer already names `ForeverCore` in its TOC's `## OptionalDeps`. The release transition establishes independent
manager ownership before removing the shared folder from consumer archives. It addresses
[#448](https://github.com/cjber/forever-core/issues/448): uninstalling the consumer that a manager considers the
folder's owner can delete core from underneath other addons. Adding metadata alone does not resolve that issue.

## 1. Declare the dependency and retain the fallback

The shared consumer sync adds `required-dependencies: - forevercore` to consumers that bundle core, preserving other
relations, the pinned GitHub ZIP external, `move-folders`, the TOC optional dependency and `X-Forever-Core` field.
Existing bundle-only consumers remain accepted during adoption. Consumer PRs need their normal checks and a published
release before the relation reaches users. No consumer bundle is removed in this phase.

Verify the published CurseForge file relation is `requiredDependency` for project 1796337, not `embeddedLibrary`.
BigWigs packager v2.7.0 automatically overrides relations for an external with a CurseForge slug. Our external is a
GitHub release ZIP without `curse-slug`, so retain that form and inspect the actual uploaded relation.

Sources: [CurseForge pkgmeta](https://support.curseforge.com/support/solutions/articles/9000197952-preparing-the-packagemeta-file),
[packager v2.7.0 source](https://github.com/BigWigsMods/packager/blob/v2.7.0/release.sh),
[Wago upload metadata](https://docs.wago.io/#prepare-the-metadata).
Wago documents no dependency field in its upload metadata. Do not claim automatic installation there without
independent verification of its manager and project settings.

## 2. Prove manager ownership with a canary

Use disposable addon installations with saved variables backed up. Record manager version, provider, old and new
file IDs, archive hashes, actions taken, resulting folder ownership and the exact in-game smoke commit. Test each
supported path independently: CurseForge app, WowUp with CurseForge provider, WowUp with Wago provider, wowaddon and
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

## 3. Remove bundles only on proven channels

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

## Rollback

Stop expansion at the first failing lifecycle check. Publish a higher patch version restoring the pinned bundle
on the affected channel, retain the required relation and preserve saved variables. Test rollback as an ordinary
update from the failed canary; do not overwrite releases or tags. If uninstall has already removed core, verify the
manager's repair or dependency installation path and communicate that precise recovery. Rollback availability does
not replace proving the migration first.
