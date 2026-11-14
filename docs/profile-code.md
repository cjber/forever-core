# The Forever profile code

`/forever profile` shows one line for this character: a link to a card on [wow.cjber.dev](https://wow.cjber.dev/p/)
that anyone holding the link can open. The code is inside the `#` fragment, so the browser decodes it and the server
never sees it. The addon sends nothing, saves nothing new and has no account: copying the link out of the game is the
only way it leaves the client, and sharing the link is sharing the card.

Write the code with [Core/ProfileCode.lua](../Core/ProfileCode.lua), read a card with
[`site/p/index.html`](https://github.com/cjber/wow.cjber.dev/blob/main/site/p/index.html), and see
[`profile-code-example.txt`](profile-code-example.txt) for one.

## Format, version 1

```
1.<base64url>
```

The code opens with its version and a dot, so a reader can refuse a version it does not know instead of guessing.

The rest is [base64url](https://datatracker.ietf.org/doc/html/rfc4648#section-5), with `-` and `_` in place of `+`
and `/` and no `=` padding, of a compact UTF-8 JSON object. Fields in the order the writer emits them:

| Key | Type | Meaning |
|---|---|---|
| `n` | string | The character's name, as `UnitName("player")` reads it. |
| `c` | string | The class file token, such as `HUNTER`, as `UnitClass` reads it. |
| `l` | number | The level, as `UnitLevel` reads it. |
| `f` | string | `Alliance`, `Horde` or `Neutral`, as `UnitFactionGroup` reads it. |
| `t` | number | The unix time in seconds the code was made, as `GetServerTime` reads it. |
| `s` | object | One object per addon present, keyed by its short key below. |

An addon's object maps each metric its own `API.Stats()` returned to one number. A metric reported once per subject
(one row per flight path, say) is summed across its subjects, so the card shows totals rather than a list. A missing
addon, an addon that has not published its API, and an addon whose read returns nothing are simply absent. Every
number is a non-negative whole number; a missing or broken value is written as `0`.

The JSON has no spaces, and its keys are sorted, so the same record always makes the same code. A fully populated
record, with every metric below and a nine-digit value in each, is well under the 2 KB browsers handle in a URL;
`tests/profile_code_spec.lua` holds that bound.

Nothing in the code is signed or encrypted. Any key inside an addon is readable, so a faked card only fools the
person who made it; the page is a profile, not a ranking.

## Addon short keys

| Key | Addon | API the code reads |
|---|---|---|
| `adv` | AdventureGuideForever | `API.Stats()` |
| `spf` | ShortestPathForever | `API.Stats()` |
| `skl` | SkillUpForever | `API.Stats()` |
| `leg` | LegacyForever | `API.Stats()` |
| `com` | CommissionsForever | `API.Stats()` |
| `fgd` | FieldGuideForever | `API.Stats()` |

## Stat keys and units

Every key is the metric name the addon's own `API.Stats()` rows carry, never a label the card draws, so the code
keeps meaning if a label changes.

| Key | Unit | What it counts |
|---|---|---|
| `adv.quest_turn_ins` | quests | Quests turned in, the aggregate row. |
| `adv.quest_turn_in` | quests | The same turn-ins summed from the addon's one row per quest. |
| `spf.distance_yards` | yards | Distance travelled. |
| `spf.routes_completed` | journeys | Journeys completed. |
| `spf.transports_used` | transports | Boats, zeppelins, trams and the like. |
| `spf.flights_taken` | flights | Taxi flights taken. |
| `spf.portals_used` | portals | Portals taken. |
| `skl.recipes_observed_learned` | recipes | Recipes learned. |
| `leg.flight_path_known` | flight paths | Flight paths known, summed over nodes. |
| `com.commission_turnin` | commissions | Commissions turned in. |
| `fgd.creature_kills` | kills | Creatures killed. |
| `fgd.bronze_finds` | creatures | Bronze finds. |
| `fgd.silver_finds` | creatures | Silver finds. |
| `fgd.gold_finds` | creatures | Gold finds. |
| `fgd.shiny_finds` | creatures | Shiny finds. |
| `fgd.first_sighting` | creatures | First sightings. |
| `fgd.first_kill` | creatures | First kills. |
| `fgd.first_bronze` | creatures | First bronze finds. |
| `fgd.first_silver` | creatures | First silver finds. |
| `fgd.first_gold` | creatures | First gold finds. |
| `fgd.first_shiny` | creatures | First shiny finds. |
| `fgd.boss_sightings` | bosses | Boss sightings. |
| `fgd.boss_kills` | bosses | Boss kills. |
| `fgd.boss_first_sighting` | bosses | Boss first sightings. |
| `fgd.boss_first_kill` | bosses | Boss first kills. |

`adv.quest_turn_in` is the same total as `adv.quest_turn_ins`, read from the addon's one row per quest rather than its
aggregate row. A card shows the number once, under the aggregate, and leaves the per-quest copy out of the drawing.

## A new version

A version that changes the record or its meaning takes the next number and a new section here. A reader shows the
newest version it knows and, for any other, names the version it found and asks for a newer page. It never guesses at
a record it does not understand.
