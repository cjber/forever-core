# Brief: in-game bug report / feature request → ready-made GitHub issue

Owner request (2026-10-23, #wow-addons): "add a general report bug or feature request option in game. It should make a
GitHub issue or whatever possible."

## What already exists (do not rebuild)

Every addon already has `/agf report`, `/lf report`, `/path report`, `/sk report`, `/tw report`:
`UI/Report.lua` (window + shared header + caught errors + addon list, all selected for Ctrl+C) plus
`Core/Report.lua` (`ns.ReportLines()`) and `Core/SafeCall.lua`. `adventure-guide-forever/docs/report-window.md`
documents the pattern. That window only produces a blob of text aimed at Discord/forums.

## What is missing, and what to build

A second, deliberate flow: the player says *what* is wrong and whether it is a bug or a feature request, and the addon
hands them a **pre-filled GitHub new-issue link** for that addon's own repo. The client cannot open a browser or make an
HTTP request, so the honest ceiling is: build the URL, put it in the window fully selected, tell the player to Ctrl+C
and paste it into their browser. Do not pretend an addon can "submit" an issue.

`/path issue` (and `/<cmd> issue` in the other four) opens a composer window:

```
+----------------------------------------------+
| Report a bug or request a feature            |
| [ Bug ] [ Feature request ]                  |  <- two toggle buttons, Bug selected
| Title                                        |
| [ Bug: ................................... ] |
| What happened, or what you would like        |
| [ multiline edit box, ~4 lines             ] |
| [ Copy issue link ]  [ Copy report ]         |
| The link is selected. Press Ctrl+C ...       |
| +------------------------------------------+ |
| | read-only, selected edit box (URL)       | |
| +------------------------------------------+ |
+----------------------------------------------+
```

- Type toggle switches the prefix of the Title box (`Bug: ` / `Feature request: `) and the label/template used.
- "Copy issue link" builds the URL below and selects it; the hint says to paste it into a browser.
- "Copy report" puts the full markdown report (details + system information) in the same box, selected, for a
  Discord/forum post or for pasting into the form if the browser drops the prefill.
- The system information is `Report.Text(ns.ReportLines())` — the existing, already-tested builder. Nothing new is
  collected.

### URL

```
https://github.com/<owner>/<repo>/issues/new?template=report.md&title=<enc>&body=<enc>&labels=<bug|enhancement>
```

- `<owner>/<repo>` comes from the TOC: `C_AddOns.GetAddOnMetadata(addonName, "X-Website")`, strip
  `https://github.com/` and any trailing `/`. No per-addon constant, so the file stays portable.
- `template=report.md` — because `blank_issues_enabled: false` in every repo and the existing templates are issue
  **forms** (`.yml`), which ignore the `body` parameter. A markdown template is the only reliable way to prefill a
  whole issue body from a URL. Add `.github/ISSUE_TEMPLATE/report.md` to each of the five repos:

```markdown
---
name: Report from the game
description: A bug or feature request filed from the addon's in-game report window, with the details already filled in.
---

<!-- Opened from the addon's in-game report window. The details below are filled in for you; edit anything that is wrong. -->
```

- `labels=bug` for a bug, `labels=enhancement` for a feature request (both labels exist; they are the ones the yml
  forms already use). Keep the label out of `report.md`'s front matter so the URL decides it.
- Percent-encode every byte outside `A-Za-z0-9-_.~` as `%XX` (`%w` in Lua 5.1 is ASCII-only, so
  `("([^%w%-_%.~])"):gsub` style is fine). A space becomes `%20`.
- Cap the encoded body so the URL stays well under 8,000 characters: build the body from the player's details first
  (cap at 1,000 characters through the existing `ns.CutText`) and the system information second (cap at 1,200). If the
  finished URL is still over 7,000 characters, drop the system-information section and add the line
  `System information: copy it from Copy report.` Never cut mid-UTF-8 (use `ns.CutText`, not `#`).

### Issue body (markdown)

```
### What happened, or what you would like

<details or "-">

### System information

<Report.Text(...)>
```

Field labels stay English in every locale, exactly as the existing report does; the player's own details and the
addon's lines are the client's language.

## Files per repo (five repos, same change, only the deltas differ)

| Repo | `ns.L` style | slash command registered in |
|---|---|---|
| adventure-guide-forever | `L.REPORT_TITLE` table keys | `Core/Core.lua` (~line 1078, `if command == "report"`) |
| legacy-forever | `L[...]` | `Core/Core.lua` (~line 96) |
| shortest-path-forever | `L[...]` | `UI/Settings.lua` (~line 576, `SlashCmdList.SHORTESTPATHFOREVER`) |
| skillup-forever | `L[...]` | `Core/Core.lua` (~line 627) |
| tweaks-forever | `L[...]` | `UI/Settings.lua` (~line 149) |

1. `UI/Report.lua` — extend. Keep the file's existing shape, type annotations and comment voice (the file's own header
   says it copies across the Forever addons with only its strings changed; keep that true). Add and export on
   `ns.Report`:
   - `Report.Encode(text) -> string` — the percent encoder.
   - `Report.Repo() -> string` — `owner/repo` from `X-Website`, `""` when absent.
   - `Report.Issue(kind, title, details, lines) -> string` — the finished URL; `kind` is `"bug"` or `"feature"`.
   - `Report.Body(kind, title, details, lines) -> string` — the markdown issue body (used for `Copy report` and by
     `Issue`).
   - `Report.Compose(kind?) -> ()` — builds and shows the composer window, `kind` defaulting to `"bug"`.
   Reuse the existing `Header()`/`Errors()`/`Addons()`/`Text()` untouched; `Text()` keeps its 2,000-character cap.
   The composer is its own frame named `<addonName>Issue`, in `UISpecialFrames`, movable, clamped, `DIALOG` strata,
   `PortraitFrameTemplate` + `Art.Icon` like the report window, created on first use and reused. Escape and the close
   button hide it; the details and title boxes keep their text between opens.
2. `.github/ISSUE_TEMPLATE/report.md` — new, as above.
3. Slash command: `issue` (and `bug` / `feature` as aliases that open the composer on that kind), wired next to the
   existing `report` branch, plus a `HELP_ISSUE` line in the help text next to `HELP_REPORT`.
4. `Locales/enUS.lua` — English phrases are their own keys via the `__index` fallback, so no entry is strictly needed;
   add the keys anyway where the repo lists its phrases (AGF does), and regenerate `Locales/phrases.txt` where the repo
   has one (`python3 tools/phrases.py > Locales/phrases.txt`). Do not machine-translate; other locales fall back.
   New phrases:
   - `Report a bug or request a feature`
   - `Bug`
   - `Feature request`
   - `Title`
   - `What happened, or what you would like`
   - `Copy issue link`
   - `Copy report`
   - `The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste it into your browser: GitHub opens a new issue with this filled in.`
   - `The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report.` (already exists as the report hint)
   - `/<cmd> issue - report a bug or request a feature with a ready-made GitHub issue link`
5. `tests/report_spec.lua` — extend (do not replace). Cover: `Encode` on space/`&`/`#`/UTF-8/`~`; `Repo()` from
   `X-Website` and its absence; `Issue("bug", ...)` starts with the right repo URL, carries
   `template=report.md`, `labels=bug`, the encoded title and the encoded body; `labels=enhancement` for a feature;
   the body holds the details and `System information`; a 4,000-character detail is cut and the URL stays under
   7,000 characters; the window opens on the first call and not again, the box holds the URL, the text is selected,
   Escape hides it, `Copy report` swaps the box to markdown, and a new kind re-prefixes the title.
   The harness must stub `C_AddOns.GetAddOnMetadata` for `X-Website` if it does not already.
6. `docs/report-window.md` (AGF) — add a short `## Issue link` section: what the button does, why the client cannot
   open a browser, why `report.md` exists (forms ignore `body`), and the porting note. Other repos' `docs/` get the
   same paragraph if they carry the page.
7. `CHANGELOG.md` — no version entry (the release step does that); add an `Unreleased` bullet only if the repo has
   such a section.

## Gates

Run the repo's full `## Commands` block from its `AGENTS.md` — stylua, ruff, luacheck, typecheck, every
`tests/*_spec.lua`, `check_generated.py --offline` where present, `tools/changelog.py --check`, the sift gate. The
specs run on Lua 5.1/luajit with stubbed client APIs; frames cannot be exercised for real, so list the `/reload`
checks in the PR (open `/path issue`, switch to Feature request, copy the link, paste it into a browser, confirm the
issue opens with title, body and label filled in; confirm Escape closes and the text survives reopening).

## PRs

One PR per repo, branch `ccr-cc333990-q8ydc4-issue-report`, conventional commit `feat(report): in-game bug and feature
request link`, signed with `-S`, author cjberragan@gmail.com, no model names. PR body: Why / What / Gate / In-game
checks, the link to this brief, and `Closes` nothing (no issue exists — mention the owner request instead). Run the
`code-review` skill on the diff before sending READY. Then send the coordinator one line per PR:
`READY <PR URL> <head sha>`.
