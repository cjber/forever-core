# Forever addons: final report (2026-10-16)

## Releases now live (GitHub, Wago and CurseForge, all approved)
| Addon | Live | Shipped today |
|---|---|---|
| Shortest Path Forever | **1.19.0** | 1.17.0 → 1.18.0 (Forever addons page, hints, Adventure Guide suggestions in quest menus, credits) → 1.19.0 (9 languages, reagent vendors in any language) |
| Adventure Guide Forever | **0.16.0** | 0.14.0/0.14.1 (mob-level weighting, Next spot) → 0.15.0 (Forever addons page, quieter hints, suggestions API, credits) → 0.16.0 (9 languages; the name stays "Adventure Guide") |
| SkillUp Forever | **0.15.0** | 0.12.0/0.13.0 (auction-house reagents for N crafts) → 0.14.0 (Forever addons page, hints, credits) → 0.15.0 (9 languages) |
| Legacy Forever | **0.9.0** | 0.7.1 → 0.8.0 (Forever addons page, Adventure Guide zone hint, credits) → 0.9.0 (9 languages; French is Brainc3ll's plus marked machine lines) |
| Tweaks Forever | **0.14.0** | 0.12.1 → 0.13.0 (OpenMap step-aside, Forever addons page, credits) → 0.13.1 (Mouchoir's login-error fix, #202) → 0.14.0 (9 languages) |

Languages: German, French, Spanish (Spain and Latin America), Brazilian Portuguese, Russian, Korean, and Simplified and Traditional Chinese. There's no Italian, because the Forever client has none. All are machine translated and labelled as such, using the game's own terms. The shared strings are identical across the five addons.

## Visibility plan: done
- **"The Forever addons" table** in every README and store description, with a CI check that it never drifts.
- **Forever addons settings page** in every addon (shared module, VERSION 3), with *Suggest my other Forever addons*, on by default.
- **Hints only where they help:**
  - SPF: the quest-menu entry, the "What next?" footer and the Legacy line on dungeon stops.
  - SkillUp: the travel-time line and the Artisan quest-chain line.
  - Legacy: the zone-completion Adventure Guide line.
  - Tweaks: the dungeon-entrance line.
  - AGF: route, profession and dungeon hints.
- **SPF's quest menu** shows Adventure Guide's top suggestions.
- **Adventure Guide's summary** leads with the Shortest Path pairing, and the map is its first image.
- **Your GitHub profile** lists all five with CurseForge links.

## Credits and licences: done
- No licence problems in any shipped zip.
- AGF's QuestieDB-derived test data is no longer committed.
- Every README has a Credits section, naming about 30 players plus Polestar (inspiration only; Fitz may use our code), Forever Loot Sparkles and Brainc3ll.
- New standing rule: every fix or feature credits whoever reported or asked for it.

## Tooling (cjber/skills, synced into all five)
- The family-block check.
- A stricter package check: exact licence names, required credits.
- `check_locales`, which guards placeholders, escapes and TOC wiring.
- A release step to translate new phrases before every release.

## Comments and issues
- **CurseForge:** every comment is handled. One new request came in tonight, a tracker background option (AGF, anonymous), now tracked as AGF #203 for the shared tracker.
- **GitHub:** Tweaks #202 is fixed and released.
- **Still open:**
  - SPF #158, #159, #161 and #188: in-game checks.
  - SPF #194: OpenMap; the Tweaks side is done, SPF needs in-game checks.
  - SPF #103: tooling tracking.
  - AGF #166: login-time measurement.
  - AGF #203: tracker background.
  - SkillUp #124: trainer visits.
  - Tweaks #168: gamepad A/B.
  - Tweaks #210: camp benefit names in English.

## Suggested next round
1. AGF #203: the tracker background, in the shared TrackerHost.
2. Tweaks #210: translated camp benefits, via a generator change.
3. Anything your in-game checks turn up.
