# Round 4: full translations (owner-approved 2026-10-16: "I want full translations round")

brief.md (commits, signing, PRs, attribution, coordinator merges, strict protection, WFA-33 credit rule) applies.
Never merge, push tags or trigger workflows. Send `READY <PR URL> <head sha>` to "main".

## Goal
Every addon ships in all of WoW's client languages besides English:
deDE, esES, esMX, frFR, itIT, koKR, ptBR, ruRU, zhCN, zhTW.
First check which of these the WoW: Forever client actually offers (the Blizzard TOCs or GlobalStrings on wago.tools
for the pinned Forever build). Skip any it doesn't offer, and say which you skipped.

## Rules
- **Human translations win.** Legacy's frFR is Brainc3ll's: keep every existing human line and fill only the gaps.
  Never overwrite a human translation with a machine one.
- **Machine translations are marked.** Each machine-translated file starts with a comment:
  `-- Machine translated (<date>); corrections welcome: <the repo's translation issue form URL>`.
  If a file mixes human and machine lines, mark the machine lines (a trailing `-- mt` comment, or a separate
  table merged after the human one: whichever fits the repo's locale format).
- **Use the game's own terms.** Build a glossary per locale from the client's GlobalStrings for the pinned Forever build
  on wago.tools (e.g. `https://wago.tools/db2/GlobalStrings/csv?build=<build>&locale=<loc>`, or the right endpoint).
  It covers terms such as flight master, quest, trainer, Hearthstone, auction house, objective tracker, profession
  names, bags and bank. Use the official term wherever one exists. Keep the glossary out of the repo, or commit only
  a small generated one if a check needs it.
- **Never change these:** placeholders (`%s`, `%d`, `%.1f`, `%1$s`, …), colour codes (`|cff…|r`), texture escapes
  (`|T…|t`), atlas escapes, newlines (`\n`), slash commands, addon names (Shortest Path Forever and so on), and key
  names in `[brackets]` that the code matches. Keep the same count and order of placeholders, unless the format
  supports positional ones and the code passes them that way.
- **Voice:** plain, short and polite, in the register WoW's own UI uses in that language. No marketing.
- **Fit:** UI labels must fit. Prefer the shorter wording, especially for button labels: German runs long, and CJK
  needs no spaces.
- **Wire each file into the TOC** after `Locales\enUS.lua` (or as the repo's locale loader expects). Follow each repo's
  `Locales/README.md` format exactly. AGF uses symbolic keys, so translate its value table, not the phrases.
- **Shared module strings** (UI/ForeverFamily.lua phrases) must be translated the same way in all five repos. Use the
  same wording for them in every repo; the coordinator will compare.
- **Store and README copy stay English.** Add one line to README and docs/curseforge.md, within the word limits:
  "Translated into <languages> (machine translated; corrections welcome)". Link the translation form.
- **Changelog:** "**In your language.** The addon is now in German, French, … (machine translated; corrections are
  welcome through the translation issue form)." Credit any human translator by name.

## Checks (TOOLING, in cjber/skills forever_tools first, then synced)
`check_locales.py` fails when:
- a locale file's key isn't in phrases.txt or enUS, or the file has a syntax error;
- a placeholder set or count differs from English;
- a `|c`/`|r`, `|T`/`|t` or `\n` count differs from English;
- a locale file isn't loaded by the TOC.

It prints each locale's coverage and doesn't fail on missing lines, because those fall back to English. Add a spec, or
extend an existing one, that loads each locale file in the harness with GetLocale stubbed and checks that every
string formats without error, using sample arguments for each placeholder.

## Release-time upkeep
Add a step to each repo's release skill (or to wow-forever-addon's release guidance through the skills PR): before
release prep, translate any phrases added since the last tag into every shipped locale. check_locales shows the gaps.

## Order
1. TOOLING: the skills PR with check_locales plus the rule (WFA-34: shipped locales, machine-translation marking,
   human lines win), then a sync PR in each repo, together with the c841746 resync that's already queued.
2. Each repo agent: one PR, `feat: translations (<locales>)`, after its sync lands. Run the full gate plus
   check_locales. Use a code-review (high) pass, and also spot-check by back-translating a sample of 20 lines per locale.
3. Then release prep: a minor bump.
