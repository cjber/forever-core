-- luacheck: globals Auctionator, read globals FOREVER_SIM_STUBS
-- A stand-in for Auctionator's public API v1, written for forever_sim from its documented calls (no Auctionator
-- code). FOREVER_SIM_STUBS.Auctionator may set prices = { [itemID] = copper } and ages = { [itemID] = days }.
local options = (FOREVER_SIM_STUBS and FOREVER_SIM_STUBS.Auctionator) or {}
local prices, ages = options.prices or {}, options.ages or {}
local listeners = {}

Auctionator = { API = { v1 = {} } }
local v1 = Auctionator.API.v1

local function CheckCaller(caller)
	if type(caller) ~= "string" or caller == "" then
		error("Auctionator API: a caller name is required", 3)
	end
end

function v1.GetAuctionPriceByItemID(caller, itemID)
	CheckCaller(caller)
	return prices[itemID]
end

function v1.GetAuctionPriceByItemLink(caller, link)
	CheckCaller(caller)
	local id = tonumber(tostring(link):match("item:(%d+)"))
	return id and prices[id]
end

function v1.GetAuctionAgeByItemID(caller, itemID)
	CheckCaller(caller)
	return ages[itemID]
end

function v1.RegisterForDBUpdate(caller, callback)
	CheckCaller(caller)
	listeners[#listeners + 1] = callback
end

function v1.MultiSearchExact(caller, terms)
	CheckCaller(caller)
	Auctionator.lastSearch = terms
end

function v1.MultiSearchAdvanced(caller, terms)
	CheckCaller(caller)
	Auctionator.lastSearch = terms
end

function v1.CreateShoppingList(caller, name, searches)
	CheckCaller(caller)
	Auctionator.shoppingLists = Auctionator.shoppingLists or {}
	Auctionator.shoppingLists[name] = searches
end

function v1.ConvertToSearchString(caller, term)
	CheckCaller(caller)
	return type(term) == "table" and (term.searchString or "") or tostring(term)
end
