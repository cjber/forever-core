-- ForeverCore's own public API, published to the suite's list like every addon's (docs/api-conventions.md). The
-- `ForeverCore.API` field stays the interface number it always was, because every released addon compares it as a
-- number; the table callers read through `ForeverCore.APIKit.Addons()` carries the same number as `version`.

local _, ns = ...

-- `version` is the interface number (docs/api.md); `minor` is the core table's own minor.
local API = { version = 2, minor = 2 }

-- Whether an addon reached Register; Expose.lua defines it once the contexts exist.
---@param addonName string
---@return boolean
function API.Registered(addonName)
	return ns.Registered(addonName)
end

API.Open = ns.Open

ns.CoreAPI = API
ns.APIKit.Publish("ForeverCore", API)
