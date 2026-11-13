local _, ns = ...

-- Forever Leaderboards and peer stats are gone. This file exists only because older addon releases still call their
-- old public entry points unguarded while the player's other Forever addons load: Shortest Path Forever v1.33.1 runs
-- ForeverCore.Leaderboards:Register("spf", {}), ForeverCore.Leaderboards:Open("spf") and
-- ForeverCore.PeerStats.New({}), then calls Shared, Board, WeekBoard, Revision, Sync and SetEnabled on the result.
-- Older Legacy, Commissions and Field Guide releases may call the same. A nil index here is a Lua error at login,
-- so every call is answered with an empty board or a no-op. Nothing is stored, no addon message prefix is
-- registered and nothing is sent. Remove this file once no supported release calls these members.

local Leaderboards = {}

function Leaderboards.Register() end
function Leaderboards.Open() end
function Leaderboards.Select() end
function Leaderboards.Toggle() end

---@return table
function Leaderboards.Boards()
	return {}
end

---@return table
function Leaderboards.Overall()
	return {}
end

---@return nil
function Leaderboards.Standing()
	return nil
end

local Peer = {}
Peer.__index = Peer

---@return table
function Peer.Shared()
	return {}
end

---@return table
function Peer.Board()
	return {}
end

---@return table
function Peer.WeekBoard()
	return {}
end

---@return integer
function Peer.Revision()
	return 0
end

---@return boolean
function Peer.IsEnabled()
	return false
end

function Peer.Sync() end
function Peer.SetEnabled() end
function Peer.Cancel() end
function Peer.Retire() end
function Peer.Receive() end
function Peer.RecordSent() end

local PeerStats = {}

---@return table
function PeerStats.New()
	return setmetatable({}, Peer)
end

-- Field Guide releases read peer rows through Listen rather than New, and an inert reader keeps that load error-free.
---@return table
function PeerStats.Listen()
	return setmetatable({}, Peer)
end

ns.RetiredLeaderboards = Leaderboards
ns.RetiredPeerStats = PeerStats
