---
name: wow-retail-ui-style
description: "Build and review World of Warcraft Retail addon interfaces that fit Blizzard's current UI. Use when creating, changing, or auditing Retail UI frames, widgets, layouts, textures, fonts, or interaction behavior."
---

# WoW Retail UI Style

Apply these rules when making WoW Retail addon UI. Prefer Blizzard's current interface conventions and APIs, and inspect the target client/build when an API or visual detail may have changed.

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

1. Identify the target Retail build and the nearest Blizzard frame or widget that owns the interaction.
2. Inspect its current template, mixin, atlas, and API before choosing custom implementation details.
3. Build the smallest addon-specific layer on top of those conventions and cover the applicable states from the rules above.
4. Review it in the target client, then fix any visual, input, localization, scaling, or protected-frame issues found.

## Never use (blacklist)

The inventory behind these bans, with the build counts that justify each one, is
`docs/asset-registry.md`. For addon chrome, use only the vetted modern set shown in
`docs/asset-audit/native-retail.png` (build `1.60.1.70124`); use Blizzard templates and widgets for controls.
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
- **Gamepad, cursor and crosshair atlases** — input-device art, never window chrome.
- **Fonts that are not FRIZQT or ARIALN.** No Cinzel, EB Garamond, Marcellus or any webfont in a
  window, tooltip, or screenshot; and no hand-picked hex described as "gold".
- **Art from an unpinned or wrong build.** Only `1.60.1.70124`; the cached `1.15.9.70003` is a
  Classic-era client whose UI predates the Forever redesign.
