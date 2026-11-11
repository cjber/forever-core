-- The shared TOC reader every consumer's spec loader calls: core's own TOC expands in order, UI/TrackerSection.xml's
-- template comes back with its stock parent, and a fixture with nested includes, comments, both quote styles,
-- self-closing tags and Windows separators resolves exactly.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")

local function lines(entries)
	local out = {}
	for index, entry in ipairs(entries) do
		out[index] = entry.kind .. " " .. entry.path
	end
	return table.concat(out, "\n")
end

local function expected(rows)
	return table.concat(rows, "\n")
end

-- Core's real TOC: every Lua file at its TOC path, and the one XML file in the place the TOC puts it.
equal(
	lines(Toc.files(".", "ForeverCore.toc")),
	expected({
		"lua Core.lua",
		"lua Locales/enUS.lua",
		"lua Locales/deDE.lua",
		"lua Locales/esES.lua",
		"lua Locales/esMX.lua",
		"lua Locales/frFR.lua",
		"lua Locales/koKR.lua",
		"lua Locales/ptBR.lua",
		"lua Locales/ruRU.lua",
		"lua Locales/zhCN.lua",
		"lua Locales/zhTW.lua",
		"lua Data/Credits.lua",
		"lua Core/SafeCall.lua",
		"lua Core/OpenMap.lua",
		"lua Core/OpenSettings.lua",
		"lua Core/Log.lua",
		"lua Core/Text.lua",
		"lua Core/PeerStats.lua",
		"lua Core/MinimapButton.lua",
		"lua UI/Art.lua",
		"lua UI/Report.lua",
		"lua UI/ForeverFamily.lua",
		"lua UI/Credits.lua",
		"lua UI/SettingsPage.lua",
		"lua UI/TrackerQuestie.lua",
		"lua UI/TrackerEqot.lua",
		"lua UI/TrackerLock.lua",
		"lua UI/TrackerOrder.lua",
		"lua UI/ContextMenu.lua",
		"lua UI/TrackerHost.lua",
		"xml UI/TrackerSection.xml",
		"lua UI/TrackerSection.lua",
		"lua Core/QuestOrder.lua",
		"lua UI/TrackerQuests.lua",
		"lua UI/MapCanvas.lua",
		"lua Core/LeaderboardsData.lua",
		"lua Core/APIKit.lua",
		"lua UI/Leaderboards.lua",
		"lua UI/QuestLogTabs.lua",
		"lua UI/ProfessionTabs.lua",
		"lua Expose.lua",
	}),
	"core's TOC expands in order"
)

-- The template a harness registers before UI/TrackerSection.lua runs: it inherits Blizzard's objective line.
local tracker = Toc.templates("UI/TrackerSection.xml")
equal(#tracker, 1, "UI/TrackerSection.xml defines one template")
equal(tracker[1].name, "ForeverTrackerInteractiveLineTemplate", "the tracker line's name")
equal(tracker[1].type, "Frame", "the tracker line is a Frame")
equal(tracker[1].inherits, "ObjectiveTrackerLineTemplate", "the tracker line inherits the stock line")

-- A fixture that exercises the client's rules: a Windows TOC line, a Windows and a relative include, a comment
-- holding tags, single and double quoted attributes, and self-closing tags.
equal(
	lines(Toc.files("tests/fixtures/toc-reader", "Test.toc")),
	expected({
		"xml tests/fixtures/toc-reader/Files/Root.xml",
		"xml tests/fixtures/toc-reader/Files/Nested/Child.xml",
		"xml tests/fixtures/toc-reader/Files/Nested/Grandchild.xml",
		"lua tests/fixtures/toc-reader/Files/Nested/Deep.lua",
		"lua tests/fixtures/toc-reader/Files/Scripts/Child.lua",
		"lua tests/fixtures/toc-reader/Files/Scripts/Root.lua",
		"lua tests/fixtures/toc-reader/Files/Last.lua",
	}),
	"the fixture expands in document order"
)

-- The fixture's templates come only from virtual elements, including one written with single quotes.
local rootTemplates = Toc.templates("tests/fixtures/toc-reader/Files/Root.xml")
equal(#rootTemplates, 2, "Root.xml defines two templates")
equal(rootTemplates[1].name, "RootTemplate", "the first fixture template")
equal(rootTemplates[1].inherits, "ObjectiveTrackerLineTemplate", "with its stock parent")
equal(rootTemplates[2].name, "OtherTemplate", "the second fixture template")
equal(rootTemplates[2].inherits, "RootTemplate", "whose parent is single quoted")

local deepTemplates = Toc.templates("tests/fixtures/toc-reader/Files/Nested/Grandchild.xml")
equal(#deepTemplates, 1, "Grandchild.xml defines one template")
equal(deepTemplates[1].name, "DeepTemplate", "the nested template")
equal(deepTemplates[1].inherits, "ChildTemplate", "with the template from its parent file")

print(("toc_reader_spec: %d checks passed"):format(checks))
