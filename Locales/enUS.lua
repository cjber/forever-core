local _, ns = ...

-- English phrases are the keys, so a phrase with no translation reads as English. These are the phrases core's own
-- files draw: the tracker column, the report and issue windows, the debug log and the settings page.
---@type table<string, string>
local L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})
ns.L = L

L["%s (%s)"] = "%s (%s)"
L["%s and %s"] = "%s and %s"
L["%s, %s and %s"] = "%s, %s and %s"
L["%s, %s, %s and %d more"] = "%s, %s, %s and %d more"
L["+%d more"] = "+%d more"
L[", "] = ", "
L["%d contributions"] = "%d contributions"
L["%s (last %d):"] = "%s (last %d):"
L["%s: no lines yet."] = "%s: no lines yet."
L["1 ms"] = "1 ms"
L["5 ms"] = "5 ms"
L["10 ms"] = "10 ms"
L["50 ms"] = "50 ms"
L["100 ms"] = "100 ms"
L["Addon"] = "Addon"
L["All addons"] = "All addons"
L["Application"] = "Application"
L["Bug"] = "Bug"
L["Bug: "] = "Bug: "
L["Close"] = "Close"
L["Copy issue link"] = "Copy issue link"
L["Copy report"] = "Copy report"
L["Debug log is already on and pinned for this character."] = "Debug log is already on and pinned for this character."
L["Debug log is off and unpinned."] = "Debug log is off and unpinned."
L["Debug log is off for this session; it is still pinned."] = "Debug log is off for this session; it is still pinned."
L["Debug log is off."] = "Debug log is off."
L["Debug log is on and pinned for this character."] = "Debug log is on and pinned for this character."
L["Debug log is on for this session."] = "Debug log is on for this session."
L["%d more rows not shown."] = "%d more rows not shown."
L["Debug capture is on: /forever debug off stops it."] = "Debug capture is on: /forever debug off stops it."
L["Debug capture is on. Attach the files in the client's Logs folder to your report. Turn it off with /forever debug off."] =
	"Debug capture is on. Attach the files in the client's Logs folder to your report. Turn it off with /forever debug off."
L["Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."] =
	"Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."
L["Debug capture is off and the client's settings are back; the debug log is off and unpinned."] =
	"Debug capture is off and the client's settings are back; the debug log is off and unpinned."
L["Debug capture could not start because ForeverCore has not finished loading."] =
	"Debug capture could not start because ForeverCore has not finished loading."
L["%s: the installed ForeverCore is another addon (%s). Remove it and install ForeverCore from CurseForge."] =
	"%s: the installed ForeverCore is another addon (%s). Remove it and install ForeverCore from CurseForge."
L["%s needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app."] =
	"%s needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app."
L["%s: ForeverCore is turned off. Enable it in the AddOns list to fix this."] =
	"%s: ForeverCore is turned off. Enable it in the AddOns list to fix this."
L["Feature request"] = "Feature request"
L["Feature request: "] = "Feature request: "
L["ForeverCore"] = "ForeverCore"
L["Forever addons"] = "Forever addons"
L["Hide this section"] = "Hide this section"
L["Inspired by"] = "Inspired by"
L["Lock the tracker"] = "Lock the tracker"
L["Last"] = "Last"
L["Memory KB"] = "Memory KB"
L["Memory: not available on this client."] = "Memory: not available on this client."
L["No addon has attached its log yet."] = "No addon has attached its log yet."
L["No one is listed yet."] = "No one is listed yet."
L["On"] = "On"
L["Peak"] = "Peak"
L["Performance (read when this window opened):"] = "Performance (read when this window opened):"
L["Performance: not available on this client."] = "Performance: not available on this client."
L["Performance: the client's add-on profiler is off."] = "Performance: the client's add-on profiler is off."
L["Players"] = "Players"
L["Recent"] = "Recent"
L["Report a bug or request a feature"] = "Report a bug or request a feature"
L["Session"] = "Session"
L["Thanks"] = "Thanks"
L["Thanks to %s"] = "Thanks to %s"
L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."] =
	"The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."
L["The players who helped each Forever addon."] = "The players who helped each Forever addon."
L["The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."] =
	"The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."
L["Title"] = "Title"
L["Tracker background"] = "Tracker background"
L["Tracker position"] = "Tracker position"
L["Under the quest tracker"] = "Under the quest tracker"
L["Left of the quest tracker"] = "Left of the quest tracker"
L["Attach to quest tracker"] = "Attach to quest tracker"
L["The shared Forever tracker sits under the quest tracker when this is on, and left of it when it is off. Every Forever addon shows this same setting."] =
	"The shared Forever tracker sits under the quest tracker when this is on, and left of it when it is off. Every Forever addon shows this same setting."
L["Tracker"] = "Tracker"
L["Click to %s"] = "Click to %s"
L["Right-click for options"] = "Right-click for options"
L["Unavailable in combat"] = "Unavailable in combat"
L["Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"] =
	"Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"
L["What happened, or what you would like"] = "What happened, or what you would like"
L["Quests"] = "Quests"

L["ForeverCore startup report"] = "ForeverCore startup report"
L["Core: %s; API %s"] = "Core: %s; API %s"
L["Runtime: %s copy %s"] = "Runtime: %s copy %s"
L["Runtime error: %s"] = "Runtime error: %s"
L["Standalone runtime"] = "Standalone runtime"
L["Core copies:"] = "Core copies:"
L["Rejected"] = "Rejected"
L["Sealed"] = "Sealed"
L["Unsealed"] = "Unsealed"
L["%s: build %s, %s"] = "%s: build %s, %s"
L['No installed Forever addon named "%s".'] = 'No installed Forever addon named "%s".'
L["No installed Forever addons found."] = "No installed Forever addons found."
L["Enable ForeverCore or a Forever addon in AddOns if /fcore is unavailable, then /reload and read Lua errors."] =
	"Enable ForeverCore or a Forever addon in AddOns if /fcore is unavailable, then /reload and read Lua errors."
L["Installed Forever addons:"] = "Installed Forever addons:"
L["Registered"] = "Registered"
L["Loaded but not registered"] = "Loaded but not registered"
L["Not loaded"] = "Not loaded"
L["Load: %s; enabled: %s; core pin: %s"] = "Load: %s; enabled: %s; core pin: %s"
L["Requires: %s; optional: %s"] = "Requires: %s; optional: %s"
L["Loadable: %s; reason: %s"] = "Loadable: %s; reason: %s"
L["First error: %s"] = "First error: %s"
L["No error captured. Use /console scriptErrors 1, then /reload and read the first error naming %s."] =
	"No error captured. Use /console scriptErrors 1, then /reload and read the first error naming %s."
L["Callback error: %s"] = "Callback error: %s"
L["Login error: %s"] = "Login error: %s"
L["Warning: %s"] = "Warning: %s"
L["Copy %s: %s"] = "Copy %s: %s"

L["Drag to move the tabs."] = "Drag to move the tabs."
L["Reset tab position"] = "Reset tab position"
