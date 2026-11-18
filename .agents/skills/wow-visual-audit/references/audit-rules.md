# Visual audit rules

## Manifest rules (`tools/visual_audit.py`, units)

| Rule | Threshold | Why |
|---|---|---|
| Widget inside frame | 0 units of tolerance at half-pixel | the frame is the window; drawing outside it is a bug in any client |
| Widget inside canvas | -8 units | the mock's own margin must never be load-bearing |
| Interactive overlap | no intersection | two clickable things on one another is unusable, and it looks broken |
| Interactive gap | 8 units | matches the tightest spacing the client uses between adjacent buttons |
| Container inset | 8 units | a button flush to a card's edge reads as clipped |

## Pixel rules

| Rule | How it is measured |
|---|---|
| Button art inside the frame | brightest run in the bottom-bar row band vs the frame's detected right edge |
| One piece per button | contiguous red runs across the band |
| Declared size | widest run within 15 percent of the manifest's widest button |
| Declared gap | run-to-run gap at least the manifest gap times the render scale |

The frame is found from the top band of the image: only the window's own chrome is drawn there, so its left and
right extremes are the frame's. That stays true when a control bleeds off the bottom.

## Worth knowing

- Pillow's red mask reads the button caps a few units narrower than the widget rect, because the caps are dim; that is
  why the width rule is 15 percent and not exact.
- The mock backdrop is a radial gradient that tops out around luminance 33, so anything above 62 is UI. Do not raise
  the threshold without re-checking a dark scene.
- An image with no button art in the band is a scene the manifest does not describe - list it in `scenes` or leave it
  out, never let it fail silently.
- `layout.json` is an output of the render, not a source of it: it is regenerated with the images and stamped by
  `scenes.sha256` alongside them.

## Composition evidence

The numeric checks above do not validate native asset relationships. Audit these separately against
Core's `docs/ui-composition.md`:

| Relationship | Required evidence |
| --- | --- |
| Tab to panel | Template orientation, owning panel edge and native attachment; bottom tabs cannot serve as top tabs |
| Image to frame | Complete matching frame, artwork clipped inside its four edges, border rendered above the image |
| Icon to chrome | Native-resolution source, proven crop/mask, exactly one framing owner |
| Side rail to host | Native external anchor and complete hit area recorded, not silently omitted |
| Runtime to render | Same template, crop, anchors, selected state and draw order |

Keep an unverified relationship open. Do not suppress a geometry finding to make a mock pass, or claim
that a fresh render proves the runtime layout is correct.
