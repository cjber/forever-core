-- Native Friends, mail and denomination setup with no addon or an optional full SkillUp checkout.
-- Full combined inventory still has the separate, unresolved CurrencyTransfer SetNumber callback timing gap.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local skillup = os.getenv("FOREVER_SIM_SKILLUP")
local core = os.getenv("FOREVER_CORE")
local selected = os.getenv("FOREVER_SIM_SETUP_CONTROL")
local controls = selected and { selected == "1" } or (skillup and { true, false } or { true })
for _, control in ipairs(controls) do
	local sim = Sim.new()
	if not control then
		assert(core, "FOREVER_CORE is required with FOREVER_SIM_SKILLUP")
		sim:addon(core, "ForeverCore")
		sim:addon(skillup, "SkillUpForever")
	end
	sim:expectNoErrors()
	local G = sim.G
	sim:login()
	if control then
		assert(#sim.loader.addons == 0, "control loads no addon")
	else
		assert(G.C_AddOns.IsAddOnLoaded("SkillUpForever"), "full SkillUp fixture loaded")
		assert(G.C_AddOns.IsAddOnLoaded("ForeverCore"), "full Core fixture loaded")
	end
	sim:loadBlizzard("Blizzard_UIPanels_Game:Bank|TradeFrame")
	sim:loadBlizzard("Blizzard_MailFrame")
	sim:loadBlizzard("Blizzard_FrameXML/Mainline/StackSplitFrame.lua")
	sim:loadBlizzard("Blizzard_FrameXML/Camelot/StackSplitFrame.xml")

	sim:expectNoErrors()
	assert(G.BNFeaturesEnabled() == false)
	assert(G.BNConnected() == false)
	local presence, tag, toon, broadcast, afk, dnd, realID = G.BNGetInfo()
	assert(presence == nil and tag == nil and toon == nil and broadcast == "")
	assert(afk == false and dnd == false and realID == false)
	sim.world.battleNet.afk = true
	assert(select(5, G.BNGetInfo()) == true)
	sim.world.battleNet.afk = false
	sim.world.mail.sendPrice = 60
	assert(G.GetSendMailPrice() == 60)
	sim.world.mail.sendPrice = 30
	-- Native MoneyDisplayFrame XML must preserve the actual denomination tables by identity.
	do
		local frame = G.CreateFrame("Frame", nil, G.UIParent, "MoneyDisplayFrameTemplate")
		assert(frame.GoldDisplay.displayType == G.MoneyDenominationDisplayType.Gold)
		assert(frame.SilverDisplay.displayType == G.MoneyDenominationDisplayType.Silver)
		assert(frame.CopperDisplay.displayType == G.MoneyDenominationDisplayType.Copper)
	end
	sim:expectNoErrors()
	assert(type(G.SocialUIScrollableElementExtentPreviewerMixin.OnLoad) == "function")
	assert(G.FriendsFriendsFrame.TemplateRegistrations ~= nil)
	assert(G.FriendsFriendsFrame.TemplateExtentCache ~= nil)
	print("native_setup_spec: " .. (control and "zero addons" or "SkillUp and ForeverCore") .. " passed")
end
