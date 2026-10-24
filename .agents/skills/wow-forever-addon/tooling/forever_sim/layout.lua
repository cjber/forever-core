-- Layout checks: where frames end up on screen given their anchors, sizes and scale, and whether two overlap.
local M = {}

function M.build(sim)
	local W = sim.widgets

	local function resolve(frame)
		if type(frame) == "string" then
			return sim.G[frame]
		end
		return frame
	end

	-- left, bottom, width, height in UIParent units, or nil when the frame is not placed.
	function sim.rect(_, frame)
		frame = resolve(frame)
		local r = frame and W.rect(frame)
		if r then
			return r[1], r[2], r[3], r[4]
		end
	end

	-- The overlap of two frames' screen rects (both visible and placed): its area, or 0.
	function sim.overlap(_, a, b)
		a, b = resolve(a), resolve(b)
		if not (a and b and W.isVisible(a) and W.isVisible(b)) then
			return 0
		end
		local ra, rb = W.rect(a), W.rect(b)
		if not ra or not rb then
			return 0
		end
		local w = math.min(ra[1] + ra[3], rb[1] + rb[3]) - math.max(ra[1], rb[1])
		local h = math.min(ra[2] + ra[4], rb[2] + rb[4]) - math.max(ra[2], rb[2])
		if w <= 0.5 or h <= 0.5 then
			return 0
		end
		return w * h
	end

	local function describe(frame)
		frame = resolve(frame)
		if not frame then
			return "nil"
		end
		local r = W.rect(frame)
		return string.format(
			"%s %s",
			frame:GetDebugName(),
			r and string.format("(left %.0f, bottom %.0f, %.0fx%.0f)", r[1], r[2], r[3], r[4]) or "(not placed)"
		)
	end
	sim.describeRect = describe

	-- Fails when a and b (frames or global names) overlap on screen.
	function sim.expectNoOverlap(_, a, b)
		local area = sim:overlap(a, b)
		if area > 0 then
			error(string.format("%s overlaps %s by %.0f square units", describe(a), describe(b), area), 2)
		end
	end

	-- Fails unless frame is shown, placed and entirely on screen.
	function sim.expectOnScreen(_, frame)
		local f = resolve(frame)
		local r = f and W.rect(f)
		if not (f and W.isVisible(f) and r) then
			error(describe(frame) .. " is not shown on screen", 2)
		end
		if
			r[1] < -0.5
			or r[2] < -0.5
			or r[1] + r[3] > sim.screenWidth + 0.5
			or r[2] + r[4] > sim.screenHeight + 0.5
		then
			error(describe(frame) .. " runs off the screen", 2)
		end
	end
end

return M
