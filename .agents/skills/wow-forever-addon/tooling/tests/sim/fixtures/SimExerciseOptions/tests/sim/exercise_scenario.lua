-- luacheck: read globals scenario
-- The declared exercise: its own options (here, tolerating the refusal the fixture's button causes) replace the
-- runner's automatic one, which would otherwise fail. The scenario options carry the same tolerance.
scenario("the declared exercise with its own options", { allowErrors = true }, function(sim)
	sim:exercise({ allowErrors = true })
end)
