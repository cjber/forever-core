-- Right-clicking a section header opens the column's own switches: Attach to quest tracker, and Lock when the host
-- offers one. Every section the host attaches answers the same way, and a section's own left click is left alone.
local harness = dofile("tests/tracker_host_harness.lua")
local t = harness.new({ headerShown = true })
local check, drain = t.check, t.drain
local host, first, second = t.ns.TrackerHost, t.first, t.second

local function Menu(module)
	module.Header.scripts.OnMouseUp(module.Header, "RightButton")
	return t.menus[#t.menus]
end

local function Entry(menu, text)
	for _, entry in ipairs(menu.entries) do
		if entry.text == text then
			return entry
		end
	end
end

check(first.Header.mouse == true, "a section header takes a right click")
local opened = #t.menus
local menu = Menu(first)
check(#t.menus == opened + 1 and menu.owner == t.host, "the section's menu opens on the shared column")
local attach = Entry(menu, "Attach to quest tracker")
check(attach ~= nil, "the section menu offers the attach switch")
check(attach.isSelected() == true, "the attach switch reads the saved setting")
attach.setSelected()
check(t.hostSettings.attached == false, "the attach switch saves the setting")
check(host.IsAttachedToQuestTracker() == false, "the column reports the detached setting")
local lock = Entry(menu, "Lock the tracker")
check(lock ~= nil, "the section menu offers Lock")
check(lock.isSelected() == false, "the Lock switch reads the saved setting")
lock.setSelected()
check(host.IsLocked() == true, "the Lock switch saves the setting")

-- The background is a submenu of that same menu, so every addon gets it without a settings page of its own.
local background = Entry(menu, "Tracker background")
check(background ~= nil and background.submenu ~= nil, "the section menu offers the tracker background")
local off = Entry(background.submenu, "Off")
check(off ~= nil and off.isSelected() == true, "the background starts off")
check(
	Entry(background.submenu, "25%")
		and Entry(background.submenu, "50%")
		and Entry(background.submenu, "75%")
		and Entry(background.submenu, "100%"),
	"the background offers 25%, 50%, 75% and 100%"
)
local half = Entry(background.submenu, "50%")
check(half.isSelected() == false, "a background choice reads the saved opacity")
half.setSelected()
check(t.hostSettings.backdropOpacity == 0.5, "picking 50% saves the opacity")
check(host.GetBackdropOpacity() == 0.5, "the column reports the saved opacity")
check(t.textures[1].shown == true, "picking 50% shows the background")
check(off.isSelected() == false, "the off choice follows the saved opacity")
off.setSelected()
check(t.hostSettings.backdropOpacity == 0, "Off saves the opacity as off")
check(t.textures[1].shown == false, "Off hides the background")

-- An addon that owns its context menu gets that menu, and Blizzard's is never called: Adventure Guide draws its own
-- because Blizzard_Menu.AcquireMenu can assert in Forever 70009. The generator is the same either way.
local owned = harness.new({ headerShown = true })
local ownedMenus, blizzardCalls = {}, 0
function owned.ns.ContextMenu(owner, generator)
	local function Description()
		local descriptionObject = { entries = {} }
		function descriptionObject.CreateCheckbox(_, text, isSelected, setSelected)
			descriptionObject.entries[#descriptionObject.entries + 1] =
				{ text = text, isSelected = isSelected, setSelected = setSelected }
			return {}
		end
		function descriptionObject.CreateRadio(_, text, isSelected, setSelected)
			descriptionObject.entries[#descriptionObject.entries + 1] =
				{ text = text, isSelected = isSelected, setSelected = setSelected }
			return {}
		end
		function descriptionObject.CreateButton(_, text, callback)
			if callback then
				descriptionObject.entries[#descriptionObject.entries + 1] = { text = text, callback = callback }
				return {}
			end
			local submenu = Description()
			submenu.text = text
			descriptionObject.entries[#descriptionObject.entries + 1] = { text = text, submenu = submenu }
			return submenu
		end
		return descriptionObject
	end
	local ownedMenu = { owner = owner }
	local root = Description()
	generator(owner, root)
	ownedMenu.entries = root.entries
	ownedMenus[#ownedMenus + 1] = ownedMenu
	return ownedMenu
end
owned.env.MenuUtil.CreateContextMenu = function()
	blizzardCalls = blizzardCalls + 1
end
owned.first.Header.scripts.OnMouseUp(owned.first.Header, "RightButton")
check(#ownedMenus == 1, "the addon-owned menu opens on a right click")
check(blizzardCalls == 0, "the addon-owned menu replaces Blizzard's")
check(ownedMenus[1].owner == owned.host, "the addon-owned menu opens on the shared column")
local ownedAttach = Entry(ownedMenus[1], "Attach to quest tracker")
check(ownedAttach ~= nil, "the addon-owned menu gets the same generator")
check(ownedAttach.isSelected() == true, "the addon-owned menu reads the saved setting")
ownedAttach.setSelected()
check(owned.hostSettings.attached == false, "the addon-owned menu saves the setting")
check(Entry(ownedMenus[1], "Lock the tracker") ~= nil, "the addon-owned menu offers Lock")
check(Entry(ownedMenus[1], "Tracker background") ~= nil, "the addon-owned menu offers the tracker background")

-- A section's own left click still runs, and a right click runs it too before the shared menu opens.
local buttons = {}
local third = t.module(3, function(_, button)
	buttons[#buttons + 1] = button
end)
opened = #t.menus
third.Header.scripts.OnMouseUp(third.Header, "LeftButton")
check(#t.menus == opened, "a left click opens no menu")
check(buttons[1] == "LeftButton", "the section's own left click still runs")
Menu(third)
check(buttons[2] == "RightButton", "the section's own handler still runs on a right click")

-- A switch made in combat is saved at once and applied when combat ends, as the save buttons already are.
host.SetAttached(true)
drain()
t.setCombat(true)
local inCombat = Menu(second)
Entry(inCombat, "Attach to quest tracker").setSelected()
check(t.hostSettings.attached == false, "a combat switch saves the setting")
drain()
check(t.host.point[2] == t.native.NineSlice, "a combat switch waits for combat's end")
t.setCombat(false)
t.fire("PLAYER_REGEN_ENABLED")
drain()
check(t.host.point[2] == t.parent, "combat's end applies the switch")

print("tracker_header_menu_spec: " .. t.checks() .. " checks passed")
