---
name: foreverauras
description: "Builds and decodes ForeverAuras (WoW Forever WeakAuras fork) import strings without the game. Use when asked to make, change or explain a WeakAura or ForeverAura, such as a missing-buff alert or a cooldown icon."
---

# ForeverAuras

ForeverAuras (`cf:1703325`, installed through `wowaddon`) is the fork of WeakAuras for WoW Forever.

The user's auras live in the dev addon `DevAuras` in `~/drive/proj/wow/forever-dev` (private repo cjber/forever-dev), linked
into the client as `DevAuras`. Each file in its `Auras/` declares specs with `ns.Aura({d = data, c =
{children}})`, the shape of an import payload. At every login or `/reload` the addon adds or updates each
spec through ForeverAuras' own `WeakAuras.Add`, which runs the same upgrade and defaults as an import, and
skips a spec whose text has not changed, so edits made in game stand until the spec changes. `/devauras`
lists the specs; `/devauras reset` reapplies all of them.

`scripts/fa.lua` makes import strings for sharing an aura with someone else. It uses the installed
addon's own LibSerialize and LibDeflate (`!WA:2!` format), so its strings are the format the addon reads.

```sh
luajit <forever-core>/.agents/skills/foreverauras/scripts/fa.lua encode <Auras/X.lua> [id]   # prints the import string(s)
luajit <forever-core>/.agents/skills/foreverauras/scripts/fa.lua decode <file|->              # prints a string's payload as Lua
```

`FA_DIR` names the installed addon folder, the `_forever_` client's `Interface/AddOns/ForeverAuras`; the script stops without it.
The encoder stamps `internalVersion` from the installed addon, so the import runs the addon's own
upgrade and defaults over every field the spec leaves out.

## Building an aura

1. Put the aura in a Modern Aura Group wherever it can go in one. Add a reminder as a child in
   `Auras/Reminders.lua`, or copy that file for a new group and list it in `DevAuras.toc`. A lone aura
   is for something that never sits beside others. Give every display a fixed `id` and a unique `uid`.
2. Choose the trigger (below), then the display, the load conditions, and any options the user asked for.
3. Look up every field you set in the installed source, in the file the table below names. When a field's
   meaning is unclear, decode a published aura that uses it rather than guessing.
4. Check the file loads: `luajit <forever-core>/.agents/skills/foreverauras/scripts/fa.lua encode <file>`, piped into the same script with `decode -`, prints every display.
5. Commit in `forever-dev` and push, then give the user the in-game check: `/reload`, the chat line
   `DevAuras: installed <id>` or `updated <id>`, and what should show. Agents never drive the client.

The aura is done when the file loads, the decoded output matches the spec, and every field it sets is one
you found in the source.

## Triggers

Forever keeps aura data secret in combat. **Aura (Legacy)** (`type = "aura2"`) cannot list a unit's
auras while they are secret, so it goes stale mid-fight. **Aura (Modern)** (`type = "secretAura"`) is
drawn by the client's own aura frames and keeps working. Use Modern for any buff or debuff trigger.

Modern trigger fields (`BlizzardAuraDisplay.lua` `Display.Validate`, `SecretAuraSingle.lua`):

- `unit`: `player`, `target`, `focus`, `pet`, `group`, `party`, `raid`, `boss`, `nameplate`, `member` (with
  `specificUnit`). `debuffType`: `HELPFUL` or `HARMFUL`.
- `secretShowOn`: `showOnActive` (default), `showOnMissing`, or the other `Display.showOnValues`.
- Names: `secretUseRankSpellIDs = true` with `auraRankSpellIDs = {"Aspect of the Hawk", ...}`. A name
  matches every rank. Exact IDs: `auraspellids = {"13165"}`.
- `data.triggers.activeTriggerMode` must point at the Modern trigger: it is what draws the display.

Modern displays accept the `icon`, `aurabar`, `text`, `progresstexture` and `texture` region types. Text
is literal or one each of `%p`, `%s`, `%n`; glows are `buttonOverlay`, `Proc`, `Pixel` or `ACShine`; the
only sub-elements are text, texture, glow and border (`SecretAuraAppearance.lua`
`Display.ValidateAppearance`). A Missing icon shows `displayIcon` when `iconSource = 0`.

## Modern Aura Group

The default container. It is a normal `group` with `blizzardFlow = true`, and its Aura (Modern) children
line up and stay in step in combat, which a Dynamic Group cannot do while auras are secret
(`SecretAuraFlow.lua`). The editor's own defaults are `blizzardFlowGrowth = "RIGHT"`,
`blizzardFlowSpacing = 2` and `blizzardFlowOrigin = "group"` (`ForeverAurasOptions.lua`). Growth also
takes `LEFT`, `UP`, `DOWN`, `CENTER_HORIZONTAL`, `CENTER_VERTICAL` and `GRID`. The group lists its
children's ids in `controlledChildren`, and each child sets `parent` to the group's id and offsets of 0.

## Where fields are defined

| Field | Source file |
| --- | --- |
| Icon and group defaults | `RegionTypes/Icon.lua`, `RegionTypes/Group.lua` `default` |
| Text and glow sub-elements | `SubRegionTypes/SubText.lua`, `SubRegionTypes/Glow.lua` |
| Load conditions (`load.use_class`, `class = {single = "HUNTER"}`, `use_combat`) | `Prototypes.lua` load prototype |
| Import payload (`m`, `d`, `c`, `v`, `s`) | `Transmission.lua` `DisplayToString`, `WeakAuras.Import` |

## Look

Every reminder has one look, the "No Aspect" one: build it through `reminder()` in
`Auras/Reminders.lua`, which takes only the trigger, so a new aura never styles itself. That look is a
50 px icon at zoom 0 in ForeverCore's Cooldown Manager frame (`cooldownFrame = true`, which `Core.lua` applies through `ForeverCore.Art.CooldownIcon`), no glow, and a fixed label under
it in Friz Quadrata 12, gold `{1, 0.82, 0}`, drop shadow, no outline. Give each state that needs
different words its own reminder with its own label, rather than one `%n` label. Each label is as wide as
its icon's slot in the row (icon plus the group's spacing), so neighbours never overlap. Change the look
only when the user asks.

A display that is not an Aura (Modern), such as a custom-trigger icon, is never drawn itself in a Modern
Aura Group: ForeverAuras draws a copy of it in the row (`SecretAuraStand.lua`). `Core.lua` frames both the
region's icon and that copy; judge such an icon by the copy, not by the region `WeakAuras.GetRegion` returns.

## Toggles

When the user wants something to be optional, such as showing only in combat, keep one spec and name the
toggle in its header comment (`load.use_combat = true`). The user can flip it on the aura's Load tab
after importing, so one string covers both.
