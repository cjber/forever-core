# SkillUp Forever: opt-in `/su export` of trainer requirements seen in game (issue #124)

## Goal
Add an opt-in slash command that prints the trainer requirements this character has actually
seen at trainers, as a Lua table literal ready to paste into `tools/gen_trainer.py`'s
`SEEN_REQUIREMENTS`. Nothing else changes behaviour; nothing runs automatically.

## Why
`Data/Trainer.lua` is generated and its required skills are an inferred rule (skills moved by
however far Forever moved each recipe's yellow and grey, clamped by `SEEN_REQUIREMENTS`). Players
who visit a trainer and see the real number already have it saved in
`ns.db.trainer[skillLine][recipeID] = { fee, bundledRequirement, shownRequirement }`. Today that
value only helps that one character. Issue #124 asks for a way for a player to hand the values
back so they can be merged into the committed override table and the guess improves for everyone.
This is the one remaining code half of #124. The live-trainer verification half stays open.

## Read first
- `AGENTS.md` (Commands section is the gate; follow its conventions exactly).
- `CLAUDE.md` / `CONTRIBUTING` if present.
- `Core/Core.lua` around the slash handler (`SLASH_SKILLUPFOREVER1/2`, `local function Slash`).
- `Integrations/Trainer.lua` (`ns.TrainerReport`, `ns.TrainerChecks`) for house style.
- `Core/Report.lua` for the existing copyable-text window used by `/su report`.
- `tools/gen_trainer.py` `SEEN_REQUIREMENTS` (currently one entry, `9985: 110`).
- `Locales/` for how strings are added.

## Behaviour
1. New subcommand: `/su export trainers` (accept `export` on its own as an alias for the same
   thing, since trainers are the only export today). Do not take over `export` for anything else.
2. It collects every recorded row where a shown requirement was saved (third element of the row).
   Rows with only `{ fee, bundled }` carry no player-seen requirement and must be skipped.
3. It prints, in a copyable window (reuse the `/su report` window if it takes plain text), the
   longest seen requirement per recipe across all skill lines, formatted exactly as:
   ```lua
   SEEN_REQUIREMENTS = {
       9985: 110,  -- <Recipe Name>, <Profession>, seen <YYYY-MM-DD or build>
   }
   ```
   Keep the comment short. Recipe name via the existing `RecipeName` helper. If the profession
   name is not cheaply available, omit it rather than inventing one.
4. If nothing has been seen, print a plain line telling the player to visit a trainer first, and
   do not open an empty window.
5. Chat fallback: if the copy window cannot be shown, print the same lines to chat through `ns.Print`.
6. It must never write to saved variables, never print on login, never run on an event, and must be
   safe to run in combat (no protected calls, no taint). The command is purely a read plus a frame.
7. Add the command to the `/su help` list and to the locale file, matching existing phrasing style.

## Files you will likely touch
- `Core/Core.lua` (dispatch, help line)
- `Integrations/Trainer.lua` (the collector, e.g. `ns.TrainerExport()`)
- `types/Namespace.lua` (annotation for the new namespace function)
- `Locales/enUS.lua` (strings)
- `tests/trainer_export_spec.lua` (new spec, modelled on `tests/trainer_spec.lua` and using
  `tests/client.lua`'s mock client)
- `CHANGELOG.md` (one entry under the unreleased/latest heading in the repo's existing style;
  `python3 tools/changelog.py --check` must pass)

## Tests to write
- Rows with a shown requirement are exported; rows without one are not.
- The highest shown requirement wins when two skill lines recorded the same recipe.
- Empty state prints the "nothing yet" line and opens no window.
- The generated text is valid Lua: load it with `loadstring` in the spec and assert the table
  round-trips to the expected values. This is the important one.
- `/su help` lists the new command.

## Gates (all must pass before you open the PR)
```
stylua --check .
luacheck .
tools/typecheck.sh
for s in tests/*_spec.lua; do luajit "$s" || exit 1; done
python3 tools/changelog.py --check
python3 tools/check_generated.py
python3 tools/check_locales.py
```

## Delivery
- Branch from current `main`, e.g. `feat/su-export-trainer-requirements`.
- Commit signing is automatic: never use `-s`, `--signoff`, or any signing flag.
- Open a PR against `main` titled `feat: export trainer requirements seen in game as SEEN_REQUIREMENTS (#124)`.
- Do not merge it yourself. Report the PR number and the gate output.

## Boundaries
- No new dependencies, no generated data edits, no changes to the release workflow, no touching
  `Data/Trainer.lua` by hand.
- Do not change what is saved when a trainer is visited, and do not alter planning behaviour.
- Keep it small: this is one command plus its spec.
