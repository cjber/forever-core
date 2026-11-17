-- Native load-on-demand initialization must not inherit the addon that requested it.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new()
sim:login()
sim:runAs(
	"LoadContextProbe",
	[=[
    assert(not issecure())
    assert(C_AddOns.LoadAddOn("Blizzard_Professions"))
    assert(not issecure(), "native loading must restore the insecure caller")
    LoadContextAfter = {}
    LoadContextAfter.writer = true
]=]
)
sim:expectNoErrors()
assert(sim.taint.slotInfo(sim.G.LoadContextAfter, "writer").addon == "LoadContextProbe")
local flyout
for i = 1, 100 do
	local name, value = debug.getupvalue(sim.G.IsProfessionsItemFlyoutOpen, i)
	if not name then
		break
	end
	if name == "flyout" then
		flyout = value
	end
end
assert(flyout, "actual native singleton exists")
for _, frame in ipairs({ flyout, sim.G.ProfessionsFrame.CraftingPage.CraftingOutputLog }) do
	for _, key in ipairs({ "callbackTables", "executingEvents", "deferredCallbacks" }) do
		assert(frame[key], "native registry initialized: " .. key)
		assert(not sim.taint.slotInfo(frame, key), "native initialization inherited caller taint into " .. key)
	end
end
-- The same loader must retain addon ownership for addon XML and its virtual OnLoad.
sim.taint.registerAddon("TemplateContextProbe", "TemplateContextProbe")
sim.taint.dispatch("TemplateContextProbe", function()
	assert(sim.templates.loadXML(here .. "template_context.xml", "TemplateContextProbe", "template_context.xml"))
end)
sim:runAs(
	"TemplateContextProbe",
	[=[
    TemplateContextFrame = CreateFrame("Frame", nil, nil, "AddonContextTemplate")
]=]
)
sim:expectNoErrors()
assert(sim.taint.slotInfo(sim.G.TemplateContextFrame, "initialized").addon == "TemplateContextProbe")
print("load_context_spec: native loading, caller restoration and addon template ownership passed")
