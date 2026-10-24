-- Generates the client's C_* namespaces, global API functions, Enum and Constants from
-- Blizzard_APIDocumentationGenerated, so every stub has the client's name, arguments, return shape and flags.
--
-- A stub answers from the scenario's implementation (sim.impl["C_Map.GetBestMapForUnit"] or sim.impl.UnitName),
-- else with the documented type's zero value. On top of either it applies the documentation's rules:
--   * secret arguments (NotAllowed, or AllowedWhenUntainted from tainted code) raise the client's error;
--   * SecretReturns, and the SecretWhen* predicates while their restriction is active, return secrets;
--   * protected functions called from tainted code are forbidden (ADDON_ACTION_FORBIDDEN);
--   * from tainted code, a missing non-nilable argument raises the client's usage error.
local Secret = require("veil")

local M = {}

local NUMBER_TYPES = {
	number = true,
	luaIndex = true,
	uiUnit = true,
	size = true,
	time_t = true,
	BigUInteger = true,
	BigInteger = true,
	normalizedValue = true,
	fileID = true,
	SingleColorValue = true,
	WOWMONEY = true,
	uiMapID = true,
	DurationSeconds = true,
}
local STRING_TYPES = {
	string = true,
	cstring = true,
	WOWGUID = true,
	UnitToken = true,
	ClubId = true,
	textureAtlas = true,
	kstringClubMessage = true,
	mouseButton = true,
	FramePoint = true,
	CScriptObject = false,
}
M.NUMBER_TYPES = NUMBER_TYPES

-- Which restriction each SecretWhen* predicate follows. `unit` means: only for units other than the player.
local PREDICATES = {
	SecretWhenInCombat = { "combat" },
	SecretWhenUnitIdentityRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitNameIdentityRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitStatsRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitAuraRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitSpellCastRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitPowerRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitPowerMaxRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitHealthMaxRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitThreatStateRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitThreatValuesRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitPossessionRestricted = { "unitRestricted", unit = true },
	SecretWhenUnitComparisonRestricted = { "unitRestricted", unit = true },
	SecretWhenCooldownsRestricted = { "combat" },
	SecretWhenAurasRestricted = { "combat" },
	SecretWhenLossOfControlInfoRestricted = { "combat" },
	SecretWhenTotemSlotSecret = { "combat" },
	SecretWhenEncounterEvent = { "encounter" },
	SecretInChatMessagingLockdown = { "chatLockdown" },
	SecretOnRestrictedMaps = { "restrictedMap" },
	SecretInActivePvPMatch = { "pvp" },
}
M.PREDICATES = PREDICATES

function M.build(sim)
	local G, Taint, docs = sim.G, sim.taint, sim.docs
	local A = { functions = {}, byName = {} }
	sim.api = A
	sim.impl = sim.impl or {}

	-- Enum and Constants. The client defines more enums than it documents; client code reading an undocumented
	-- one gets a table of distinct values (recorded in sim.gaps), addon code gets nil as for any missing global.
	sim.gaps = sim.gaps or {}
	local autoValue = 100000
	local function autoEnum(name)
		return setmetatable({}, {
			__index = function(t, k)
				if Taint.current then
					return nil
				end
				autoValue = autoValue + 1
				rawset(t, k, autoValue)
				sim.gaps["Enum." .. name .. "." .. tostring(k)] = true
				return autoValue
			end,
		})
	end
	G.Enum = setmetatable(G.Enum or {}, {
		__index = function(t, k)
			if Taint.current or type(k) ~= "string" then
				return nil
			end
			local e = autoEnum(k)
			rawset(t, k, e)
			sim.gaps["Enum." .. k] = true
			return e
		end,
	})
	for name, e in pairs(docs.enums) do
		local t = {}
		for _, f in ipairs(e.Fields or {}) do
			t[f.Name] = f.EnumValue
		end
		G.Enum[name] = t
		local meta = { MinValue = e.MinValue, MaxValue = e.MaxValue, NumValues = e.NumValues }
		G.Enum[name .. "Meta"] = meta
	end
	G.Constants = setmetatable(G.Constants or {}, {
		__index = function(t, k)
			if Taint.current or type(k) ~= "string" then
				return nil
			end
			local c = autoEnum(k)
			rawset(t, k, c)
			sim.gaps["Constants." .. k] = true
			return c
		end,
	})
	for name, c in pairs(docs.constants) do
		local t = autoEnum(name)
		for _, v in ipairs(c.Values or {}) do
			if type(v.Value) ~= "table" then
				t[v.Name] = v.Value
			end
		end
		G.Constants[name] = t
	end

	local zero
	local function zeroPlain(ret, depth)
		if ret.Nilable then
			return nil
		end
		local t = ret.Type
		if t == "bool" then
			return false
		elseif NUMBER_TYPES[t] then
			return 0
		elseif STRING_TYPES[t] then
			return ""
		elseif t == "table" then
			return {}
		elseif docs.enums[t] then
			local e = docs.enums[t]
			return e.Fields and e.Fields[1] and e.Fields[1].EnumValue or 0
		elseif docs.widgets[t .. "API"] then
			return A.scriptObject(t)
		elseif docs.structures[t] and (depth or 0) < 3 then
			local out = {}
			for _, field in ipairs(docs.structures[t].Fields or {}) do
				out[field.Name] = zero(field, (depth or 0) + 1)
			end
			return out
		end
		return nil
	end
	zero = function(ret, depth)
		local v = zeroPlain(ret, depth)
		if ret.Mixin and not ret.Nilable and type(G[ret.Mixin]) == "table" then
			v = type(v) == "table" and v or {}
			G.Mixin(v, G[ret.Mixin])
		end
		return v
	end
	A.zero = zero

	-- A documented script object (LuaDurationObject, NumericFormatter...): its documented methods, setters stored
	-- for their getters, everything else the zero value.
	local objectMetas = {}
	function A.scriptObject(t)
		local meta = objectMetas[t]
		if not meta then
			local methods = {}
			for _, sys in ipairs({ t .. "BaseAPI", t .. "API" }) do
				for _, f in ipairs(docs.widgets[sys] and docs.widgets[sys].Functions or {}) do
					local rest = f.Name:match("^Set(.+)$")
					local getRest = f.Name:match("^Get(.+)$") or f.Name:match("^Is(.+)$")
					methods[f.Name] = function(self, ...)
						if rest then
							self._props[rest] = { n = select("#", ...), ... }
							return
						end
						local stored = getRest and self._props[getRest]
						if stored then
							return unpack(stored, 1, stored.n)
						end
						local out = {}
						for i, r in ipairs(f.Returns or {}) do
							out[i] = zero(r, 3)
						end
						return unpack(out, 1, #(f.Returns or {}))
					end
				end
			end
			meta = { __index = methods }
			objectMetas[t] = meta
		end
		return setmetatable({ _props = {} }, meta)
	end

	local function unitArg(fdoc, args)
		for i, a in ipairs(fdoc.Arguments or {}) do
			if
				a.Name == "unit"
				or a.Name == "unitToken"
				or a.Name == "unitGUID"
				or (a.Type or ""):find("^UnitToken")
			then
				return args[i]
			end
		end
	end

	local function secretNow(fdoc, args)
		if fdoc.SecretReturns then
			return true
		end
		local r = sim.restrictions
		for key, rule in pairs(PREDICATES) do
			if fdoc[key] then
				local active = r[rule[1]]
				if rule[1] == "unitRestricted" then
					active = sim.inCombat or r.restrictedMap or r.unitRestricted
				end
				if active then
					if not rule.unit then
						return true
					end
					local unit = Secret.unwrap(unitArg(fdoc, args))
					if unit ~= "player" then
						return true
					end
				end
			end
		end
		return false
	end
	A.secretNow = secretNow

	local function usage(qualified, fdoc)
		local names = {}
		for _, a in ipairs(fdoc.Arguments or {}) do
			names[#names + 1] = a.Nilable and ("[" .. a.Name .. "]") or a.Name
		end
		return string.format("Usage: %s(%s)", qualified, table.concat(names, ", "))
	end

	local protectedNames = {}
	for _, name in ipairs(sim.protectedGlobals or {}) do
		protectedNames[name] = true
	end

	local function stub(qualified, fdoc)
		local nargs = #(fdoc.Arguments or {})
		local protected = fdoc.IsProtectedFunction or protectedNames[qualified]
		local secretArgs = fdoc.SecretArguments
		local returns = fdoc.Returns or {}
		local f = function(...)
			local args = { ... }
			local tainted = Taint.current
			if tainted then
				for i, a in ipairs(fdoc.Arguments or {}) do
					local v = args[i]
					if v == nil and not a.Nilable and a.Default == nil and not (a.Type or ""):match("^LuaValue") then
						error(usage(qualified, fdoc), 2)
					end
					if NUMBER_TYPES[a.Type] and v ~= nil and not Secret.is(v) and tonumber(v) == nil then
						error(usage(qualified, fdoc), 2)
					end
				end
			end
			if secretArgs == "NotAllowed" or (secretArgs == "AllowedWhenUntainted" and tainted) then
				for i = 1, math.max(nargs, select("#", ...)) do
					local a = fdoc.Arguments and fdoc.Arguments[i] or (fdoc.Arguments and fdoc.Arguments[nargs])
					-- Type-erased value arguments (issecretvalue's) take any value, secrets included.
					local erased = a and ((a.Type or ""):match("^LuaValue") or a.Type == "any")
					if Secret.is(args[i]) and not erased then
						error(
							string.format(
								"bad argument #%d to '%s' (secret values are not allowed%s)",
								i,
								qualified,
								tainted and string.format("; execution tainted by '%s'", tainted) or ""
							),
							2
						)
					end
				end
			end
			if protected and tainted then
				sim.forbidden(qualified)
				return
			end
			local impl = sim.impl[qualified]
			local out
			if impl then
				out = { n = 0 }
				local r = { impl(...) }
				out.n = table.maxn(r)
				for i = 1, out.n do
					out[i] = r[i]
				end
			else
				out = { n = 0 }
				for i, r in ipairs(returns) do
					if r.StrideIndex then
						break
					end
					out[i] = zero(r)
					out.n = i
				end
			end
			if secretNow(fdoc, args) then
				for i = 1, out.n do
					local r = returns[i]
					if not (r and r.ConditionalSecret == false) then
						out[i] = Secret.wrap(out[i])
					end
				end
			end
			return unpack(out, 1, out.n)
		end
		A.functions[qualified] = { doc = fdoc, fn = f }
		return f
	end

	for _, system in ipairs(docs.systems) do
		local ns = system.Namespace
		local target = G
		if ns then
			G[ns] = G[ns] or {}
			target = G[ns]
		end
		for _, fdoc in ipairs(system.Functions or {}) do
			local qualified = ns and (ns .. "." .. fdoc.Name) or fdoc.Name
			-- A native the sim already provides answers the stub, which still applies the documented rules.
			local existing = rawget(target, fdoc.Name)
			if type(existing) == "function" and not sim.impl[qualified] then
				sim.impl[qualified] = existing
			end
			target[fdoc.Name] = stub(qualified, fdoc)
			A.byName[qualified] = fdoc
		end
	end

	-- Protected globals the documentation does not list still block tainted callers.
	for name in pairs(protectedNames) do
		if not A.byName[name] then
			G[name] = stub(name, { Name = name, Arguments = {}, Returns = {} })
		end
	end

	-- C_* functions Blizzard's Lua calls that the documentation leaves out (fetch.py lists them): the client has
	-- them, so they exist here and answer nothing unless a scenario implements them.
	local file = loadfile(sim.dataDir .. "/api-calls.lua")
	local scanned = file and file() or {}
	A.blizzardEvents = {}
	for _, e in ipairs(scanned.events or {}) do
		A.blizzardEvents[e] = true
	end
	for _, qualified in ipairs(scanned.calls or {}) do
		local ns, name = qualified:match("^([^.]+)%.(.+)$")
		G[ns] = G[ns] or {}
		if G[ns][name] == nil then
			local q = qualified
			-- With no documentation, the name says the likely shape: counts are numbers, predicates booleans.
			local default
			if name:match("^GetNum") or name:match("Count$") then
				default = 0
			elseif name:match("^Is") or name:match("^Has") or name:match("^Can") or name:match("^Should") then
				default = false
			end
			G[ns][name] = function(...)
				local f = sim.impl[q]
				if f then
					return f(...)
				end
				return default
			end
			A.undocumented = (A.undocumented or 0) + 1
		end
	end

	-- Every documented event, for RegisterEvent's check.
	A.events = {}
	for name in pairs(docs.events) do
		A.events[name] = true
	end
	return A
end

return M
