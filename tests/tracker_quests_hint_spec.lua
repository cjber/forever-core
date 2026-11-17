-- The Forever quest list replaces the game's objective tracker by default, so the first time it is drawn in its place
-- it says what it is and how to switch it off, with one click back to the game's tracker (issue #765). Either answer
-- is saved for the account and the hint never returns; a player who already turned the list off never sees it, nor
-- does one whose quest list another tracker owns, and it waits for combat to end. Each `Load` is a fresh login against
-- the same saved table, so "never returns" is checked across reloads.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end

local L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})

-- A widget that records what the hint does to it. Only the methods the list calls exist, so a new call fails here.
local function Widget(kind, template)
	local widget = { kind = kind, template = template, shown = true, scripts = {}, points = {} }
	function widget:Show()
		self.shown = true
	end
	function widget:Hide()
		self.shown = false
	end
	function widget:IsShown()
		return self.shown
	end
	function widget:SetScript(name, fn)
		self.scripts[name] = fn
	end
	function widget.RegisterEvent() end
	function widget.UnregisterEvent() end
	function widget.SetFrameStrata() end
	function widget.SetClampedToScreen() end
	function widget.EnableMouse() end
	function widget:SetWidth(width)
		self.width = width
	end
	function widget:GetWidth()
		return self.width or 0
	end
	function widget:SetHeight(height)
		self.height = height
	end
	function widget:ClearAllPoints()
		self.points = {}
	end
	function widget:SetPoint(...)
		self.points[#self.points + 1] = { ... }
	end
	function widget:SetText(text)
		self.text = text
	end
	function widget:GetTextWidth()
		return #(self.text or "") * 6
	end
	function widget.CreateFontString()
		local font = Widget("FontString")
		function font.SetJustifyH() end
		function font.SetJustifyV() end
		function font.GetStringHeight()
			return 48
		end
		return font
	end
	return widget
end

local env, ns, section, menuContract, ready, tracker, created
local combat, addons, uiWidth = false, {}, 1920

local function Load(db)
	created = {}
	ready, menuContract = nil, nil
	tracker = Widget("Frame")
	function tracker.GetAlpha()
		return 1
	end
	function tracker.SetAlpha() end
	function tracker.IsVisible()
		return tracker.shown
	end
	function tracker.IsProtected()
		return false
	end
	function tracker.HookScript() end
	section = Widget("Frame")
	section.hooks = {}
	section.visible = false
	function section.RegisterEvent() end
	function section.SetHeader() end
	function section.MarkDirty() end
	function section:HookScript(name, fn)
		self.hooks[name] = fn
	end
	function section:IsVisible()
		return self.visible
	end
	function section.GetCenter()
		return 1700, 800
	end
	-- The client draws the section: it becomes visible and its OnShow runs, as the column lays it out.
	function section:Draw()
		self.visible = true
		if self.hooks.OnShow then
			self.hooks.OnShow(self)
		end
	end
	function section:Undraw()
		self.visible = false
		if self.hooks.OnHide then
			self.hooks.OnHide(self)
		end
	end
	ns = {
		L = L,
		TrackerHost = {
			IsAttached = function()
				return true
			end,
		},
		TrackerSection = {
			Create = function(_, _, options)
				menuContract = options.contract
				return section
			end,
		},
	}
	env = setmetatable({
		-- The native tracker's visibility driver (#608) is not what this spec checks.
		RegisterStateDriver = function() end,
		UnregisterStateDriver = function() end,
		UIParent = {
			IsVisible = function()
				return true
			end,
			GetWidth = function()
				return uiWidth
			end,
		},
		CreateFrame = function(kind, _, _, template)
			local widget = Widget(kind, template)
			created[#created + 1] = widget
			return widget
		end,
		ObjectiveTrackerFrame = tracker,
		QuestObjectiveTrackerMixin = {},
		TRACKER_HEADER_QUESTS = "Quests",
		ForeverCoreDB = db,
		EventUtil = {
			ContinueAfterAllEvents = function(fn)
				ready = fn
			end,
		},
		C_AddOns = {
			IsAddOnLoaded = function(name)
				return addons[name] == true
			end,
		},
		C_Timer = { NewTicker = function() end },
		Mixin = function(target, mixin)
			for key, value in pairs(mixin) do
				target[key] = value
			end
		end,
		InCombatLockdown = function()
			return combat
		end,
	}, { __index = _G })
	env._G = env
	setfenv(assert(loadfile("UI/TrackerQuests.lua")), env)("ForeverCore", ns)
	ready()
end

-- The hint frame, if the list made one: the client's tutorial box, never Blizzard's HelpTip system.
local function Hint()
	for _, widget in ipairs(created) do
		if widget.template == "GlowBoxTemplate" then
			return widget
		end
	end
end

local function HintShown()
	local hint = Hint()
	return hint ~= nil and hint.shown
end

-- hint_shows_once_on_first_show: a fresh save shows the hint when the list is first drawn, not before.
local db = {}
Load(db)
check(not HintShown(), "no hint before the list is on screen")
section:Draw()
local hint = Hint()
check(hint and hint.shown, "the first time the list is drawn in place of the game's tracker, the hint shows")
check(hint.Text.text:find("Forever quest list", 1, true), "the hint names the list")
check(hint.Text.text:find("right-click the Quests header", 1, true), "the hint says where the switch is")
check(hint.Off.text == "Use the game's tracker", "the hint offers the game's tracker")
check(hint.Keep.text == "Keep this list", "the hint offers a dismiss")
check(
	hint.points[1][1] == "TOPRIGHT" and hint.points[1][3] == "TOPLEFT",
	"a column on the right gets the hint on its left"
)
local frames = #created
section:Undraw()
check(not hint.shown, "the hint goes with the list")
section:Draw()
check(hint.shown and #created == frames, "an unanswered hint comes back on the same frame")
check(db.questListHintDone == nil, "showing the hint is not an answer")

-- hint_off_button_turns_list_off_and_persists: one click goes back to the game's tracker, through the same switch as
-- the settings page, and the next login shows no hint.
hint.Off.scripts.OnClick()
check(db.questList == false, "the button turns the Forever quest list off")
check(db.questListHintDone == true, "the button's answer is saved")
check(not hint.shown, "the hint closes")
check(tracker.shown, "the game's tracker is back")
Load(db)
section:Draw()
check(not HintShown(), "after going back to the game's tracker the hint never returns")
db.questList = nil
Load(db)
section:Draw()
check(not HintShown(), "turning the list back on later shows no hint either")

-- hint_dismiss_persists: Keep this list leaves the list on and the hint gone for good.
db = {}
Load(db)
section:Draw()
Hint().Keep.scripts.OnClick()
check(db.questListHintDone == true, "dismissing is saved")
check(db.questList == nil, "dismissing leaves the list on")
check(not HintShown(), "dismissing closes the hint")
Load(db)
section:Draw()
check(not HintShown(), "a dismissed hint never returns")

-- hint_never_for_list_off: a player who turned the list off sees nothing, now or after a reload.
db = { questList = false }
Load(db)
section:Draw()
check(Hint() == nil, "a player with the list off never gets a hint")

-- hint_answered_by_any_switch: the Quests header menu reads plainly and its switch also answers the hint.
db = {}
Load(db)
section:Draw()
local label, action
menuContract.menu({ kind = "section" }, {
	Action = function(_, text, fn)
		label, action = text, fn
	end,
})
check(label == "Turn off the Forever quest list (use the game's tracker)", "the Quests menu names the switch plainly")
action()
check(
	db.questList == false and db.questListHintDone == true,
	"the menu's switch turns the list off and answers the hint"
)
check(not HintShown(), "the hint closes with the list")

-- hint_waits_for_combat: drawn in combat, the hint waits for PLAYER_REGEN_ENABLED.
db = {}
Load(db)
combat = true
section:Draw()
check(not HintShown(), "no hint opens in combat")
combat = false
section:OnEvent("PLAYER_REGEN_ENABLED")
check(HintShown(), "the hint opens once combat ends")

-- hint_never_while_other_tracker_owns: another tracker's quest list keeps the slot, and no hint shows.
db = {}
addons["!KalielsTracker"] = true
Load(db)
section:Draw()
check(not HintShown(), "no hint while another tracker owns the quest list")
addons["!KalielsTracker"] = nil
section:OnEvent("PLAYER_ENTERING_WORLD")
check(HintShown(), "the hint shows once the Forever list takes the slot")

-- A column on the left of the screen gets the hint on its right.
uiWidth = 4000
section:Undraw()
section:Draw()
check(
	Hint().points[1][1] == "TOPLEFT" and Hint().points[1][3] == "TOPRIGHT",
	"a column on the left gets it on its right"
)

print("tracker_quests_hint_spec: " .. checks .. " checks passed")
