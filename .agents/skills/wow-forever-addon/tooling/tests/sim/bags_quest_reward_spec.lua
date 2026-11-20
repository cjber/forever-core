-- Issue #927: bag contents and the quest giver's reward panel, with every item answered from the client's own data.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new({ addon = false })
sim:login()
local G = sim.G

local LINEN, PANTS, SHORTSWORD, STAFF, HEARTHSTONE = 2589, 39, 25, 35, 6948

-- Items come from the client's Item and ItemSparse rows, not from the scenario.
local name, link, quality, _, _, _, _, stack, _, _, sell = G.C_Item.GetItemInfo(LINEN)
assert(name == "Linen Cloth" and quality == 1 and sell == 13 and stack == 20, "Linen Cloth from client data")
assert(link:find("|Hitem:2589:", 1, true) and link:find("[Linen Cloth]", 1, true), "an item link the client's shape")
assert(select(9, G.C_Item.GetItemInfo(SHORTSWORD)) == "INVTYPE_WEAPONMAINHAND", "equip slot from InventoryType")
assert(G.C_Item.GetItemInfo(999999) == nil, "an item the client has no row for does not exist")
assert(not pcall(sim.putInBag, sim, 0, 1, 999999), "a bag cannot hold an item no client data has")

-- Bags: what a slot holds, and BAG_UPDATE for the bag that changed.
local seen = {}
sim.run(function()
	local f = G.CreateFrame("Frame")
	f:RegisterEvent("BAG_UPDATE")
	f:RegisterEvent("BAG_UPDATE_DELAYED")
	f:SetScript("OnEvent", function(_, event, bag)
		seen[#seen + 1] = event .. (bag and (":" .. bag) or "")
	end)
end)
sim:putInBag(0, 1, LINEN, 5)
sim:putInBag(0, 2, PANTS, 1)
assert(seen[1] == "BAG_UPDATE:0" and seen[2] == "BAG_UPDATE_DELAYED", "BAG_UPDATE for the backpack, then DELAYED")
assert(
	G.C_Container.GetContainerNumSlots(0) == 16 and G.C_Container.GetContainerNumFreeSlots(0) == 14,
	"16 slots, 2 used"
)
local info = G.C_Container.GetContainerItemInfo(0, 2)
assert(info.itemID == PANTS and info.quality == 0 and info.stackCount == 1, "a grey item in slot 2")
assert(G.C_Container.GetContainerItemID(0, 1) == LINEN and G.C_Item.GetItemCount(LINEN) == 5, "five Linen Cloth held")
assert(G.C_Container.GetContainerItemInfo(0, 3) == nil, "an empty slot")

-- Selling junk at a merchant: the slot empties and the sell price is paid.
sim:openMerchant()
local money = G.GetMoney()
sim.run(function()
	G.C_Container.UseContainerItem(0, 2)
end)
assert(G.C_Container.GetContainerItemInfo(0, 2) == nil and G.GetMoney() == money + 1, "the grey item sold for 1c")
sim:closeMerchant()
sim:expectNoErrors()

-- The quest reward panel: two choices and a fixed reward, drawn by the client's QuestInfo.
sim:openQuestReward(1234, { title = "A Test", choices = { SHORTSWORD, STAFF }, rewards = { HEARTHSTONE }, money = 50 })
assert(G.QuestFrame:IsShown() and G.QuestFrameRewardPanel:IsShown(), "the reward panel shows")
assert(G.GetNumQuestChoices() == 2 and G.GetNumQuestRewards() == 1, "two choices, one fixed reward")
local choiceName, _, count, choiceQuality, _, itemID = G.GetQuestItemInfo("choice", 2)
assert(choiceName == "Bent Staff" and count == 1 and choiceQuality == 1 and itemID == STAFF, "the second choice")
assert(G.GetQuestItemLink("choice", 1):find("[Worn Shortsword]", 1, true), "a choice's link")
local drawn = {}
for i = 1, 3 do
	local button = G["QuestInfoRewardsFrameQuestInfoItem" .. i]
	drawn[i] = button:IsShown() and button.type .. ":" .. button.Name:GetText()
end
assert(
	table.concat(drawn, ",") == "choice:Worn Shortsword,choice:Bent Staff,reward:Hearthstone",
	"the client's QuestInfo draws each reward: " .. table.concat(drawn, ",")
)
sim:expectNoErrors()
money = G.GetMoney()
sim:completeQuestReward(2)
assert(not G.QuestFrame:IsShown(), "turning the quest in closes the quest frame")
assert(
	G.C_Item.GetItemCount(STAFF) == 1 and G.C_Item.GetItemCount(HEARTHSTONE) == 1,
	"the choice and reward are in the bags"
)
assert(G.C_Item.GetItemCount(SHORTSWORD) == 0 and G.GetMoney() == money + 50, "only the chosen item, plus the money")
sim:expectNoErrors()
print("bags_quest_reward_spec: passed")
