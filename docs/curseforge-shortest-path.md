Hold Shift and click the world map or minimap, or choose *Plan journey* on a quest. Shortest Path Forever shows the route on both maps and lists each step beside the game’s quest tracker.

Free to use. For help, [join me on Discord](https://discord.gg/FpHugGxRJY).

[![Join me on Discord](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/discord-button.png)](https://discord.gg/FpHugGxRJY) [![Sponsor me on GitHub](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/github-sponsors-button.png)](https://github.com/sponsors/cjber) [![Support me on Ko-fi](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/kofi-button.png)](https://ko-fi.com/cjber)

**Known limitations**

- Flight times with Frequent Flier are estimated until players confirm them.
- Walking maps are built ahead of time, so patched terrain can route wrongly until an update.
- The game names your bind point but not where it is, so the Hearthstone counts once you bind or hearth with the addon on.
- A boat, lift or tram shows "no sighting yet" until you have ridden that route once, because the game holds no timetables.
- The game gives no player height, so standing still at a lift's landing right after a ride, the tracker can name the landing you rode from until you step off it.
- The game cannot show another player's spells, so you list a party mage's portals yourself in the settings (Party mage portals).

![A route settling, the departure countdown and compass](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/screenshots/demo.gif)

The route settles, the boat countdown starts and the compass turns with you.

![Journey steps with time and distance remaining](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/screenshots/tracker.png)

The tracker shows each step in order.

![Route and waypoint on the minimap](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/screenshots/minimap.png)

Walking breadcrumbs and the native waypoint guide each step.

![The Nearby services tab in the world map's quest log](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/screenshots/services.png)

Nearby services finds the closest vendor, trainer or inn, and how long it takes to get there.

![Dock destinations and departures](https://raw.githubusercontent.com/cjber/shortest-path-forever/main/docs/screenshots/docks.png)

Hover a dock to see its services and destinations.

These images are generated previews of the Shortest Path UI.

## Features

- **Plan the trip.** Combine walking, known flights, boats, zeppelins, lifts, the tram, portals and teleports. Walks go around walls, hills and water, and replan as you move. A spot inside a dungeon or raid leads to its entrance.
- **Find anything nearby.** The Nearby services tab in the world map's quest log lists vendors by what they sell, your class trainer, profession trainers, battlemasters, portal trainers for mages, inns, banks, auction houses, flight masters, stables and repairs, and every dungeon and raid door on your continent. Each row shows the nearest one and the time to get there, and orders dungeon and raid doors by that time. Search for a service, NPC, item or instance, then click a row to go there; a dungeon row takes you to the door and the journey ends when you go in. Arrows mark that NPC's nameplate when you arrive. Pick a level under *Town services* in the map's filter menu and zone and city maps show the same services where they stand, with one icon for services of the same kind at a spot. A market stall marks a spot shared by different kinds. Click an icon to go there or use the filter menu to choose what appears on the maps. Nearby services needs QuestieDB, and class trainer locations also use Tweaks Forever.
- **Follow your guide.** RestedXP and Guidelime journeys follow the current step by default. When TomTom is absent, other guides’ TomTom waypoints can start journeys too. Turn on *Follow Dugi guides* in Guidance to follow Dugi too, with its own arrow still visible. RestedXP keeps its own arrow. Adventure Guide takes over when its RestedXP display is on.
- **Choose what you see.** Hide Journey steps, the arrow, or all map marks (*Show Shortest Path marks*). With OpenMap on, the route crosses its stitched map into the neighbouring zones. Move and scale the arrow, choose whether its label shows the distance, the time left or both, and add the time left under the compass.
- **Complete a step.** Click the current journey step and choose *Complete this step*. Skipping a Hearthstone leaves it out for that journey; other steps return if you still need them.
- **Travel journal.** Type `/path stats` to see this character’s approximate walking distance, completed journeys and transport use.
- **See departures.** Dock and flight master tooltips show destinations and times.
- **Travel prompts.** Hearthstone and teleport steps show what to cast. A sound and taskbar flash warn before a boat arrives, and an optional ping marks your arrival. A red corpse route guides ghosts back to their bodies.

With the gamepad interface on, you open and turn the world map; Shortest Path won't, and its right-click menus need mouse and keyboard.

## Usage

- `/path` opens settings under **Options → AddOns → Shortest Path Forever**. `/spfnear` opens the Nearby services tab.
- Alt-click the world map to choose a destination over a Questie icon. Shift-click the map, minimap or a Shortest Path icon; for quests, choose **Plan journey** in the right-click menu. **Key to plan a journey** in **Guidance**: Shift or Alt.
- In **Map marks**, scale each kind of icon, and choose whether journey stops hide the game's quest markers. Right-click a flight master icon to mark its path known or unknown.
- In **Interface**, choose what shows, metres, sizes and a compass background. While moving the arrow or compass, Shift-drag or use the arrow keys for fine placement.
- The shared Forever column sits left of the game's quest tracker. Drag a heading to move it; right-click a heading for **Lock the tracker** to stop dragging. **Resume guide** returns to RestedXP, Guidelime or Dugi Guides; your journey survives a reload.
- `/way [zone] x y [title]` plans a journey, or `/path way` when another addon owns `/way`. **Follow TomTom's arrow** in Guidance follows TomTom.

For a bug report, use `/path report`. For a GitHub issue link, use `/path issue`.

Translated into German, French, Spanish, Brazilian Portuguese, Russian, Korean and Chinese (machine translated; corrections welcome through the [translation form](https://github.com/cjber/shortest-path-forever/issues/new?template=translation.yml)).

Installed together, the others send Shortest Path their destinations. Pick an Adventure Guide journey, one of its suggestions in a quest menu or a RestedXP, Guidelime or Dugi Guides step, or click a trainer or vendor in a SkillUp route to travel to the nearest one. Click a Legacy dungeon or raid pin, or a dungeon or raid entrance Tweaks adds to the map, to travel there. Journey steps share one tracker column with the Adventure Guide, SkillUp and Legacy sections, beside the game's quest tracker.

Capital trails come from Fitz's [Polestar](https://github.com/fitzforge/polestar), used with permission.

<!-- forever-credits:start -->

Thanks to Alex21xx, Maggew, MacieGx, Stiandresius, alexaroth, Chulf58, user_lsqt69ps7bgb5p7e, The___Fast, Joster91, GenericP, cotijelucie, vladsnz, user_sggieekz05hc7uxt, kindguydev, ubrider, Drusangus, Nedula, icouldonlygetthisname, user_u3k9hweaatfhnjs0, treadpool, user_g496wu46adiwjuc5, emmiehbun, VolomonBeddarm, zhega, catubba, Hatemost, JaidyEU, embiem, InfamousMunky, A player, kaelr1, Enel3008, azure463, AsimRamay, nookie909, Zerhathos, jakerist, cobalt_44, Xeteskian, DaFrozenMage, user_zbqhuuoypkkr46x1, Fitz, TRDeadbeat, tallsmartman, Sol_Deus, Zavian, Osipanda, Nightwind416, wfournier, cidolfus27, o0saw0o, Merlinqt, team_Brigade, phear, Testvonfarkle, rydoc, deathmvp1, saikoso, Ragnarok11B, Brainc3ll, Mouchoir, z1ck, Oxds, sean16981, aryaxo, Exo_NA, legortiz, JohnChrin, wheelbarrel00, lkshrk, HeartOfD2, rml9ty, hwalflor, chris-chrysos, Quantity-4, Bolton_wow, Aldericdevir, joaocjesus, jakerist (Grayburn), borick7318, sampconrad, jixxor, Gaafah, _spada, macwire, scraak, overspark, TeeRKee, Speaker1264, SuubzTV, Fel7, Kragmars, spidersylar, Acem, tgkGate, user_efwsfml273dlvfm5, IronmanBG, vcatalin, sdtom, Bervath, Blast22, hervad, caghanpekin-prog, Zwaffelmagic, CptShooter, user_10oietw0rdrgk4le, cwebbx, lone_viking1921, Nivlemoth_Nathrezim, Lůca [Luutsa], esc_return, MrOxiMoron, Zhiroc, Crypa7, ghuff07, nimri82, cmartin303, lukehmu and everyone who reported a bug or asked for a feature.

<!-- forever-credits:end -->

Source code and issues on [github.com/cjber/shortest-path-forever](https://github.com/cjber/shortest-path-forever). Licence: GPL-3.0-or-later.
