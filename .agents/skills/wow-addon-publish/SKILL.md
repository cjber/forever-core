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
   text at the end (click the textarea, `ctrl+End`, type the footer). `form_input` alone does not update
   React state, so the step validates as empty. cjber's footer:
   `Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)`
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

**Descriptions.** After a PR that changes `docs/curseforge.md` merges, run `python3 tools/sync_curseforge.py <wow folder>` from `forever-core`: it publishes every changed description through the user's Chrome and reads each back from CurseForge's Core API (`CURSEFORGE_CORE_API_KEY`, in pass as `dev/CURSEFORGE_CORE_API_KEY`). By hand: paste `docs/curseforge.md` without its `forever-family` marker lines. CurseForge shows
"Changes saved successfully" for changes it did not store: set `textarea.mde-text`, then click into it,
press `ctrl+End`, type a newline and click Save with real input. Read the result back after a reload:
CurseForge rewrites the markdown, so compare words and links, not lengths. Wago keeps its stub (step 3).

**CurseForge gallery.** The `file_upload` tool cannot reach this page: its file input is created
detached on click, and a real click opens a native picker that blocks the tab. Instead:

1. Override `HTMLInputElement.prototype.click` to capture `file` inputs without opening a picker.
2. Click "Add media", then "Upload or Drag Image".
3. Fetch the image from `raw.githubusercontent.com` into a `File`, set the captured input's `files` from
   a `DataTransfer`, dispatch `change`. Convert anything over 2 MB in the page: canvas, JPEG, quality 0.9.
4. Wait about 5 s between images. New images land last, and their caption is a filename.
5. Click the card, replace Title, click Apply, and use the side arrows for the next image. Move on only
   after Apply dims. Check for a filename left in Description and an unwanted Feature Media star, which
   can appear after processing.

To reorder, open "Reorder gallery" after a full page load: the dialog can keep another project's list
after in-app navigation. A mouse drag does nothing, so `focus()` the `li.sortable-screenshot-element`,
press real keys, wait 4 s, read the order and click Done. The list is a grid three cards wide and
the arrows move by position on screen: Left and Right move one place within a row, Up and Down move a
whole row, and Left does nothing from the first column. Send space, the arrow (with `repeat` for more
than one) and space as separate key calls: several keys in one string drop presses, and a dropped
space leaves the sorter stuck until Done and a reload. Read the order after each move. The author
site's order can flip between reloads even after a good save: confirm on the public
`curseforge.com/wow/addons/<slug>/gallery` page. That page can serve a replaced file from cache for
hours; when only the public copy is stale, check it again later.

To delete, hover the card so its pencil and trash buttons render, click the trash and then OK in
the "Delete media" dialog, one card at a time with a screenshot before each click. The buttons exist
only on the hovered card, so a script that walks up from an image to "the last button" lands on a
different card's trash. Screenshot coordinates differ from `getBoundingClientRect`; take positions
from the screenshot.

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
2. Run `/forever selftest` (the `!!DevSmoke` dev addon, linked from `forever-smoke`). It opens and closes every
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
