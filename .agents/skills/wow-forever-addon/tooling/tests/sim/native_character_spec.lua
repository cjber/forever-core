-- #714: selected startup panels must complete their own and their gamepad setup without unattributed errors.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new({ addon = false })
local G = sim.G
sim:login()
assert(G.PaperDollFrame.ItemsFrame, "paper doll loaded from the native XML")
assert(G.C_AddOns.IsAddOnLoaded("Blizzard_UIPanels_Game"), "selected TOC completes its addon lifecycle")
assert(select("#", G.C_QuestLog.GetZoneStoryInfo(1454)) == 0, "no invented zone story achievement")
for _, gamepad in ipairs({ false, true, false }) do
	sim:setGamepad(gamepad)
	sim:openCharacter()
	sim:advance(0.1)
	if gamepad then
		assert(G.PaperDollFrame.CharacterViewerFooter, "character viewer footer initialized")
		assert(G.CharacterFrame.leftFooter and G.CharacterFrame.rightFooter, "gamepad footers initialized")
	end
	sim:closeCharacter()
	sim:openWorldMap()
	sim:closeWorldMap()
	sim:expectNoErrors()
end
print("native_character_spec: passed")
