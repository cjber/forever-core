# Native UI composition

This is the suite's composition contract for journal, map, portrait and detail panels. Read it with the [Retail UI style skill](../.agents/skills/wow-retail-ui-style/SKILL.md) and [asset registry](asset-registry.md). It describes relationships between native surfaces, not a new skin.

## One lockup before implementation

Approve one complete panel lockup before building individual widgets. It must show the native outer frame, portrait or map surface, side rail, detail tabs, content inset, icons and labels. Validate short, long and empty states in implementation renders after the owner approves the direction. An AI concept communicates direction, but it does not prove an atlas, template, crop or draw layer is valid.

## Edge ownership

- The outer frame owns its portrait or map border. Use the native portrait or map frame and keep subject artwork inside its clip. Zone art is content art, not a replacement for the host frame or a global marble background.
- `LargeSideTabButtonTemplate` owns the outer right rail. Anchor the rail to the host edge, as Adventure Guide and SkillUp do. Do not move a panel tab to that edge.
- `PanelTabButtonTemplate` is a panel-bottom control. It belongs on the bottom edge of the panel it switches, with the panel content above it.
- Native panel-top tabs can use `PanelTopTabButtonTemplate`, whose mixin crops and anchors the panel-tab art for the upper edge. Macro UI and Wardrobe use it. Do not substitute the bottom-facing base template.
- TabSystem top-facing tabs use `TabSystemTopButtonTemplate` through `TabSystemTemplate` so `AddTab` calls `TabSystemButtonMixin:Init` and `HandleRotation`. For a custom art-only tab, set `isTabOnTop=true` and call `HandleRotation()` explicitly, as the `isTabOnTop` key in `Blizzard_ProfessionsCrafterOrderPage.xml` and the explicit rotation call in its Lua companion do. The flag alone does not rotate the art. `Blizzard_SharedXML/Shared/TabSystem/TabSystemTemplates.xml` and its Lua companion are the source evidence. Moving a `PanelTabButtonTemplate` upward is still the wrong control.
- A content icon has one chrome owner. Inspect the source first: preserve a baked bevel, or apply the proven host frame once. Crop only proven bounds, preserve aspect, and reset stale texcoords when reusing a texture. Never put `WhiteIconFrame` around an icon that already contains its own border.
- The Minimap rim owns its buttons. An addon button is a 20-unit frame parented to `Minimap`, centred on an angle outside its edge, with the client's `UI-HUD-Minimap-Button` plate (and `-Down` press state) as its chrome and `bags-roundhighlight` as its hover glow. The plate is the one the client's own `AddonCompartment` and tracking buttons use; do not substitute `MiniMap-TrackingBorder` or another loose pre-Legion ring.
- Artwork and frame are separate responsibilities. A location image is clipped by the inset frame, a creature portrait is masked by its portrait frame, and text uses semantic client font colours. Do not use artwork as a border or a border as artwork.

## Evidence record

Record this table before implementation and beside every exact-asset mockup or composition review. An AI direction proposal may mark these fields unresolved; it cannot approve them:

| Source or template | Attachment edge | Atlas or file | Set | Texcoords | Border owner | Draw layer |
| --- | --- | --- | --- | --- | --- | --- |
| `PortraitFrameTemplate` or native map frame | outer host edge | resolved native layout | 1 when available | native mask | template | template layers |
| `LargeSideTabButtonTemplate` | outer right rail | resolved side-tab atlas | 1 when available | native | template | template layers |
| `TabSystemTopButtonTemplate` with native initialization | associated panel top | TabSystem atlas | 1 when available | native | template | native tab layers |
| `PanelTabButtonTemplate` | associated panel bottom | panel-tab atlas | 1 when available | native | template | native tab layers |
| `InsetFrameTemplate` | content inset | NineSlice layout | 1 when available | artwork clipped inside | frame | border above artwork |
| inspected content icon | content box | subject file or atlas | resolved | proven crop only | exactly one owner | artwork, then one frame |

The inspected FrameXML extract is [1.60.1.69913 at `70ef1b2`](https://github.com/Gethe/wow-ui-source/blob/70ef1b2fd78061a73f886c4a1e79dc5b5cff6d5e/version.txt). [TabSystem templates](https://github.com/Gethe/wow-ui-source/blob/70ef1b2fd78061a73f886c4a1e79dc5b5cff6d5e/Interface/AddOns/Blizzard_SharedXML/Shared/TabSystem/TabSystemTemplates.xml) and [panel templates](https://github.com/Gethe/wow-ui-source/blob/70ef1b2fd78061a73f886c4a1e79dc5b5cff6d5e/Interface/AddOns/Blizzard_SharedXML/Mainline/SharedUIPanelTemplates.xml) are reproducible upstream evidence. This older source extract supports discovery; confirm the selected template behavior in the target client build before approving implementation. The separate UI art evidence pin remains `1.60.1.70124`. A generated data refresh may name `1.60.1.70753`, but that does not change the art pin or justify a speculative cache bump.

## Full sweep

When auditing an existing addon, inspect every frame and renderer path for the same edge, chrome and crop rules. Compare against SkillUp's profession host and Adventure Guide's quest map, then update the whole lockup together. Standalone bottom tabs are valid when attached to their panel's bottom edge, as in Hoard and Tweaks. Window type alone never establishes a valid attachment.
