---
name: wow-addon-publish
description: "Use in a WoW addon repo (a .toc at the root; cjber's WoW: Forever addons such as tweaks-forever, skillup-forever, legacy-forever, shortest-path-forever) to publish it on CurseForge and Wago, create the store project, set its description/logo/gallery, or cut a release that uploads to both. Not for non-WoW repos."
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
6. **Media** (`#/projects/<ID>/media`): `file_upload` the screenshot PNGs straight into the media file
   input (`find` "file input for uploading media/screenshots"). This one works; it has a real input
   (target the `type="file"` button, not its label) and takes several files at once. Each image must
   be under 2 MB: convert large PNGs to `-quality 90` JPEGs in a temp dir first. Reload the page to see
   a multi-file upload's results.

A new project stays hidden until a moderator approves it; uploaded files appear after approval.

## 3. Wago project (addons.wago.io)

`https://addons.wago.io/developers/projects/create`, create from the GitHub repo. Settings: name,
summary, categories, thumbnail. The project ID is the slug in `addons.wago.io/addons/<ID>`.

Gallery, one image per submit: navigate straight to
`https://addons.wago.io/developers/projects/<slug>/gallery/create` (the "New Gallery Image" link
sometimes does nothing), `find` the file input, Description and "Add Image", then:

1. `file_upload` the image in its own call. Attaching re-renders the form a moment later and wipes
   anything typed in the same batch.
2. In a later call: click Description, `ctrl+a`, type the caption, zoom to check it. The first attempt
   after an upload is often dropped; repeat until the zoom shows it.
3. Submit only once the caption shows. A submit with an empty caption still uploads.
4. Check with `get_page_text` on the gallery page.

Wago lists the newest first, so upload in reverse display order. `/gallery/<id>/edit` edits only the
caption; it cannot swap the image, so a stale image means uploading a new one and the user deleting
the old one.

## Keep galleries in sync

A gallery image that no longer matches the addon is a defect of the change that made it stale.
Whenever a visible feature changes, regenerate its mocks in the same PR (`wow-mock-screenshots`),
and after the release upload the new images to both stores and list the stale ones, by caption,
for the user to delete.

## 4. TOC and release

```
## X-Curse-Project-ID: <numeric id>
## X-Wago-ID: <wago id>
```

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

Uploading the CurseForge logo, setting the API-token secrets, permanently deleting store files or
gallery images, and anything needing a login. Say exactly which, with the command or page to use.
