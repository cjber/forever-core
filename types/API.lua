---@meta

-- ForeverCore's own published API, version 2, minor 3 (docs/api.md). Core/API.lua implements it and publishes it
-- through ForeverCore.APIKit.Publish as "ForeverCore".

---@class ForeverCorePublishedAPI
---@field version integer the interface number, the same as ForeverCore.API
---@field minor integer the core table's own minor, the same as ForeverCore.minor
---@field Registered fun(addonName: string): boolean whether that addon reached Register, so its files started
---@field Open fun(addon: string, where?: any): boolean?, string?
---@field CharacterKey fun(): string? the key per-character saved data is filed under; nil until the client knows
