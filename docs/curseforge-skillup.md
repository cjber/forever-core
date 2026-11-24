SkillUp Forever shows skill-up chances, recipe costs and colour thresholds in the Professions window. Its side panel has levelling routes, shopping lists, crafted gear and the buffs each profession makes.

Free, with nothing locked behind it. If it saves you time, you can [sponsor me on GitHub](https://github.com/sponsors/cjber), which takes no fees, or [buy me a coffee on Ko-fi](https://ko-fi.com/cjber). For help, [join me on Discord](https://discord.gg/FpHugGxRJY).

[![Join me on Discord](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/discord-button.png)](https://discord.gg/FpHugGxRJY) [![Sponsor me on GitHub](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/github-sponsors-button.png)](https://github.com/sponsors/cjber) [![Support me on Ko-fi](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/kofi-button.png)](https://ko-fi.com/cjber)

**Known limitations**

- Recipe colours come from the game, but a recipe you have not seen yet uses bundled thresholds that can be slightly off.
- Trainer fees, requirements and drop chances come from Classic databases, as the game lists none until you visit.
- Gathering nodes and corpses have no colour in the game, so theirs is an estimate.
- Prices need an auction scan or a price addon; until then, steps show a price unknown.
- Working Overtime's bonus (4% per rank, 20% at 5/5) may be added points or a multiplier, so its estimate is off by default.
- Two tracked professions that share reagents can count the same bag items twice in the shopping list.

![Leatherworking levelling from 48 to 60](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/screenshots/demo.gif)

From 48 to 60 the rows re-sort by cost per skill-up, and the bracers turn green at 55.

![Recipe tooltip with thresholds, reagent prices and cost per skill-up](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/screenshots/tooltip.png)

Colour thresholds and reagent prices for the recipe you hover.

![The SkillUp route tab with training and crafting steps and the reagents they need](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/screenshots/route.png)

The route tab from 48 to 73: what to train, craft and buy.

![A Leatherworking trainer's recipes with skill-up chance, cost and a green arrow on the one that best helps the route](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/screenshots/trainer.png)

At the trainer, a green arrow marks the recipe that best extends or cheapens your route.

![The Crafted gear tab: item slots around the edge with the newest crafted item, and one slot's recipe, reagents and status](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/screenshots/gear.png)

The gear tab, turned on in settings: the newest craftable item for each slot.

![The Buffs tab: the Cooking buff timeline by skill, its rank divider and legend, and the selected buff's words and reagents](https://raw.githubusercontent.com/cjber/skillup-forever/main/docs/screenshots/buffs.png)

The buffs tab: what each profession can make for your level, in columns on a skill timeline.

These images are generated previews of the SkillUp UI.

## Features

- **Recipe rows and tooltips.** Each recipe shows its skill-up chance, cost and colour thresholds, in the row and in its tooltip.
- **A sortable recipe list.** See how many your bags can make after each name. Sort by difficulty range start, chance, cheapest skill-ups, highest craft profit or newest learned first.
- **Unlearned recipes.** A setting, off by default, lists them greyed under the learned ones, each marked with its trainer or recipe item and the skill it asks, sorted by required skill or newest first. Search by name or use *Has skill up* to narrow the list. Select an unlearned recipe to preview its reagents and cost.
- **Buffs only.** Filter recipes to buffs you can use at your level.
- **Levelling routes.** Crafts, trainer visits, skill books and rank quests to your target skill, in the order you craft them, with fees, tools and stations. Cheaper crafted reagents become their own steps, Craft next makes missing intermediates first, and right-clicking a recipe and choosing *Not this recipe* plans without it.
- **Shopping lists.** Reagents are counted against bags and bank. Buying is the default, so materials your professions gather are bought unless you choose to gather them; track the list beside quests, buy vendor stock and keep an Auctionator list up to date. At the auction house, click *Search* in Professions for missing reagents.
- **Trainers, reagents and gathering.** Trainers mark the best recipe to train next. Reagent tooltips, enabled in settings, show what tracked routes need; hold Shift for every recipe that uses the item, and each line names its profession. Herb and ore nodes show the skill they need, coloured at yours.
- **Crafted gear and buffs.** The gear tab, enabled in settings, shows the newest craft for each slot with its recipe, reagents and learning location. The buffs tab shows what each profession can make for your level on a skill timeline.

## Prices

Each reagent uses the cheapest known vendor or auction price; visiting a vendor records its prices and reputation discounts. *Value gathered materials at what they'd sell for* is on for new installs and costs them at their sale value; turn it off to count them as free. *Price self-supplied reagents at auction values* prices whatever you gather, loot or already own at its market value, and leaves it unpriced rather than free when there is none.

Auction prices come from Auctionator, TradeSkillMaster's AuctionDB, AHDB, Naowh Forever's scans and nightly snapshot, or Forever Ledger's own scans. Naowh can price materials before your first auction house visit. *Auction prices from* picks the source; the others fill gaps.

A craft's vendor sell value comes off its cost, or its auction value after the 5% cut if you choose. With TradeSkillMaster and its desktop app, *Region sale average if higher* values the craft from regional sales instead, with the vendor price as a floor. Profit shows a green `+`.

## Usage

Open a profession and the numbers are already there.

- `/skillup` opens the settings (also in Settings > AddOns and the addon compartment).
- `/skillup skipped` lists the recipes you said *Not this recipe* to, and `/skillup unskip <ID>` (or `all`) brings them back.
- `/skillup audit`, with a profession open, prints where the bundled thresholds differ from the colours the game shows.
- `/skillup trainers` lists the trainer skill requirements SkillUp guessed and which ones a trainer has confirmed.

Settings cover tooltips, recipe rows, prices, tabs, trainers and sorting. Crafted gear and reagent tooltips start off, each one setting away.

For a bug report, paste `/skillup report`.

Translated into German, French, Spanish, Brazilian Portuguese, Russian, Korean and Chinese (machine translated; corrections welcome through the [translation form](https://github.com/cjber/skillup-forever/issues/new?template=translation.yml)).

With [Shortest Path Forever](https://www.curseforge.com/wow/addons/shortest-path-forever), clicking a trainer or vendor in the route plans the trip there, and SkillUp picks the nearest one by travel time. [Adventure Guide Forever](https://www.curseforge.com/wow/addons/adventure-guide-forever) shows each profession's next steps in its Professions tab. A tracked route shares one tracker column with the Shortest Path, Adventure Guide and Legacy Forever sections, beside the game's quest tracker.

<!-- forever-credits:start -->

Thanks to kopuliak, bromidious, Mouchoir, Chuujitsuna, st3nlee, davef1n, sundered1985, trias6657, iPulse, cotijelucie, prokn4h, CtrlDKhayos, AlteredIgor, Benjy_Boi, DemDragons, user_nd8yffdjkebopqym, vulpeep, messajahswe, user_bvgv4fnauhmhf9i7, puschie286, Belth, yavinn, cursebandit, rissole, codipherus, jugg__, keerp, yusufdanis, Diamondclaw, mimmordino, soviman1, Yivry, luna, FreakinNerd, nookie909, vladdoubrov, _spada, SanyaBane, Rambomst, fusionley, ItachiGrave, .phear, Brainc3ll, berserkerlxl, SilentGentlemanSG, BallaRa, kurila11478, Bolthorr, TechnoHunter, Viper2042, Syrberus, zazomazzo, Setuaro, 0xTrk, 3kinex, icouldonlygetthisname, jakeyjake07, Rekalicious, leenagil-coder, Weythx, lokitako, Rawveggie, hardliquor, CodexFD, rockhumper84, Kozoaku, turkeyfire69, Kirdan, rick1tz, time2w8, ThePNAG, derzwiebelritter, Ekallo, CorvidofShadows13, Sogu, achubbert, jackthereaper_, qwertzyxc, Da_Tronic, shenhyrosame, davefin and everyone who reported a bug or asked for a feature.

<!-- forever-credits:end -->

Source code and issues: [github.com/cjber/skillup-forever](https://github.com/cjber/skillup-forever). Licence: GPL-3.0-or-later.
