---@type string, ForeverTrackerNamespace
local _, ns = ...

-- EllesmereUI's Quest Tracker, on WoW Forever with its Custom Quest Tracker on, draws the visible quest list in
-- EUI_CustomQuestTracker. Blizzard's ObjectiveTrackerFrame is left shown but at alpha 0 and click-through, and it
-- still holds the game's watched quests, which need not match the filtered list on screen. A column hung under that
-- frame therefore sits far below the quests the player sees and ignores the tracker's filters.
--
-- The custom frame's height is its filtered content's height (capped, then scrolled), so its bottom edge is exactly
-- where the visible list ends. UI/TrackerHost.lua consults this module after EQOT and before Questie, so a player
-- with both installed follows the custom tracker even while EllesmereUI's own visibility rules hide it: the slot
-- they chose is still that one. Every call here is a read: nothing moves, sizes or otherwise touches EllesmereUI's
-- frame, its settings or Blizzard's tracker.
--
-- Never anchor a frame of ours to the custom tracker. EllesmereUI's Unlock Mode re-applies its own anchor and reads
-- its geometry while moving it; the host keeps itself on UIParent and asks the frame where it is instead.
---@class ForeverTrackerEllesmere
local TrackerEllesmere = {}
ns.TrackerEllesmere = TrackerEllesmere

-- The room the column leaves between itself and the list, and from the screen's edges.
local GAP, MARGIN = 8, 24
local WATCH_INTERVAL = 0.25
local watched = false
local waits = 0
local ticker, sinceTick, lastPlace

-- Another addon's global, read with rawget: it exists only while the custom tracker is the one in use.
---@return Frame?
local function CustomFrame()
	return rawget(_G, "EUI_CustomQuestTracker")
end

-- Whether the Quest Tracker module has loaded at all, so Await knows there is something to wait for.
---@return boolean
local function Installed()
	return rawget(_G, "EllesmereUIQuestTracker") ~= nil or CustomFrame() ~= nil
end

-- Where the list says it is, as one string, so a move, a resize or a filter change shows up as a different one.
---@param frame Frame
---@return string
local function Place(frame)
	local point, relativeTo, relativePoint, x, y = frame:GetPoint()
	return table.concat({
		tostring(point),
		tostring(relativeTo),
		tostring(relativePoint),
		x or 0,
		y or 0,
		frame:GetWidth() or 0,
		frame:GetHeight() or 0,
	}, "|")
end

-- The list's show, hide, size and drag-stop scripts call `onChange` when the list toggles, grows or is dragged, and
-- one addon-owned ticker notices the moves and resizes nothing of the list's own does: Unlock Mode moves it while the
-- player drags, and a profile load puts it back with no event of its own.
--
-- A hidden list is still read: EllesmereUI's visibility rules hide the frame in raids, out of instances or on
-- mouseover, and its custom tracker is the slot the player chose even then. The muted native tracker is never the
-- better answer.
---@param frame Frame
---@param onChange function
local function Watch(frame, onChange)
	watched = true
	frame:HookScript("OnShow", onChange)
	frame:HookScript("OnHide", onChange)
	frame:HookScript("OnDragStop", onChange)
	frame:HookScript("OnSizeChanged", onChange)
	ticker = ticker or CreateFrame("Frame")
	lastPlace = Place(frame)
	ticker:SetScript("OnUpdate", function(_, elapsed)
		sinceTick = (sinceTick or 0) + (elapsed or 0)
		if sinceTick < WATCH_INTERVAL then
			return
		end
		sinceTick = 0
		local place = Place(frame)
		if place ~= lastPlace then
			lastPlace = place
			onChange()
		end
	end)
end

-- EllesmereUI's custom list while it is placed, or nil. A list anchored to `host` moves with it, so it can never be
-- cleared: that one is left alone.
---@param host Frame
---@param onChange function
---@return Frame?
function TrackerEllesmere.List(host, onChange)
	local frame = CustomFrame()
	if type(frame) ~= "table" or type(frame.GetPoint) ~= "function" then
		return nil
	end
	if not watched then
		Watch(frame, onChange)
	end
	local _, relativeTo = frame:GetPoint()
	if relativeTo == host then
		return nil
	end
	if not (frame:GetLeft() and frame:GetRight() and frame:GetTop() and frame:GetBottom()) then
		return nil
	end
	return frame
end

-- EllesmereUI builds its custom tracker on PLAYER_LOGIN, and a reload can put it together after the host's first
-- layout. While the module is loaded and the custom frame is not there yet, check once a second, at most 30 times.
---@param onFound function
function TrackerEllesmere.Await(onFound)
	if watched or waits >= 30 or not Installed() or CustomFrame() then
		return
	end
	waits = waits + 1
	C_Timer.After(1, function()
		if CustomFrame() then
			onFound()
		else
			TrackerEllesmere.Await(onFound)
		end
	end)
end

-- The list's edges in `host`'s own scale, from the screen's bottom left corner: left, right, top, bottom.
---@param list Frame
---@param host Frame
---@return number, number, number, number
local function Edges(list, host)
	local toHost = list:GetEffectiveScale() / host:GetEffectiveScale()
	return list:GetLeft() * toHost, list:GetRight() * toHost, list:GetTop() * toHost, list:GetBottom() * toHost
end

-- The height the sections may take: the room above the list's top, the most any place gives.
---@param list Frame
---@param host Frame
---@return number
function TrackerEllesmere.Room(list, host)
	local _, _, top = Edges(list, host)
	return math.max(0, top - MARGIN)
end

-- Where `host`, as laid out, can go round the list, best first, each as { point on UIParent, x, y } in the host's
-- scale: below the list, then above it, each only when it fits on screen, then beside it at `besideX`, level with its
-- top, which always comes last. Below and above line up with the list's edge nearer the screen's side.
---@param list Frame
---@param host Frame
---@param besideX number
---@param screenWidth number
---@param screenHeight number
---@return { [1]: FramePoint, [2]: number, [3]: number }[]
function TrackerEllesmere.Places(list, host, besideX, screenWidth, screenHeight)
	local left, right, top, bottom = Edges(list, host)
	local width, height = host:GetWidth(), host:GetHeight()
	local function onScreen(x)
		return math.max(0, math.min(x, math.max(0, screenWidth - width)))
	end
	local x = onScreen((left + right) / 2 <= screenWidth / 2 and left or right - width)
	local places = {}
	if bottom - GAP - height >= MARGIN then
		places[#places + 1] = { "TOPLEFT", x, bottom - GAP - screenHeight }
	end
	if top + GAP + height <= screenHeight - MARGIN then
		places[#places + 1] = { "BOTTOMLEFT", x, top + GAP }
	end
	places[#places + 1] = { "TOPLEFT", onScreen(besideX), top - screenHeight }
	return places
end
