---
name: wow-addon-publish
description: "Use in a WoW addon repo (a .toc at the root; cjber's WoW: Forever addons such as tweaks-forever, skillup-forever, legacy-forever, shortest-path-forever) to publish it on CurseForge and Wago, create the store project, set its description/logo/gallery (CurseForge; Wago gets a stub), or cut a release that uploads to both. Not for non-WoW repos."
---

# Publish a WoW addon to CurseForge and Wago

The pipeline is: a store project on each site → its ID in the TOC → a signed `v*` tag → the BigWigs
packager uploads to GitHub, CurseForge and Wago. Project creation is the only manual part; do it once,
in the user's already-logged-in Chrome, through each site's own web form.

Never enter passwords, API keys or tokens into a page, never log in for the user, never print a secret.
If a token is missing, ask the user to run, in their own terminal (not `!`: it has no TTY, so gh's hidden
prompt reads empty stdin and stores an empty secret), `gh secret set <NAME> -R <owner>/<repo>`, or
`--body "$VAR"` when the key is in a variable. The names are exactly `CF_API_KEY` and `WAGO_API_TOKEN`
(Wago's UI calls it an "API key"; `WAGO_API_KEY` is ignored). An empty secret shows as a blank rather than
`***` in the release log.

## 1. Repo prerequisites

- `.github/workflows/release.yml` on `push: tags: ["v*"]` running `BigWigsMods/packager` (pinned by SHA)
  with `CF_API_KEY`, `WAGO_API_TOKEN` and `GITHUB_OAUTH: ${{ secrets.GITHUB_TOKEN }}`, and
  `permissions: contents: write`. Copy it from `cjber/skillup-forever` rather than writing one.
- Release notes = this version's CHANGELOG entry only (`tools/changelog.py <tag>`, also in skillup-forever),
  prose style, `## [x.y.z] - YYYY-MM-DD` headings. API changes go under an optional `### For addon authors`
  subsection after the player bullets; the notes carry it to GitHub, CurseForge and Wago as written.
- A `package` CI job builds with the packager's `-d -z` and runs `tools/check_package.py`
  (`wow-forever-addon` WFA-15), so `.pkgmeta` drift fails before a tag, not after an upload.
- `docs/curseforge.md`: the store description, pitched and worded per `wow-forever-addon` WFA-23/24
  (`voice.md`); run its `check_copy.py docs/curseforge.md README.md` before every paste (Markdown; screenshots referenced by
  `raw.githubusercontent.com/<owner>/<repo>/main/docs/screenshots/*.png`). Make screenshots with the
  `wow-mock-screenshots` skill.
- Check secrets exist: `gh secret list -R <owner>/<repo>` (names only; that is enough).

## Requiring ForeverCore

Every Forever addon depends on ForeverCore, the suite's shared library, and ships it inside its own release zip.
A store dependency does not reach a player who is updating: CurseForge can update the addon without installing its
required dependency, and a Wago upload carries no dependencies at all, because the packager sends Wago only label,
patches, stability and changelog. In the TOC:

```toc
## Dependencies: ForeverCore
```

In `.pkgmeta`, an external at the release `tools/forever-core.txt` pins, moved to the zip's top level beside the
addon's own folder, and no `required-dependencies` entry (one owner for the folder):

```yaml
externals:
  ForeverCore: https://github.com/cjber/forever-core/releases/download/v1.4.1/ForeverCore-v1.4.1-forever.zip

move-folders:
  LegacyForever/ForeverCore: ForeverCore
```

Keep the external's tag equal to the tag in `tools/forever-core.txt`, and `<package-as>/ForeverCore` equal to your
`package-as`; `tools/check_consumers.py` fails either mismatch. ForeverCore's own store pages are CurseForge
`forevercore` (project 1796337; `forever-core` belongs to someone else) and Wago `addons.wago.io/addons/forever-core`
(project ID `RNL4RQNo`). Do not list ForeverCore under `OptionalDeps` and do not copy its runtime files into the addon.

## 2. CurseForge project (authors.curseforge.com)

Use the create wizard at `https://authors.curseforge.com/#/projects/create/choose-game`. Its internal
`/_api/...` endpoints exist, but the form is the reliable path; don't reverse-engineer the JS bundle
(tool output gets blocked as cookie/query data).

Steps and what trips agents up:

1. **Choose Game** → World of Warcraft, category Addons.
2. **General**: name, summary, categories, logo. **The logo is a user step; Claude cannot upload it.**
   The create form's upload is broken (POSTs `/_api/projects/null/upload-avatar` → 400 "Id must be a
   string"), and the project General page's "Upload image" button opens a native OS file picker with no
   DOM file input behind it, so `file_upload` has nothing to target (don't click it: the stray picker
   blocks the tab). Ask the user to click "Upload image" and pick the repo's 400×400 PNG
   (`media/icon-400.png` in cjber's addons), either here or later at `#/projects/<ID>/general`.
3. **Description**: set the textarea with `form_input` to `docs/curseforge.md`, then **type** a little
   text at the end (click the textarea, `ctrl+End`, type a newline). `form_input` alone does not update
   React state, so the step validates as empty. The description ends with the support buttons; add no
   author footer.
4. **License**: the dropdowns are custom comboboxes whose list often does not show in screenshots. Open
   with a click, then `find` the option by its text (e.g. "GNU General Public License version 3 (GPLv3)")
   and click the returned ref. Close an open list by clicking empty page space before the next field.
   Distribution: "Allow distribution to 3rd party" (the addon is also on Wago/GitHub).
5. **Create** (the user's request to publish is the authorization). You land on
   `#/projects/<ID>/files`; the number in the URL is the **project ID**.
6. **Media** (`#/projects/<ID>/media`): upload with the in-page steps under Store updates, one image
   per run.

A new project stays hidden until a moderator approves it; uploaded files appear after approval.

## 3. Wago project (addons.wago.io)

Wago is an upload mirror for the few players on the Wago app or WowUp's Wago source: CurseForge
carries well over 95% of downloads, so the full store page lives there and Wago gets only what the
packager and a short pointer give it.

`https://addons.wago.io/developers/projects/create`, create from the GitHub repo. Settings: name,
summary, categories, thumbnail. The project ID is the slug in `addons.wago.io/addons/<ID>`.

Its description is this stub, set once on the settings page (paste in the `textarea`, a real keypress
in it, then "Save changes" in that textarea's own form) and left alone afterwards:

```
<Addon name> for WoW: Forever. <The summary line from the TOC.>

Screenshots, the full feature list and the changelog are on CurseForge: <CurseForge project URL>
Source and issues: <GitHub repo URL>
```

Wago has no gallery to maintain. When a Wago gallery still holds images, list their captions for the
user to delete on `addons.wago.io/addons/<slug>/gallery`.

## Store updates

Run the browser work in the user's logged-in Chrome, in batches of about three images, so a slow page
does not outlast the tool call. Confirm every change after a reload or on the public page.

**Descriptions.** After a PR that changes `docs/curseforge.md` merges, paste it on CurseForge, then run `python3 tools/sync_curseforge.py <wow folder>` from `forever-core`: it reads each stored description back from CurseForge's Core API and fails on any word or link that differs from `main`. Its `--push` publishes through fastbrowse but is unreliable until agent-labs-dev/fastbrowse#939 is fixed. It needs `CURSEFORGE_CORE_API_KEY`, in pass as `dev/CURSEFORGE_CORE_API_KEY`. Paste `docs/curseforge.md` without its `forever-family` marker lines. CurseForge shows
"Changes saved successfully" for changes it did not store: set `textarea.mde-text`, then click into it,
press `ctrl+End`, type a newline and click Save with real input. Read the result back after a reload:
CurseForge rewrites the markdown, so compare words and links, not lengths. Wago keeps its stub (step 3).

**CurseForge gallery.** Upload from the current `origin/main` render. Take the title from
`docs/curseforge.md` first, then `docs/gallery.md`. The media title limit is 128 characters.

1. CurseForge rejects uploads of 2 MB or more. For oversized still PNGs, stage lossless WebP
   copies under 2,000,000 bytes. Check dimensions and decoded RGBA pixels against the source
   before uploading. Keep the tracked PNG and its links; keep animated GIFs animated.
2. In Chrome, open "Add media", arm the Playwright `filechooser` event, then click "Upload or
   Drag Image" and call `setFiles` on the chooser with the staged absolute path. The input is
   created on click. This avoids a native picker. The ChatGPT Chrome extension needs "Allow
   access to file URLs" to attach a local file.
3. A new card lands last with a filename for its title. Save its image URL and use it to
   identify the card, including when the old card has the same caption. If an upload times
   out, read the author gallery before retrying.
4. Click the new image to open its editor. Set Title, click Apply, check the saved caption
   on that card, then close with Cancel if the editor stays open. Check Description and
   Feature Media for unintended changes. Read the cards back after a reload; the Core API
   can lag behind the author page.

To reorder, open "Reorder gallery" after a full page load: in-app navigation can leave the
previous project's list in the dialog. Use the sortable card's keyboard controls: press Space
to pick it up, wait until it is active, send arrow keys separately, then press Space to drop it.
Measure the current grid width; Up and Down move by a row and Left and Right move within a
row. Re-read the image URLs in order after each drop, click Done, then check after a reload
and on `curseforge.com/wow/addons/<slug>/gallery`. The public page can lag behind the author page.

For an approved removal, identify the old card by image URL and verify its replacement
first. Hover the exact card to reveal its trash button and selection checkbox. For a batch,
check the selected image URLs and count against the approved list before confirming.
Wait for those cards to disappear before leaving the page. Reload and read back before
retrying a deletion, as the first reload can still show stale cards.

## Keep galleries in sync

A gallery image that no longer matches the addon is a defect of the change that made it stale.
Whenever a visible feature changes, regenerate its mocks in the same PR (`wow-mock-screenshots`),
and after the release upload the new images to both stores. Delete duplicates, older renders of an
image the repo now renders differently, and images neither `docs/curseforge.md` nor `docs/gallery.md`
shows: every image can be rebuilt from the repo. Order each gallery as `docs/curseforge.md` shows its
images, then the rest of `docs/gallery.md`.

## 4. TOC and release

```
## X-Curse-Project-ID: <numeric id>
## X-Wago-ID: <wago id>
```

Before the version bump, smoke the build in the client when it is running, under the game lock, and only
when the player is not playing (a deskpilot screenshot first):

1. Unpack the build under `test-artifacts/<repo>-<build>`, point the addon's `Interface/AddOns` link at it,
   note `date +%s`, then `/reload`.
2. Run `/forever selftest` (the `!!DevSmoke` dev addon, linked from this repo's `tools/devsmoke/!!DevSmoke`). It opens and closes every
   loaded Forever addon's slash command and the world map, and shows "Dev Smoke: N surfaces, F failed" on
   screen.
3. `/reload` again so the client writes SavedVariables, then
   `python3 tools/forever_errors.py --since <noted time> --addon <AddonFolder>`. It reads the journals,
   BugGrabber, `taint.log` and the selftest's failed surfaces. Exit 1 blocks the release: fix the error first.
4. Point the link back at `test-artifacts/<repo>-dev` and `/reload`.

Before the tag, check the changelog entry: a feature release (major or minor bump) names its hero, one of
the repo's own rendered screenshots showing the new feature at its native size, at the top of its section
with `<!-- discord-image: docs/screenshots/<file>.png -->`; `tools/changelog.py --check X.Y.Z` fails without
one.

Then move `## [Unreleased]` to `## [x.y.z] - <today UTC>`, signed commit (personal email for these
repos), push, `git tag -s vX.Y.Z -m vX.Y.Z`, push the tag, and watch the run:

```sh
id=$(gh run list -R <owner>/<repo> -w release.yml -L1 --json databaseId -q '.[0].databaseId')
gh run watch "$id" -R <owner>/<repo> --exit-status
gh run view "$id" -R <owner>/<repo> --log | grep -A1 "Uploading"
```

Done means the log shows `CurseForge ID: <id> [token set]`, `Wago ID: <id> [token set]` and a
`Success!` after each `Uploading ... to` line. `[token set]` missing = secret missing; the packager
then silently skips that site while the run stays green.

## Things only the user can do

Uploading the CurseForge logo, setting the API-token secrets, and anything needing a login. Say
exactly which, with the command or page to use. Deleting store files or gallery images is permanent:
list each one by caption and position per store, and delete only after the user approves that list.
