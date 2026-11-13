local _, ns = ...

-- The report's performance section: the client's own add-on profiler numbers for every loaded addon that depends on
-- ForeverCore, plus the overall figures, and each addon's memory. It is read once when the report window opens and the
-- answer is reused while the issue composer is typed in; nothing here samples in the background, because the memory
-- walk is the expensive part of a read and a report is not worth a tick.

local L = ns.L

-- The client's metrics, in the order !!DevPerf reads them. A build without one shows "-" in that column rather than a
-- zero, so a missing metric never reads as a fast addon.
local METRICS = {
	{ name = "SessionAverageTime", header = "Session", kind = "time" },
	{ name = "RecentAverageTime", header = "Recent", kind = "time" },
	{ name = "PeakTime", header = "Peak", kind = "time" },
	{ name = "LastTime", header = "Last", kind = "time" },
	{ name = "CountTimeOver1Ms", header = "1 ms", kind = "count" },
	{ name = "CountTimeOver5Ms", header = "5 ms", kind = "count" },
	{ name = "CountTimeOver10Ms", header = "10 ms", kind = "count" },
	{ name = "CountTimeOver50Ms", header = "50 ms", kind = "count" },
	{ name = "CountTimeOver100Ms", header = "100 ms", kind = "count" },
}

local NAME_WIDTH = 22
local TIME_WIDTH = 9
local COUNT_WIDTH = 7
local MEMORY_WIDTH = 9

-- The answer from the last read, reused by the report text until the next window opens.
---@type string[]?
local snapshot

-- A value the client holds secret cannot be read or formatted (Core/SafeCall.lua, loaded first).
local Readable = ns.Readable

---@param value any
---@return number?
local function Number(value)
	value = Readable(value)
	return type(value) == "number" and value or nil
end

---@return table?
local function Profiler()
	local profiler = rawget(_G, "C_AddOnProfiler")
	return type(profiler) == "table" and profiler or nil
end

---@param profiler table
---@return boolean
local function ProfilerEnabled(profiler)
	if type(profiler.IsEnabled) ~= "function" then
		return false
	end
	local ok, enabled = pcall(profiler.IsEnabled)
	return ok and enabled == true
end

---@param metric string
---@return number?
local function Metric(metric)
	local values = rawget(_G, "Enum")
	values = type(values) == "table" and values.AddOnProfilerMetric or nil
	return type(values) == "table" and values[metric] or nil
end

---@param read function
---@param metric number
---@param name? string
---@return number?
local function MetricValue(read, metric, name)
	if type(read) ~= "function" then
		return nil
	end
	local ok, value
	if name == nil then
		ok, value = pcall(read, metric)
	else
		ok, value = pcall(read, name, metric)
	end
	return ok and Number(value) or nil
end

-- One addon's metric values, read by the profiler function `read`; `name` is left out for the overall and application
-- metrics, which take only the metric.
---@param read function
---@param name? string
---@return table<string, number?>
local function Values(read, name)
	local values = {}
	for _, entry in ipairs(METRICS) do
		local id = Metric(entry.name)
		values[entry.name] = id and MetricValue(read, id, name) or nil
	end
	return values
end

---@param name string
---@return number?
local function AddonMemory(name)
	local memory = rawget(_G, "GetAddOnMemoryUsage")
	if type(memory) ~= "function" then
		return nil
	end
	local ok, value = pcall(memory, name)
	return ok and Number(value) or nil
end

---@param name string
---@return boolean
local function Loaded(name)
	local addOns = rawget(_G, "C_AddOns")
	if type(addOns) ~= "table" or type(addOns.IsAddOnLoaded) ~= "function" then
		return false
	end
	local ok, loading, loaded = pcall(addOns.IsAddOnLoaded, name)
	if not ok then
		return false
	end
	if type(loaded) == "boolean" then
		return loaded
	end
	return loading == true
end

---@param name string
---@return boolean
local function DependsOnCore(name)
	local addOns = rawget(_G, "C_AddOns")
	if type(addOns) ~= "table" then
		return false
	end
	local dependencies = addOns.GetAddOnDependencies
	if type(dependencies) == "function" then
		local ok, list = pcall(function()
			return { dependencies(name) }
		end)
		if ok and type(list) == "table" then
			for _, dependency in ipairs(list) do
				dependency = Readable(dependency)
				if dependency == "ForeverCore" then
					return true
				end
			end
		end
	end
	local metadata = addOns.GetAddOnMetadata
	if type(metadata) == "function" then
		local ok, value = pcall(metadata, name, "Dependencies")
		value = ok and Readable(value) or nil
		if type(value) == "string" then
			for dependency in value:gmatch("[^,]+") do
				if dependency:match("^%s*(.-)%s*$") == "ForeverCore" then
					return true
				end
			end
		end
	end
	return false
end

-- The loaded addons that depend on ForeverCore, in name order so the table reads the same at every open.
---@return string[]
local function Dependents()
	local names = {}
	local addOns = rawget(_G, "C_AddOns")
	if
		type(addOns) ~= "table"
		or type(addOns.GetNumAddOns) ~= "function"
		or type(addOns.GetAddOnInfo) ~= "function"
	then
		return names
	end
	local ok, count = pcall(addOns.GetNumAddOns)
	count = ok and Readable(count) or nil
	if type(count) ~= "number" then
		return names
	end
	for index = 1, count do
		local named, name = pcall(addOns.GetAddOnInfo, index)
		name = named and Readable(name) or nil
		if type(name) == "string" and name ~= "ForeverCore" and Loaded(name) and DependsOnCore(name) then
			names[#names + 1] = name
		end
	end
	table.sort(names)
	return names
end

---@param text string
---@param width integer
---@return string
local function Left(text, width)
	return ("%-" .. width .. "s"):format(text)
end

---@param text string
---@param width integer
---@return string
local function Right(text, width)
	return ("%" .. width .. "s"):format(text)
end

---@param value number?
---@param width integer
---@param kind string
---@return string
local function Cell(value, width, kind)
	if value == nil then
		return Right("-", width)
	end
	if kind == "count" then
		return Right(("%d"):format(value), width)
	end
	return Right(("%.3f"):format(value), width)
end

---@return string
local function Header()
	local parts = { Left(L["Addon"], NAME_WIDTH) }
	for _, entry in ipairs(METRICS) do
		parts[#parts + 1] = Right(L[entry.header], entry.kind == "count" and COUNT_WIDTH or TIME_WIDTH)
	end
	parts[#parts + 1] = Right(L["Memory KB"], MEMORY_WIDTH)
	return table.concat(parts, " ")
end

---@param label string
---@param values table<string, number?>
---@param memory number?
---@return string
local function Row(label, values, memory)
	local parts = { Left(label, NAME_WIDTH) }
	for _, entry in ipairs(METRICS) do
		parts[#parts + 1] = Cell(values[entry.name], entry.kind == "count" and COUNT_WIDTH or TIME_WIDTH, entry.kind)
	end
	parts[#parts + 1] = memory and Right(("%.0f"):format(memory), MEMORY_WIDTH) or Right("-", MEMORY_WIDTH)
	return table.concat(parts, " ")
end

-- The whole section: the heading, the overall rows and one row per dependent addon. Missing client APIs are said in
-- one line rather than raised, so a report always opens.
---@return string[]
local function Read()
	local profiler = Profiler()
	if
		profiler == nil
		or type(profiler.IsEnabled) ~= "function"
		or type(profiler.GetOverallMetric) ~= "function"
		or type(profiler.GetApplicationMetric) ~= "function"
		or type(profiler.GetAddOnMetric) ~= "function"
	then
		return { L["Performance (read when this window opened):"], L["Performance: not available on this client."] }
	end
	if not ProfilerEnabled(profiler) then
		return {
			L["Performance (read when this window opened):"],
			L["Performance: the client's add-on profiler is off."],
		}
	end
	local lines = { L["Performance (read when this window opened):"], Header() }
	lines[#lines + 1] = Row(L["All addons"], Values(profiler.GetOverallMetric), nil)
	lines[#lines + 1] = Row(L["Application"], Values(profiler.GetApplicationMetric), nil)
	local refresh = rawget(_G, "UpdateAddOnMemoryUsage")
	local memory = rawget(_G, "GetAddOnMemoryUsage")
	if type(refresh) == "function" then
		pcall(refresh)
	end
	for _, name in ipairs(Dependents()) do
		local kb = AddonMemory(name)
		lines[#lines + 1] = Row(name, Values(profiler.GetAddOnMetric, name), kb)
	end
	if type(memory) ~= "function" then
		lines[#lines + 1] = L["Memory: not available on this client."]
	end
	return lines
end

-- The report asks for a fresh read when its window opens; the text and the issue composer reuse it until then.
---@param fresh? boolean
---@return string[]
function ns.PerformanceLines(fresh)
	if fresh or snapshot == nil then
		snapshot = Read()
	end
	return snapshot
end
