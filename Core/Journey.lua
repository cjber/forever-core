local _, ns = ...

local Journey = { minor = 1 }
---@type { addon: string, label: string, finish: fun(reason: string) }?
local current
local revision = 0
local hub = ns.APIKit.Hub("ForeverCore", {
	journey = function()
		return revision
	end,
})
local function Changed()
	revision = revision + 1
	hub.Queue()
end

---@param addon string
---@param label string
---@param finish fun(reason: string)
---@return boolean?, string?
function Journey.Claim(addon, label, finish)
	if
		type(addon) ~= "string"
		or addon == ""
		or type(label) ~= "string"
		or label == ""
		or type(finish) ~= "function"
	then
		return ns.APIKit.Invalid()
	end
	local previous = current
	current = { addon = addon, label = label, finish = finish }
	Changed()
	if previous and previous.addon ~= addon then
		ns.SafeCallFor(previous.addon):SafeCall("replace journey", previous.finish, "replaced")
	end
	return true
end

---@return string?, string?
function Journey.Owner()
	if current then
		return current.addon, current.label
	end
	return ns.APIKit.NotReady("none")
end

---@param owner? string
---@return boolean?, string?
function Journey.End(owner)
	if owner ~= nil and (type(owner) ~= "string" or owner == "") then
		return ns.APIKit.Invalid()
	end
	if not current then
		return ns.APIKit.NotReady("none")
	end
	if owner ~= nil and owner ~= current.addon then
		return ns.APIKit.Invalid()
	end
	local previous = current
	current = nil
	Changed()
	local ok = ns.SafeCallFor(previous.addon):SafeCall("end journey", previous.finish, "ended")
	return ok
end

---@param addon string
---@return boolean?, string?
function Journey.Release(addon)
	if type(addon) ~= "string" or addon == "" then
		return ns.APIKit.Invalid()
	end
	if not current or current.addon ~= addon then
		return false
	end
	current = nil
	Changed()
	return true
end

---@param callback fun(changes: ForeverCoreAPIChanges)
---@return fun()
function Journey.Subscribe(callback)
	return hub.Subscribe(callback)
end

ns.Journey = Journey
