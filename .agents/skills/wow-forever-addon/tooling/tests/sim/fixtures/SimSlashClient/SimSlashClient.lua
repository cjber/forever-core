-- luacheck: ignore 131 (the client reads the alias, not this file)
-- luacheck: globals SlashCmdList
-- Fixture for the client command rule: the word is the client's own main assist, so the chat box never runs the
-- addon handler.
SLASH_SIMSLASHCLIENT1 = "/ma"
SlashCmdList.SIMSLASHCLIENT = function()
	error("the addon handler must not run")
end
