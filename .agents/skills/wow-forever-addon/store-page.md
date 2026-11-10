# Store page template (WFA-11)

Every addon's `docs/curseforge.md` follows this template, in this order. It is the CurseForge description and the
source of its gallery. `forever_tools.store_page` checks it in each addon's CI, so a page that leaves a part out
fails the build.

`<angle brackets>` are filled per addon. Every other line is copied exactly.

```markdown
<Pitch: one to three sentences. Starts with the addon's TOC title, then says what it does and where it lives in the
game's UI.>

<Optional: one paragraph naming the addons it reads data from or works with, required or optional.>

Free, with nothing locked behind it. If it saves you time, you can [sponsor me on GitHub](https://github.com/sponsors/cjber), which takes no fees, or [buy me a coffee on Ko-fi](https://ko-fi.com/cjber). For help and each day's release notes, [join me on Discord](https://discord.gg/FpHugGxRJY).

![<alt text>](https://raw.githubusercontent.com/cjber/<repo>/main/docs/screenshots/<lead>.<gif|png>)

<Caption: what to look at in the lead image, in plain words, not its alt text.>

![<alt text>](https://raw.githubusercontent.com/cjber/<repo>/main/docs/screenshots/<name>.png)

<Caption.>

<More images, each with its caption: three to six images in all.>

These images are generated previews of the <short name> UI.

## Features

- **<Feature name>.** <One or two sentences on what it does for the player.>
- <Three to eight bullets, each led by a bold name.>

<Optional: one paragraph on a real limitation.>

## <Optional: one section on how the numbers or data work, for example "Prices" or "How kills are counted">

## Usage

<How to open it: slash command, minimap button, addon compartment, where its options live.>

For a bug report, paste `/<command> report`.

Translated into German, French, Spanish, Brazilian Portuguese, Russian, Korean and Chinese (machine translated; corrections welcome through the [translation form](https://github.com/cjber/<repo>/issues/new?template=translation.yml)).

<!-- forever-family:start -->
<The family block, written by tools/check_family.py --fix (WFA-32).>
<!-- forever-family:end -->

<Optional: one paragraph on what changes when other Forever addons are installed together.>

Source code and issues: [github.com/cjber/<repo>](https://github.com/cjber/<repo>). Licence: GPL-3.0-or-later.

Built with AI assistance.

[![Join me on Discord](https://raw.githubusercontent.com/cjber/<repo>/main/docs/discord-button.png)](https://discord.gg/FpHugGxRJY) [![Sponsor me on GitHub](https://raw.githubusercontent.com/cjber/<repo>/main/docs/github-sponsors-button.png)](https://github.com/sponsors/cjber) [![Support me on Ko-fi](https://raw.githubusercontent.com/cjber/<repo>/main/docs/kofi-button.png)](https://ko-fi.com/cjber)
```

## What the check enforces

- **Order.** Pitch, sponsor line, images, `## Features`, at most one optional `##` section, `## Usage`, the family
  block, source line, AI line, the button row. No other `##` headings: Install, Development and Credits live in the README.
- **Images.** Three to six, the first above `## Features`, every one under `docs/screenshots/` at a `main` raw URL,
  every file present in the repo, each followed by its caption (WFA-25). The lead image shows the main feature
  in the stock UI (WFA-23).
- **Fixed lines.** The sponsor sentence, the "generated previews" line, the report line, the translation line, the
  source line, the AI line and the button row (Discord, GitHub Sponsors, Ko-fi, in that order, each image present
  in the repo), each exactly as above with only the placeholders filled.
- **Features.** Three to eight bullets, each led by a bold name ending in a full stop.
- **Pitch.** Starts with the addon's `## Title` from the TOC, without colour codes.
- **Length.** Under 1,000 prose words by `check_copy.py --words`, the family block not counted (WFA-11).

## The gallery

The CurseForge gallery holds exactly the page's images, in page order, each titled with its alt text. Every image
can be rebuilt from the repo, so a gallery image the page no longer shows is deleted. `tools/sync_curseforge.py`
in forever-core compares each gallery with its page through the CurseForge API; CI cannot, as it holds no API key.

## The buttons

The three button images are vendored from forever-core's `docs/` by `tools/sync_consumers.py`, and
`tools/check_core_shared.py` fails a copy that differs. `tools/render_discord_button.py` draws the Discord one to
match the Sponsors one. Each addon's THIRD_PARTY.md credits them:

| Asset | Used for | Licence |
| --- | --- | --- |
| `docs/discord-button.png` | The Discord button on the store page; drawn in forever-core with Discord's logo from [Simple Icons](https://simpleicons.org) and the Adwaita Sans font | Simple Icons: CC0; Adwaita Sans: SIL OFL 1.1; the logo is Discord's, used to link to a Discord server |
