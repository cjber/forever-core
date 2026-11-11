-- luacheck: globals SlashCmdList SLASH_SIMSLASHCLIENT1
-- Fixture for the client command rule: the word is the client's own main assist, so the chat box never runs the
-- addon handler.
SLASH_SIMSLASHCLIENT1 = "/ma"
SlashCmdList.SIMSLASHCLIENT = function()
	error("the addon handler must not run")
end
