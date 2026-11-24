Field Guide Forever gives every creature in WoW: Forever a coat, and the target frame and nameplate show it the moment you see one. Most are bronze, but 1 in 25 spawns is silver, 1 in 100 gold and 1 in 1000 shiny. The journal records the kills it can see, zone by zone. Coats are cosmetic.

Field Guide needs [Questie](https://www.curseforge.com/wow/addons/questie) or the standalone QuestieDB addon for its creature list. Without one, the window says what to install.

Free, with nothing locked behind it. If it saves you time, you can [sponsor me on GitHub](https://github.com/sponsors/cjber), which takes no fees, or [buy me a coffee on Ko-fi](https://ko-fi.com/cjber). For help, [join me on Discord](https://discord.gg/FpHugGxRJY).

[![Join me on Discord](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/discord-button.png)](https://discord.gg/FpHugGxRJY) [![Sponsor me on GitHub](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/github-sponsors-button.png)](https://github.com/sponsors/cjber) [![Support me on Ko-fi](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/kofi-button.png)](https://ko-fi.com/cjber)

**Known limitations**

- Most creatures that die while you are not targeting them and their nameplate is not showing are not counted, so turn on enemy nameplates (default `V`) to record more kills. Rares shown on the minimap are still counted.
- Some creatures in fights and instances cannot be identified and do not count towards the journal.
- When the game hides a creature from addons (in some fights and instances), its rarity cannot be read, so it always shows as bronze.

![Silver, gold and shiny laurels on the target frame, a sheen sweeping the shiny one, and the matching nameplate mark under each](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/screenshots/rarity-nameplates.gif)

A silver, gold or shiny spawn wears a laurel ornament around its target portrait, from a plain silver ring with one oak sprig to a full gold laurel, and on shiny a pearl laurel with a slow light sweeping across it. Its nameplate gets the same mark beyond the client's own left badge and buff row.

![The Field Guide stepping through creatures, instances and the coat filters in several zones](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/screenshots/demo.gif)

Every catalogued zone has its own page of creatures, with your kills and research rank for each. Pick one to see its level, zone and how far you are towards Mastered. The bar at the bottom is the zone's completion.

![The Creatures page filtered to Silver found, with Irradiated Invader selected and its bronze, silver, gold and shiny slots](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/screenshots/variants.png)

Creatures and Instances share the side rail. Silver, gold and shiny are filters, and each entry shows all four coats a spawn can wear.

![The journal entry for a creature whose shiny coat was found, with when it was first and last seen and the best coat found](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/screenshots/shiny-record.png)

Records keep when you first and last saw a creature, how many deaths you recorded and the best coat you have found.

![The game's achievement toast announcing a Shiny Nightsaber](https://raw.githubusercontent.com/cjber/field-guide-forever/main/docs/screenshots/discovery-toast-shiny.png)

Your first silver, gold or shiny of a species, a species reaching Mastered and a zone with every creature recorded each get the game's achievement toast. Click one to open the journal there. Toasts appear above the action bars. Choose Move toasts in the options to drag them elsewhere, or right-click the sample to reset their position.

These images are generated previews of the Field Guide UI.

## Features

- **Rarity marks.** A silver, gold or shiny spawn wears a laurel around its target portrait and the same mark beyond the client's own left badge and buff row on its nameplate, and silver and shiny keep the game's rare silver frame. Health bars, names, the game's own rare, elite and boss art, and every bronze creature look exactly as they always did.
- **The coat ladder.** Every spawn is bronze, silver (1 in 25), gold (1 in 100) or shiny (1 in 1000), fixed for that spawn and the same for every player who sees it. The journal keeps how many of each you have found.
- **Journal.** Creatures across outdoor zones, dungeons and raids, with their level, rank and zone, opening on Discovered so a new character starts with what they have actually met. Search by name, filter by status or coat, and switch between the Creatures and Instances tabs.
- **Research ranks and zone completion.** Kills move a species through Discovered (1), Observed (3), Studied (6) and Mastered (10), and the count keeps going after that. Each zone shows the share of its species you have recorded at any research rank.
- **Records and tracking.** Each creature keeps its first sighting, first kill and best coat per character, with a sighting log for the current session. Track Species puts the one you are working on in the Forever tracker column every Forever addon shares, with its zone, sightings toward Mastered and kills.
- **Discoveries.** A first kill is announced at the top of the screen and tagged New in the journal, and silver, gold, shiny, mastery and zone milestones get the game's achievement toast. Both can be turned off in the options.
- **Instances.** Bosses the game reports when an encounter ends, with first clears, attempts and kills by difficulty. It is a personal record.

## How kills are counted

Field Guide counts the kills it can see: a creature you have targeted, or whose nameplate is showing, dies and nobody outside your group tagged it first. A rare also counts when its map marker, seen alive, turns dead while it is on your minimap. Each death counts once.

A creature that dies with no nameplate showing and not targeted is not counted. Turn on enemy nameplates (`V`) to record more of the creatures you fight.

## Usage

Type `/fg` or `/fieldguide`, or press Shift-F. `/fg preview` shows every creature as silver, gold or shiny for this session and `/fgf help` lists the commands. Options are under Options > AddOns > Field Guide Forever.

For a bug report, paste `/fgf report`.

<!-- forever-credits:start -->

Thanks to Kimab, QuincyO, tgkGate and everyone who reported a bug or asked for a feature.

<!-- forever-credits:end -->

Source code and issues: [github.com/cjber/field-guide-forever](https://github.com/cjber/field-guide-forever). Licence: GPL-3.0-or-later.
