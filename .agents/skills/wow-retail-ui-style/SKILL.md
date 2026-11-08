---
name: wow-retail-ui-style
description: "Build and review WoW: Forever addon interfaces using the client's clean Retail-style frames, widgets and assets. Use for UI design, mockups, layouts, textures, fonts, native integrations and visual audits."
---

# WoW Retail UI Style

WoW: Forever uses many modern Retail assets. Match the native Forever client, not an older
Classic skin or arbitrary assets from current Retail. Use the pinned build in the
[asset registry](../../../docs/asset-registry.md), including its blacklist and conditional uses.
Read this skill and the registry before choosing art or rendering a mockup.
For panel composition and edge ownership, the canonical source is [ui-composition.md](../../../docs/ui-composition.md).

## Design target

- **Integrate first.** Put the feature in the native window that owns the task, using its tabs,
  page or detail pane. SkillUp's Professions side tabs and Adventure Guide's quest-map tab are
  suite references. A standalone movable window needs a task that the native host cannot serve;
  a generic floating frame is not the default.
- **Match the whole panel.** Inspect the host's source and a readable screenshot: frame, portrait,
  content textures, inset boundaries, selection treatment, typography and action placement.
  Native fonts and buttons alone do not establish a visual match.
- **Use compact content rhythm.** Match the host's row heights and icon sizes. SkillUp's recipe
  list uses 20-unit rows; its two-line item lists use 46-unit rows with 37-unit icons. These are
  references for different content types, not one global row size. Keep related facts together,
  align counts, and use shared section headings instead of repeating labels on every row.
- **Use the host's content surfaces.** Clean Retail style includes textured lists, inset panels
  and the host's own detail art where the client uses it for that subject. A profession-specific
  illustration belongs to that profession, not to an unrelated commission page. Do not substitute one large
  flat fill, spread a short list across a tall window, or add scenery to fill unused space.
  Preserve native host dimensions when integrating; use a useful detail pane or an honest empty
  state rather than invented rows.
- **Keep optional integrations optional.** A page in Blizzard's Professions window must not
  require SkillUp to be installed. Choose the host by the player's task, not by a dependency.

## The 12 rules

1. **Templates over textures.** Start with the closest Blizzard XML/Lua template or mixin for the control. Let its template provide the expected layout, scripts, hit rects, and accessibility behavior; customize only what the feature needs.

2. **NineSlice over drawn borders.** Use the frame's NineSlice and a named Blizzard layout for panel edges and corners. Don't approximate a standard panel with many independent textures or a single stretched border.

3. **Blizzard atlases over bespoke art.** Reuse current Retail atlases and media for familiar controls, states, and icons. Check the atlas exists in the target build; use addon art only where it communicates addon-specific content.

4. **Native widgets over imitations.** Use buttons, check buttons, dropdowns, scroll boxes, edit boxes, sliders, and status bars from Blizzard's widget system. Preserve their normal interaction scripts and state handling.

5. **Retail typography.** Use the current shared font objects and readable hierarchy. Match Blizzard's sizing and emphasis for title, body, metadata, and disabled text; avoid hard-coded font paths and excessive all-caps.

6. **Retail spacing and alignment.** Follow the target panel's spacing rhythm, align related controls to shared edges, and keep labels close to their controls. Use anchors and layout systems instead of pixel-positioning every child independently.

7. **Color carries meaning.** Use Blizzard's semantic colors and class/reaction colors where they carry established meaning. Keep text contrast legible and avoid using color alone to signal state.

8. **States are complete.** Define and inspect normal, hover, pressed, checked, disabled, selected, focused, and unavailable states as applicable. State changes must remain visible with the panel's art and opacity.

9. **Input follows Retail expectations.** Support mouse and keyboard navigation, sensible tab/focus order, Escape and confirmation behavior where appropriate, tooltip access, and gamepad navigation when the surrounding interface supports it.

10. **Layout adapts to real content.** Anchor to parent bounds, handle localized or long strings, changing list lengths, and UI scale changes. Avoid overlap, clipped labels, and fixed sizes that only fit English test data.

11. **Respect secure and protected UI.** Follow combat lockdown and taint rules for protected frames and actions. Defer protected changes during combat and use supported hooks or APIs instead of replacing Blizzard behavior.

12. **Verify in the target client.** Confirm the interface in the current Retail client at representative UI scales and states. Check actual atlas/template rendering, interactions, long text, and combat behavior; update assumptions when the client API differs.

## Workflow

1. Read [ui-composition.md](../../../docs/ui-composition.md), identify the target Forever build and the native host that owns the interaction. Inspect SkillUp or the nearest suite integration as a concrete layout reference.
2. Inspect the host template, mixin, atlas and API. Resolve every proposed asset against the registry: approved native use, conditional use in its proper context, or blacklisted. Record names and the selected atlas set in the mockup source or review notes.
3. Approve one whole-panel lockup before implementation. Confirm edge ownership, artwork clipping, one icon chrome owner, semantic colours and compact spacing, then build the smallest addon-specific layer on top of those conventions.
4. Render concepts inside their proposed host with representative full, short, empty and unavailable states. Compare against the host at the same UI scale for gaps, texture choice, row density and alignment. Label sample data and proposed behavior clearly.
5. Present every generated variant for owner review using the owner's preview workflow. A rendered concept establishes design intent, not in-game correctness; check it in the headless client (`wow-forever-addon/in-game.md`) and list what waits on the user.

## Never use (blacklist)

Buttons use the `SharedButton*Template` family and its set-1 `128-RedButton` atlas.
Legacy loose chrome and the `UIPanelButton*` templates that select it are forbidden.
Run the shared `forever_tools.assets` checker for runtime and renderer references;
art helpers and `art-ok` comments do not waive this blacklist. The registry lists
the approved states and the native highlight exception.

The [asset registry](../../../docs/asset-registry.md) owns the inventory, conditional uses and
named exceptions. The [audit sheets](../../../docs/asset-audit.md) show actual asset appearance;
open the relevant sheets when choosing art. They are prefix-search contact sheets, not allowlists:
even `native-retail.png` contains expansion scenes and borders that are blacklisted. An asset's
presence in a sheet, its Retail origin or a broad `ui-frame-*` prefix does not approve it.
Use Blizzard templates and widgets for controls, and verify the actual host use and resolved
member in build `1.60.1.70124`. Prefer set 1 where available; a plain set-0 fallback needs native
host evidence and must not belong to a blacklisted family.
The UI art evidence pin is `1.60.1.70124`; a newer data pin such as `1.60.1.70753` does not permit a speculative art-cache bump. Follow [ui-composition.md](../../../docs/ui-composition.md) for side-rail, top-tab, bottom-tab, frame and icon ownership.
Blizzard-owned content icons may still identify game content, but expansion skins and hand-made chrome are out.

- **All expansion-era UI art, including scenic backgrounds.** `Garr*`, `GarrMission_*`, `ClassHall_*`, `orderhall*`, `covenant*`,
  `soulbinds*`, `warfront*`, `housing*`, `shop-*`, `pvpqueue*`, `pvptalents*`, `dragonriding*`,
  `plunderstorm*`, `eyeofthejailer*`. None of these have a member in the client's Forever art set;
  they are WoD-through-11.x art and read as a different game next to clean client frames.
- **`hud-*` / `UI-HUD-*` as general chrome.** Only inside the HUD system being skinned (action bars,
  cast bar, cooldown manager) — never as a border, divider, panel edge, or decoration.
- **A `-c60`-named member that resolves into a set-0 atlas.** Resolve the element to a set-1 atlas or
  take the plain member; the set-0 c60 members are the trap that made the tooltip centre brown once.
- **Hand-drawn chrome**: borders, fills, gradients, gems, glow rings, crests, stretched corners, 1px
  fills. A missing element is styled by an existing template, not by new art.
- **Loose legacy textures**: `interface/tooltips/ui-tooltip-border.blp` (137057/137056) and any
  pre-NineSlice Backdrop art. Use `Tooltip-NineSlice-*` or the frame's own template.
- **Quest-log parchment and legacy wood/leather chrome.** A quest-log icon can identify its function; the old parchment columns and `legacy*` frame skins are not neutral panel backgrounds.
- **Profession crafting progress bar art.** `Profession-ProgressBar-BG` and `Profession-ProgressBar-frame`
  read as the crafting cast bar wherever they are reused as a generic progress bar. Use a plain
  `StatusBar` filled with `common-stat-bar-white` over `common-stat-bar-BG`, the client's
  `ColoredProgressBarTemplate` art.
- **Gamepad, cursor and crosshair atlases** — input-device art, never window chrome.
- **Fonts that are not FRIZQT or ARIALN.** No Cinzel, EB Garamond, Marcellus or any webfont in a
  window, tooltip, or screenshot; and no hand-picked hex described as "gold".
- **Art from an unpinned or wrong build.** Only `1.60.1.70124`; the cached `1.15.9.70003` is a
  Classic-era client whose UI predates the Forever redesign.
