# Forever Core

The shared floor under the WoW: Forever addon suite: one objective-tracker column, the grip and Lock switch that move
it, the section order that stacks it, and the Questie bridge that keeps it clear of Questie's own quest list.

**Interface:** 16001 (WoW: Forever, `_classic_beta_`)

## What it is for

Adventure Guide, Legacy, Shortest Path and SkillUp each draw sections into the same floating column beside the quest
tracker. Before this addon, each one carried its own copy of that column, so a layout fix or a Lock toggle meant four
identical pull requests and four copies that could drift apart between releases.

Forever Core also owns shared error capture (`Core/SafeCall.lua`), the report and issue window, and the Forever-family
link box. All five addons vendor those files so error reporting, command handling, selection behavior and link copying
stay consistent.

Forever Core is the one copy. The four addons vendor these files byte for byte (`docs/adoption.md`), and the first
Forever addon to load publishes the column as `ForeverTrackerHost`; every later one adopts it. A player with three of
them installed still gets one column, and a player with one installed gets the same column with no extra dependency.

Installing Forever Core itself is optional. It is there so the shared code has a home, so a fix can be developed,
tested and released on its own, and so a future addon can adopt the column without copying it.

The repo also owns a reusable offline UI mock renderer in [`tools/wowmock/`](tools/wowmock/README.md). It centralizes
client asset extraction, BLP decoding, font and atlas lookup, native widgets and frame compositing. Addon scene
scripts remain specific to the feature each repo owns.

## What it does not do

It draws no sections of its own and knows nothing about quests, routes, professions, challenges or creatures. Sections
belong to the addon that owns the feature: see the suite's ownership boundaries in `docs/handoff/boundaries.md`.

## Install

Drop the `ForeverCore` folder in `Interface/AddOns`. `/fcore` prints the column's anchors, heights and combat state,
which is the same diagnostic the addons print from their own slash commands.

## Licence

GPL-3.0-or-later. See `LICENSE`.
