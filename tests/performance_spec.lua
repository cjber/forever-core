-- Contract for the report's performance section: the client profiler and memory values, the fixed table, the cache
-- that keeps a report to one read, and the one line a client without the API gets.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end
local function check(value, label)
	checks = checks + 1
	assert(value, label)
end

local function Has(text, needle)
	return text:find(needle, 1, true) ~= nil
end

_G.strtrim = function(text)
	return text:match("^%s*(.-)%s*$")
end
_G.geterrorhandler = function()
	return function() end
end
_G.seterrorhandler = function() end
_G.GetTime = function()
	return 1
end
_G.date = function()
	return "2026-11-13 12:00:00"
end
_G.GetBuildInfo = function()
	return "1.0", "build", "", 16001
end
_G.GetLocale = function()
	return "enUS"
end
_G.UnitClass = function()
	return nil, "Mage"
end
_G.UnitRace = function()
	return nil, "Human"
end
_G.UnitLevel = function()
	return 60
end
_G.UnitFactionGroup = function()
	return "Alliance"
end
_G.C_Map = {
	GetBestMapForUnit = function()
		return nil
	end,
}
_G.canaccessvalue = function(value)
	return value ~= "secret value"
end

-- Two loaded addons: ForeverCore and one addon that depends on it.
_G.C_AddOns = {
	GetAddOnMetadata = function(name, key)
		if key == "Dependencies" then
			return name == "ExampleAddon" and "ForeverCore" or nil
		end
		return key == "X-Website" and "https://github.com/cjber/example-addon" or "1.0.0"
	end,
	GetNumAddOns = function()
		return 2
	end,
	GetAddOnInfo = function(index)
		return index == 1 and "ForeverCore" or "ExampleAddon"
	end,
	IsAddOnLoaded = function()
		return true, true
	end,
	GetAddOnDependencies = function(name)
		if name == "ExampleAddon" then
			return "ForeverCore"
		end
	end,
}

-- The client profiler, with one read counter so the spec can prove the report samples once.
local reads = 0
local secretMetric
_G.Enum = {
	AddOnProfilerMetric = {
		SessionAverageTime = 0,
		RecentAverageTime = 1,
		PeakTime = 2,
		LastTime = 3,
		CountTimeOver1Ms = 4,
		CountTimeOver5Ms = 5,
		CountTimeOver10Ms = 6,
		CountTimeOver50Ms = 7,
		CountTimeOver100Ms = 8,
	},
}
_G.C_AddOnProfiler = {
	IsEnabled = function()
		return true
	end,
	GetOverallMetric = function(metric)
		reads = reads + 1
		return 0.1 + metric * 0.01
	end,
	GetApplicationMetric = function(metric)
		reads = reads + 1
		return 0.2 + metric * 0.01
	end,
	GetAddOnMetric = function(name, metric)
		reads = reads + 1
		if metric == secretMetric then
			return "secret value"
		end
		if name == "ExampleAddon" then
			return metric == 1 and 0.5 or 0.25
		end
		return 0.05
	end,
}
local memoryWalks = 0
_G.UpdateAddOnMemoryUsage = function()
	memoryWalks = memoryWalks + 1
end
_G.GetAddOnMemoryUsage = function(name)
	return name == "ExampleAddon" and 1234 or 12
end

-- The shared modules the report window reads through, loaded in the TOC's own order.
local ns = {
	L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	}),
	Art = { Icon = function() end },
}
assert(loadfile("Core/SafeCall.lua"))("ExampleAddon", ns)
assert(loadfile("Core/Log.lua"))("ExampleAddon", ns)
assert(loadfile("Core/Performance.lua"))("ExampleAddon", ns)
assert(loadfile("UI/Report.lua"))("ExampleAddon", ns)

-- The fixed table: the overall rows, one dependent addon's metrics, and its memory.
local lines = ns.PerformanceLines(true)
local text = table.concat(lines, "\n")
check(Has(text, "Performance (read when this window opened):"), "the section has its heading")
check(Has(text, "All addons"), "the all-addon figures are there")
check(Has(text, "0.100"), "the all-addon figures are the client's values")
check(Has(text, "Application"), "the whole application's figures are there")
check(Has(text, "0.200"), "the application figures are the client's values")
check(Has(text, "ExampleAddon"), "a loaded addon that depends on ForeverCore is there")
check(not Has(text, "ForeverCore "), "ForeverCore itself is not listed as a dependent")
check(Has(text, "0.500"), "the addon's recent time is the client's value")
check(Has(text, "1234"), "the addon's memory is read after the memory walk")
equal(memoryWalks, 1, "the memory walk happens once per section read")

-- The report text carries the table, and a second read of the same report uses the cache.
local report = ns.Report.Text({})
check(Has(report, "Performance (read when this window opened):"), "the report text carries the performance section")
check(Has(report, "ExampleAddon"), "and the addon's row")
local afterFirst = reads
ns.Report.Text({})
equal(reads, afterFirst, "a cached report does not sample the profiler again")
ns.PerformanceLines(true)
check(reads > afterFirst, "opening a report takes one fresh sample")

-- A value the client holds secret is not formatted as a number.
secretMetric = 1
local secretText = table.concat(ns.PerformanceLines(true), "\n")
check(not Has(secretText, "secret value"), "a secret metric never reaches the report text")
check(Has(secretText, "-"), "the secret metric reads as an unknown")

-- A client without the profiler gets one line, not an error.
secretMetric = nil
_G.C_AddOnProfiler = nil
local missing = table.concat(ns.PerformanceLines(true), "\n")
check(Has(missing, "Performance: not available on this client."), "a client without C_AddOnProfiler gets the line")
local missingReport = ns.Report.Text({})
check(Has(missingReport, "Performance: not available on this client."), "and the report text carries it")

-- A table longer than its share of the report keeps whole rows and counts the rest, so no number is cut short.
local real = ns.PerformanceLines
local long = { "Performance (read when this window opened):" }
for index = 1, 20 do
	long[#long + 1] = ("Addon%02d"):format(index) .. (" 0.123"):rep(16)
end
ns.PerformanceLines = function()
	return long
end
local cut = ns.Report.Text({})
ns.PerformanceLines = real
local shownRows, lastRow = 0, nil
for row in cut:gmatch("Addon%d%d[^\n]*") do
	shownRows = shownRows + 1
	lastRow = row
end
check(shownRows > 0 and shownRows < 20, "a long table keeps only the rows that fit")
equal(lastRow, ("Addon%02d"):format(shownRows) .. (" 0.123"):rep(16), "the last row shown is whole")
check(Has(cut, ("%d more rows not shown."):format(20 - shownRows)), "the rows left out are counted")

print(("performance_spec: %d checks passed"):format(checks))
