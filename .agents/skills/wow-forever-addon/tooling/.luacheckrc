-- forever_sim and its specs. The fixture addons run in the simulated client, with its globals.
std = "lua51"
max_line_length = 120
files["tests/sim/fixtures"] = {
	allow_defined_top = true,
	globals = { "SimTrackerDB", "SimSecureFrame" },
	read_globals = {
		"CreateFrame",
		"CreateFromMixins",
		"C_Timer",
		"EventRegistry",
		"EventUtil",
		"GameTooltip",
		"GameTooltip_AddNormalLine",
		"GameTooltip_InsertFrame",
		"GameTooltip_SetTitle",
		"MapCanvasDataProviderMixin",
		"UIParent",
		"WorldMapFrame",
		"_G",
	},
}
