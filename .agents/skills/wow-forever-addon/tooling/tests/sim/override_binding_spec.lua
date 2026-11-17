-- Override ownership, simulator ordering, hardware CLICK dispatch and combat refusal.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new({ addon = false })
local G = sim.G
local a, b = G.CreateFrame("Frame"), G.CreateFrame("Frame")
local button = G.CreateFrame("Button", "SimBindingButton")
local clicks = 0
button:SetScript("OnClick", function(_, mouseButton)
	assert(mouseButton == "RightButton")
	assert(sim.hardwareInput, "binding click is hardware input")
	clicks = clicks + 1
end)
G.SetOverrideBinding(a, false, "PAD1", "JUMP")
assert(G.GetBindingAction("PAD1", true) == "JUMP", "override recorded")
assert(G.GetBindingAction("PAD1", false) == "", "overrides are opt-in")
G.SetOverrideBindingClick(b, true, "PAD1", "SimBindingButton", "RightButton")
assert(G.GetBindingAction("PAD1", true) == "CLICK SimBindingButton:RightButton")
G.SetOverrideBinding(a, false, "PAD1", "MOVEFORWARD")
assert(G.GetBindingAction("PAD1", true) == "CLICK SimBindingButton:RightButton", "priority wins")
sim:pressBinding("PAD1")
assert(clicks == 1, "bound button dispatched")
G.ClearOverrideBindings(a)
assert(G.GetBindingAction("PAD1", true) == "CLICK SimBindingButton:RightButton", "other owner preserved")
G.ClearOverrideBindings(b)
assert(G.GetBindingAction("PAD1", true) == "")
for _, priority in ipairs({ false, true }) do
	G.SetOverrideBinding(a, priority, "PAD1", "JUMP")
	G.SetOverrideBinding(b, priority, "PAD1", "MOVEFORWARD")
	assert(G.GetBindingAction("PAD1", true) == "MOVEFORWARD", "latest in same priority class wins")
	G.SetOverrideBinding(b, priority, "PAD1", nil)
	assert(G.GetBindingAction("PAD1", true) == "JUMP", "nil action clears owner's key")
	G.ClearOverrideBindings(a)
end
sim:runAs(
	"BindingProbe",
	[[
 BindingOwner = CreateFrame("Frame")
 SetOverrideBinding(BindingOwner, false, "PAD2", "JUMP")
]]
)
assert(G.GetBindingAction("PAD2", true) == "JUMP", "insecure calls allowed outside combat")
sim:enterCombat()
for _, code in ipairs({
	'SetOverrideBinding(BindingOwner, true, "PAD2", "MOVEFORWARD")',
	'SetOverrideBindingClick(BindingOwner, true, "PAD2", "SimBindingButton", "RightButton")',
	"ClearOverrideBindings(BindingOwner)",
}) do
	local before = #sim.actions
	sim:runAs("BindingProbe", code)
	assert(#sim.actions == before + 1, "insecure combat mutation refused")
	assert(sim.actions[#sim.actions].event == "ADDON_ACTION_BLOCKED")
	assert(G.GetBindingAction("PAD2", true) == "JUMP", "refused mutation preserves bindings")
	sim:takeErrors()
end
sim:input(function()
	G.SetOverrideBindingClick(b, true, "PAD2", "SimBindingButton", "RightButton")
end)
sim:pressBinding("PAD2")
assert(clicks == 2, "secure combat dispatch allowed")
sim:leaveCombat()
G.ClearOverrideBindings(b)
sim:expectNoErrors()
print("override_binding_spec: passed")
