-- Horizontal clipping is independent of the scroll height and UI scale. The native
-- POI block anchors its button left of HeaderText; a quest item's hotkey can extend right.
local harness = dofile("tests/tracker_host_harness.lua")
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
for _, scale in ipairs({ 0.5, 1, 1.5 }) do
	local t = harness.new()
	local module = t.scrollModule(3, 10, 40)
	t.host:MarkDirty()
	t.drain()
	t.drain()
	if os.getenv("TRACKER_WIDTH_CASE") ~= "overflow" then
		check(module.Header:GetWidth() == module:GetWidth(), "viewport header follows section width")
	end
	local contents = module.ContentsFrame
	contents.effectiveScale = scale
	contents.left = 100
	local function region(left, right, ownScale)
		return {
			IsShown = function()
				return true
			end,
			GetLeft = function()
				return left
			end,
			GetRight = function()
				return right
			end,
			GetEffectiveScale = function()
				return ownScale or scale
			end,
		}
	end
	local block = region(120, 332)
	-- Real native contract: default blockOffsetX20, POI TOPRIGHT at HeaderText TOPLEFT -7,
	-- with a 20-unit button and centered 32-unit art: left = 100+20-7-20-6 = 87.
	local poi = region(93, 113)
	local nativePOI = os.getenv("TRACKER_POI_SOURCE")
	if nativePOI then
		local env = setmetatable({
			CreateFramePool = function()
				return {}
			end,
			CreateFromMixins = function()
				return {}
			end,
			POIButtonUtil = { Style = { QuestInProgress = 1 } },
		}, { __index = _G })
		setfenv(assert(loadfile(nativePOI)), env)()
		function poi:SetPoint(point, _, relativePoint, x)
			check(point == "TOPRIGHT" and relativePoint == "TOPLEFT", "native POI anchors outside text")
			local right = 120 + x
			self.GetLeft = function()
				return right - 20
			end
			self.GetRight = function()
				return right
			end
		end
		poi.SetPingWorldMap = function() end
		env.ObjectiveTrackerQuestPOIBlockMixin.AddPOIButton({
			GetPOIButton = function()
				return poi
			end,
		})
	end
	local poiArt = region(87, 119)
	function poi.GetRegions()
		return poiArt
	end
	-- A region in a different effective scale must be normalised before comparing edges.
	local edge = 100 + contents:GetWidth()
	local hotkey = region(edge * 2, (edge + 16) * 2, scale / 2)
	function block.GetChildren()
		return poi
	end
	function block.GetRegions()
		return hotkey
	end
	function contents.GetChildren()
		return block
	end
	t.host:MarkDirty()
	t.drain()
	t.drain()
	check(module.scrollFrame.points.TOPLEFT[4] == -13, "native POI left edge survives clipping at scale " .. scale)
	check(module.scrollFrame.point[4] + 18 == 16, "right extension survives clipping")
	check(contents:GetWidth() == module:GetWidth() - 18, "clip expansion does not change text wrapping")
	check(contents.point[2] == module.Header and contents.point[4] == 0, "the contents keep the header's left edge")
	check(module.scrollFrame.point[4] == -18 + 16, "viewport expands its right edge")
	local held = module.scrollFrame.points.TOPLEFT[4]
	t.setCombat(true)
	contents.left = 200
	module:LayoutTrackerScroll()
	check(module.scrollFrame.points.TOPLEFT[4] == held, "combat does not change clipping geometry")
	t.setCombat(false)
	function contents.GetChildren() end
	t.host:MarkDirty()
	t.drain()
	check(contents.point[4] == 0 and module.scrollFrame.point[4] == -18, "released children leave no stale padding")
end
print("tracker_width_spec: " .. checks .. " checks passed")
