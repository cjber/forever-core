-- luacheck: read globals scenario ADDON
scenario("native settings section registers from real Core", function(sim)
	sim.impl["C_SettingsUtil.OpenSettingsPanel"] = function(id, element)
		return sim.G.SettingsPanel:OpenToCategory(id, element)
	end
	sim:setGamepad(true)
	sim:login()
	sim.G.CreateSecureDelegate = nil
	local ns = assert(sim.loader.addons[ADDON]).ns
	assert(ns.SettingsSections, "real Core SettingsSections loaded")
	sim:runAs(
		ADDON,
		[[
 local ns = ...
 local category = Settings.RegisterVerticalLayoutCategory("Section integration")
 Settings.RegisterAddOnCategory(category)
 assert(ns.SettingsSections.Register(category, "Native section", "Section tooltip"))
 ns.testCategory = category
 ]],
		ns
	)
	local category = assert(ns.testCategory)
	sim:input(function()
		ns.OpenSettingsPanel(category:GetID())
	end)
	sim:advance(0.2)
	sim:expectNoErrors(ADDON)
	assert(sim.G.SettingsPanel:IsShown(), "settings visible")
	local box = sim.G.SettingsPanel:GetSettingsList().ScrollBox
	assert(box:GetDataProvider():GetSize() == 1, "native header row exists")
	local row = assert(box:FindFrame(box:GetDataProvider():Find(1)), "native header frame exists")
	assert(row.Title:GetText() == "Native section", "native row displays the heading")
	sim.G.SpellCanTargetItem = sim.G.SpellCanTargetItem or function()
		return false
	end
	sim.G.SpellStopTargeting = sim.G.SpellStopTargeting or function() end
	local IBM = sim.G.GamepadSharedUtility.InputBindingManager
	local writes, tainted = 0, {}
	for _, method in ipairs({ "AddBindingSet", "RemoveSet", "SetCoreBindingSet", "ClearBindings" }) do
		local original = IBM[method]
		IBM[method] = function(self, ...)
			writes = writes + 1
			if sim.taint.current then
				tainted[#tainted + 1] = method .. " by " .. sim.taint.current
			end
			return original(self, ...)
		end
	end
	sim:input(function()
		sim.G.SmartNavigation:SelectButton(row)
	end)
	sim:advance(0.05)
	sim:input(function()
		sim.G.SmartNavigation:AttemptClose()
	end)
	sim:input(function()
		sim.G.SettingsPanel:Close()
	end)
	sim:advance(0.2)
	sim:input(function()
		sim.G.SetPreferredGamepadInteractTarget(nil)
	end)
	sim:advance(0.05)
	assert(writes > 0, "navigation exercised the binding stack")
	assert(#tainted == 0, "binding writes remain untainted: " .. table.concat(tainted, "; "))
	sim:advance(0.1)
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)

scenario("native section groups preserve control order and values", function(sim)
	sim.impl["C_SettingsUtil.OpenSettingsPanel"] = function(id, element)
		return sim.G.SettingsPanel:OpenToCategory(id, element)
	end
	sim:login()
	sim.G.CreateSecureDelegate = nil
	local ns = assert(sim.loader.addons[ADDON]).ns
	sim:runAs(
		ADDON,
		[[
 local ns = ...
 local category = Settings.RegisterVerticalLayoutCategory("Grouped section integration")
 Settings.RegisterAddOnCategory(category)
 ns.testSaved = { first = true, second = false }
 for index, key in ipairs({ "first", "second" }) do
  assert(ns.SettingsSections.Register(category, "Section " .. index, "Section tooltip"))
  local setting = Settings.RegisterProxySetting(category, "SectionTest_" .. key,
   Settings.VarType.Boolean, "Control " .. index, false,
   function() return ns.testSaved[key] end,
   function(value) ns.testSaved[key] = value end)
  Settings.CreateCheckbox(category, setting, "Control tooltip")
 end
 ns.testCategory = category
 ]],
		ns
	)
	sim:input(function()
		ns.OpenSettingsPanel(ns.testCategory:GetID())
	end)
	sim:advance(0.2)
	local box = sim.G.SettingsPanel:GetSettingsList().ScrollBox
	assert(box:GetDataProvider():GetSize() == 4, "both native heading/control groups exist")
	local rows = {}
	for index = 1, 4 do
		rows[index] = assert(box:FindFrame(box:GetDataProvider():Find(index)), "native group row exists")
	end
	assert(rows[1].Title:GetText() == "Section 1", "first heading precedes its control")
	assert(rows[3].Title:GetText() == "Section 2", "second heading follows the first control")
	assert(rows[2].Checkbox and rows[4].Checkbox, "native checkbox controls remain between headings")
	assert(ns.testSaved.first == true and ns.testSaved.second == false, "headings preserve existing values")
	sim:input(function()
		rows[4]:OnCheckboxValueChanged(true)
	end)
	assert(ns.testSaved.first == true and ns.testSaved.second == true, "native control writes only its own setting")
	sim:expectNoErrors(ADDON)
end)
