# Handoff: finish the extraction

Everything here is built and green; what is left is publishing it and pointing the four consumers at it. Repo creation
is the one step that needs an account-level permission the workspace GitHub app does not have (POST /user/repos
returns 403 "Resource not accessible by integration"), so the source is staged on cjber/skills branch
`forever-core-staging` under `forever-core/`.

## 1. Publish the repo

```sh
# Once cjber/forever-core exists (empty, no README):
git clone https://github.com/cjber/forever-core /tmp/forever-core
git clone --branch forever-core-staging https://github.com/cjber/skills /tmp/skills
cp -a /tmp/skills/forever-core/. /tmp/forever-core/          # the staged tree, .git excluded
cd /tmp/forever-core
git -c user.email=cjberragan@gmail.com -c user.name="Cillian Berragan" add -A
git -c user.email=cjberragan@gmail.com -c user.name="Cillian Berragan" \
  commit -S -m "feat(core): ForeverCore, the shared tracker column the suite docks into"
git push origin main
```

Then wait for `ci.yml` to pass on main, and release 0.1.0:

```sh
git tag -a v0.1.0 -m v0.1.0 && git push origin v0.1.0
```

`release.yml` publishes the GitHub release with the packager. There is no CurseForge or Wago page for a library addon,
so no store token or store verification is involved.

## 2. Point each consumer at the core as the authority

The four consumers already hold byte-identical copies, so no shipped code changes and no addon release is needed.
Only the drift check moves from four-way to core-authoritative.

For each of `adventure-guide-forever`, `legacy-forever`, `shortest-path-forever`, `skillup-forever`:

1. Replace `tools/check_shared_tracker.py` with a copy of forever-core's `tools/check_consumers.py` reduced to one
   repo: it compares that repo's own copies against `https://raw.githubusercontent.com/cjber/forever-core/main/<path>`
   and fails on any byte difference. Keep the same `VENDORED` list.
2. In `.github/workflows/shared-tracker.yml`, keep the job, change the comment to name forever-core as the source.
3. Nothing else changes: the TOC load order, the `ForeverTrackerHost` global, `ns.TrackerHostSettings` and every spec
   stay exactly as they are.

Do this as one PR per repo, and let each repo's own CI (luacheck, stylua, the specs, the package check) be the gate.

## 3. What is deliberately not done

- **No `.pkgmeta` external.** Vendored copies keep every addon standalone with nothing to install, which is the rule
  in the boundaries doc, section 5.
- **No consumer version bump for this.** The shipped bytes do not change, so a release would only add noise. Consumer
  releases happen when a real core fix lands (`tools/sync_consumers.py`, then one PR per repo).
- **No second tracker column.** Core lists the five addons as `OptionalDeps` so they load first and core adopts the
  published host. Do not remove those OptionalDeps.

## 4. Acceptance

- ci.yml green on forever-core main, and v0.1.0 released.
- `python3 tools/check_consumers.py` in forever-core prints "7 shared files match in all 4 consumer repos".
- Every consumer's own CI green, with its drift check now naming forever-core as the source.
- The boundaries doc (cjber/skills, `forever-handoff/boundaries.md`, section 5) is still true after the change: if the
  vendoring model changed, the doc changes in the same PR.
