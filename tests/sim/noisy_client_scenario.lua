-- luacheck: read globals scenario ADDON
-- The noisy client raises the item, bag and merchant traffic a live client sends unasked: seeded, so the same seed
-- gives the same stream, with failed loads among it, merchant updates only while the merchant is open, and every event
-- measured by the work counter, so a consumer spec can assert its handlers' work per event stays flat as the noise
-- runs on.
local function run(sim, seconds)
	sim.work.reset()
	sim:advance(seconds)
	local fired = {}
	for event, n in pairs(sim.noise.fired) do
		fired[event] = n
	end
	return fired
end

scenario("the noisy client raises seeded item, bag and merchant traffic", function(sim)
	local G = sim.G
	sim.world.items[2589] = { name = "Linen Cloth" }
	sim.world.items[2592] = { name = "Wool Cloth" }
	sim:login()
	sim:runAs(
		ADDON,
		[[
		local seen = { failed = 0, loaded = 0, merchant = 0 }
		_G.NoisyClientScenarioSeen = seen
		local f = CreateFrame("Frame")
		f:RegisterEvent("ITEM_DATA_LOAD_RESULT")
		f:RegisterEvent("MERCHANT_UPDATE")
		f:RegisterEvent("BAG_UPDATE_DELAYED")
		f:SetScript("OnEvent", function(_, event, itemID, success)
			if event == "ITEM_DATA_LOAD_RESULT" then
				if success then
					seen.loaded = seen.loaded + 1
				else
					seen.failed = seen.failed + 1
				end
			elseif event == "MERCHANT_UPDATE" then
				seen.merchant = seen.merchant + 1
			end
		end)
	]]
	)
	local seen = G.NoisyClientScenarioSeen

	sim:noisy({ seed = 7 })
	local first = run(sim, 2)
	assert(first.GET_ITEM_INFO_RECEIVED == first.ITEM_DATA_LOAD_RESULT, "each item event comes as a pair")
	assert(first.ITEM_DATA_LOAD_RESULT >= 2 * 20 * 4, "four items a frame for two seconds")
	assert(first.BAG_UPDATE > 0 and first.BAG_UPDATE_DELAYED > 0, "bags churn")
	assert(not first.MERCHANT_UPDATE, "no merchant updates while the merchant is closed")
	assert(seen.failed > 0 and seen.loaded > 0, "some loads fail and some succeed")
	assert(seen.merchant == 0, "no merchant update reached the addon")

	-- The work counter saw every noisy event, with one handler of ours for each.
	local loads = sim.work.paths.ITEM_DATA_LOAD_RESULT
	assert(loads and loads.runs == first.ITEM_DATA_LOAD_RESULT, "each load result is measured")
	assert(loads.maxHandlers >= 1, "our handler ran for the load results")

	-- The same seed replays the same stream.
	sim:noisy({ seed = 7 })
	local again = run(sim, 2)
	for event, n in pairs(first) do
		assert(again[event] == n, event .. " replays with the same seed")
	end

	-- With the merchant open, MERCHANT_UPDATE joins the churn.
	sim:openMerchant()
	sim:noisy({ seed = 3 })
	local shop = run(sim, 2)
	assert(shop.MERCHANT_UPDATE and shop.MERCHANT_UPDATE > 0, "the merchant churns while open")
	assert(seen.merchant > 0, "our handler saw the merchant updates")
	sim:closeMerchant()

	-- A requested load of a known item fails at the noise's rate, and always loads with the noise off.
	sim:noisy({ seed = 5, itemsPerFrame = 0, bagPercent = 0, failPercent = 100 })
	local before = seen.failed
	sim:runAs(ADDON, "C_Item.RequestLoadItemDataByID(2589)")
	sim:advance(0.1)
	assert(seen.failed == before + 1, "a requested load can fail")
	sim:noisy(false)
	local loaded = seen.loaded
	sim:runAs(ADDON, "C_Item.RequestLoadItemDataByID(2589)")
	sim:advance(0.1)
	assert(seen.loaded == loaded + 1 and seen.failed == before + 1, "without noise the load succeeds")
	sim:expectNoErrors(ADDON)
end)
