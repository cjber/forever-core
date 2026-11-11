-- luacheck: globals GameMenuEscPriority RegisterGameMenuEscHandler
-- Fixture for the Escape registry: an addon handler goes into Blizzard_GameMenuEsc's file-local list, and the
-- client's secure walk of that list on Escape must be caught by the gate.
RegisterGameMenuEscHandler(GameMenuEscPriority.AddOn, function()
	return false
end)
