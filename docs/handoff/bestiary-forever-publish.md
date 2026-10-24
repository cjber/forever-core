# Bestiary Forever — publish as its own private repo

The addon is complete and verified. The tree in `forever-handoff/bestiary-forever/` is the repository root
(`BestiaryForever.toc` at the top). It could not be pushed to `cjber/bestiary-forever` because the workspace GitHub
App has no `createRepository` permission (`403 Resource not accessible by integration` on POST /user/repos and on the
GraphQL `createRepository` mutation), and there is no personal `gh` login in the sandbox.

## One-time adoption

```sh
git clone --branch ccr-cc333990-q8ydc4-handoff https://github.com/cjber/skills.git skills
mkdir bestiary-forever && cd bestiary-forever && git init -b main
cp -R ../skills/forever-handoff/bestiary-forever/. .
git add -A && git commit -m "feat: Bestiary Forever 0.1.0"
gh repo create cjber/bestiary-forever --private --source . --push \
  --description "Bestiary Forever - a cosmetic creature catalogue for WoW: Forever (Interface 16001)"
```

Or, with the repo already created empty, `git remote add origin git@github.com:cjber/bestiary-forever.git && git push -u origin main`.

## State of the tree

- TOC: Interface 16001, Version `@project-version@`, SavedVariables `BestiaryForeverDB`.
- 10 zones / 184 Classic creatures in `Data/Creatures.lua`; pure-Lua `Core/Model.lua`; versioned `Core/API.lua`.
- `luacheck .` 0 warnings, `stylua --check .` clean, all three specs pass (`lua5.1 tests/*_spec.lua`).
- CI: `.github/workflows/ci.yml` (luacheck, specs, stylua, ruff, actionlint/zizmor, gitleaks) and
  `.github/workflows/release.yml` (BigWigs packager). Release is inert until `X-Curse-Project-ID` / `X-Wago-ID` and the
  `CF_API_KEY` / `WAGO_API_TOKEN` secrets exist — intentional, the owner tests in game first.
- Screenshots: `docs/screenshots/` (three pages, ten creature examples, `demo.gif`), rendered by
  `tools/mockups.py` from the pinned client build via the vendored `tools/wowmock/`.
