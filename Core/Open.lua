local _, ns = ...

---@class ForeverCoreOpener
---@field callback ForeverCoreOpenCallback
---@field secure boolean
---@type table<string, ForeverCoreOpener>
local openers = {}

-- Shared by direct opens and tracker actions. Reasons are already localized by their producer.
function ns.ReportRefusal(reason)
	if reason and DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
		DEFAULT_CHAT_FRAME:AddMessage(tostring(reason))
	end
end

---@param addon string
---@param callback fun(where: any): boolean?, string?
---@param secure? boolean
function ns.RegisterOpener(addon, callback, secure)
	if type(callback) ~= "function" then
		error("ForeverCore.Register: open must be a function", 2)
	end
	openers[addon] = { callback = callback, secure = secure == true }
end

---@param addon string
---@param where? any
---@return boolean?, string?
function ns.Open(addon, where)
	if type(addon) ~= "string" or addon == "" then
		return ns.APIKit.Invalid()
	end
	local opener = openers[addon]
	if not opener then
		return ns.APIKit.NotReady("none")
	end
	if opener.secure and InCombatLockdown() then
		local reason = ns.L["Unavailable in combat"]
		ns.ReportRefusal(reason)
		return false, reason
	end
	local ok, accepted, reason = ns.SafeCallFor(addon):SafeCall("open panel", opener.callback, where)
	if not ok then
		return false
	end
	if accepted ~= true then
		ns.ReportRefusal(reason)
	end
	return accepted, reason
end
