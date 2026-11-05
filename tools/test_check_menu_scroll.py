"""Tests for tools/check_menu_scroll.py: menus built from a list must scroll."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import check_menu_scroll


def lines(source):
    """Finding lines and the rule each names."""
    return [(line, message.split(":", 1)[0]) for line, message in check_menu_scroll.check(source)]


class MenuScrollTest(unittest.TestCase):
    def test_root_filled_in_a_loop_fails(self):
        source = """
MenuUtil.CreateContextMenu(owner, function(_, root)
	root:CreateTitle("Zones")
	for _, zone in ipairs(ns.Zones) do
		root:CreateRadio(zone.name, IsZone, SetZone, zone)
	end
end)
"""
        findings = check_menu_scroll.check(source)
        self.assertEqual([line for line, _ in findings], [5])
        self.assertIn("root gets entries through :CreateRadio(...) in the loop at line 4", findings[0][1])
        self.assertIn("root:SetScrollMode(extent)", findings[0][1])

    def test_scrolled_root_passes(self):
        source = """
MenuUtil.CreateContextMenu(owner, function(_, root)
	root:SetScrollMode(MENU_EXTENT)
	for _, zone in ipairs(ns.Zones) do
		root:CreateRadio(zone.name, IsZone, SetZone, zone)
	end
end)
"""
        self.assertEqual(lines(source), [])

    def test_shortest_path_359_shape_passes(self):
        # cjber/shortest-path-forever#359, UI/Nearby.lua: the specialty submenu scrolls; the submenu is made once per
        # call, so the caller's root gets one entry from it.
        source = """
local MENU_ROW, MENU_ROWS = 20, 20
local function AddService(root, service, world)
	local place = world and Nearest(service.key, world)
	if service.hasSpecialties and place then
		local submenu = root:CreateButton(service.label)
		submenu:SetScrollMode(MENU_ROW * MENU_ROWS)
		for _, specialty in ipairs(SpecialtyNames(service.key, world)) do
			local specialist = Nearest(service.key, world, specialty)
			submenu:CreateButton(specialty, function()
				return Pick(service.key, specialist)
			end)
		end
		submenu:CreateButton(L["Nearest"], function()
			return Pick(service.key, place)
		end)
		return
	end
	local entry = root:CreateButton(service.label, function()
		return Pick(service.key, place)
	end)
	entry:SetEnabled(place ~= nil)
end
"""
        self.assertEqual(lines(source), [])

    def test_shortest_path_before_359_fails(self):
        source = """
local function AddService(root, service, world)
	local submenu = root:CreateButton(service.label)
	for _, specialty in ipairs(SpecialtyNames(service.key, world)) do
		submenu:CreateButton(specialty)
	end
end
"""
        self.assertEqual(lines(source), [(5, "menu-scroll")])

    def test_submenu_made_inside_the_loop_gets_its_own_entries_once(self):
        source = """
local function Fill(root)
	root:SetScrollMode(400)
	for _, boss in ipairs(bosses) do
		local drops = root:CreateButton(boss.name)
		drops:CreateTitle(boss.name)
		drops:CreateButton(L.GO)
	end
end
"""
        self.assertEqual(lines(source), [])

    def test_nested_submenus_each_need_their_own_scroll(self):
        source = """
local function AddUnlocated(root, tops)
	local submenu = root:CreateButton("No fixed location")
	submenu:SetScrollMode(400)
	for _, top in ipairs(tops) do
		local topMenu = submenu:CreateButton(top.name)
		for _, sub in ipairs(top.subs) do
			local subMenu = topMenu:CreateButton(sub.name)
			subMenu:SetScrollMode(400)
			for _, item in ipairs(sub.items) do
				subMenu:CreateCheckbox(item.name)
			end
		end
	end
end
"""
        findings = check_menu_scroll.check(source)
        self.assertEqual([line for line, _ in findings], [8])
        self.assertIn("topMenu gets entries", findings[0][1])

    def test_scroll_in_another_function_does_not_count(self):
        source = """
local function Scroll(menu)
	menu:SetScrollMode(400)
end
local function Fill(menu, items)
	for _, item in ipairs(items) do
		menu:CreateButton(item)
	end
end
"""
        self.assertEqual(lines(source), [(7, "menu-scroll")])

    def test_while_and_repeat_loops_count(self):
        source = """
local function Fill(menu, items)
	local i = 1
	while items[i] do
		menu:CreateButton(items[i])
		i = i + 1
	end
	repeat
		menu:CreateDivider()
	until true
end
"""
        self.assertEqual(lines(source), [(5, "menu-scroll")])

    def test_literal_lengths_pass(self):
        source = """
local function Fill(menu)
	for i = 1, 3 do
		menu:CreateButton(i)
	end
	for _, key in ipairs({ "a", "b" }) do
		menu:CreateButton(key)
	end
end
"""
        self.assertEqual(lines(source), [])

    def test_non_literal_bounds_fail(self):
        source = """
local function Fill(menu, items)
	for i = 1, #items do
		menu:CreateButton(items[i])
	end
end
"""
        self.assertEqual(lines(source), [(4, "menu-scroll")])

    def test_description_passed_to_a_helper_in_a_loop_fails(self):
        source = """
MenuUtil.CreateContextMenu(owner, function(_, root)
	for _, service in ipairs(services) do
		AddService(root, service)
	end
end)
"""
        findings = check_menu_scroll.check(source)
        self.assertEqual([line for line, _ in findings], [4])
        self.assertIn("a call that receives root", findings[0][1])

    def test_a_call_that_returns_runs_once(self):
        source = """
Menu.ModifyMenu("MENU_QUEST_OBJECTIVE_TRACKER", function(owner, root)
	for _, header in ipairs(GetMouseFoci()) do
		if header:GetParent() == owner then
			AddQuestMenuEntry(root, header.id)
			return
		end
	end
	for _, entry in ipairs(entries) do
		root:CreateButton(entry):SetEnabled(false)
		break
	end
end)
"""
        self.assertEqual(lines(source), [])

    def test_a_loop_outside_the_generator_does_not_count(self):
        source = """
for _, row in ipairs(rows) do
	row:SetScript("OnClick", function()
		MenuUtil.CreateContextMenu(row, function(_, root)
			root:CreateButton(row.text)
		end)
	end)
end
"""
        self.assertEqual(lines(source), [])

    def test_loop_variables_are_fresh_each_pass(self):
        source = """
local function Fill(menus)
	for _, menu in ipairs(menus) do
		menu:CreateButton("Go")
	end
end
"""
        self.assertEqual(lines(source), [])

    def test_a_reused_outer_variable_is_not_fresh(self):
        source = """
local function GuideChoices(choose, guides)
	choose:SetScrollMode(400)
	local group
	for _, guide in ipairs(guides) do
		if guide.first then
			group = choose:CreateButton(guide.group)
		end
		group:CreateButton(guide.name)
	end
end
"""
        self.assertEqual(lines(source), [(9, "menu-scroll")])

    def test_method_definitions_are_not_entries(self):
        source = """
function Description:CreateButton(text)
	for _, hook in ipairs(self.hooks) do
		hook(text)
	end
end
function Description:CreateTitle(text)
	return self:CreateButton(text)
end
"""
        self.assertEqual(lines(source), [])

    def test_suppression_with_a_reason_excuses_the_loop(self):
        source = """
local function AddModes(owner, root)
	-- menu-scroll-ok: SORT_OPTIONS holds four sort modes
	for _, option in ipairs(SORT_OPTIONS) do
		root:CreateRadio(option[2])
	end
	for _, filter in ipairs(FILTERS) do -- menu-scroll-ok: FILTERS is three fixed filters
		root:CreateRadio(filter.text)
	end
end
"""
        self.assertEqual(lines(source), [])

    def test_suppression_without_a_reason_fails(self):
        source = """
local function AddModes(owner, root)
	for _, option in ipairs(SORT_OPTIONS) do -- menu-scroll-ok: short
		root:CreateRadio(option[2])
	end
end
"""
        self.assertEqual(lines(source), [(3, "menu-scroll-unused"), (4, "menu-scroll")])

    def test_suppression_that_excuses_nothing_fails(self):
        source = """
local function Fill(root)
	-- menu-scroll-ok: the list of things stays short
	root:CreateButton("Go")
end
"""
        findings = check_menu_scroll.check(source)
        self.assertEqual([line for line, _ in findings], [3])
        self.assertIn("excuses no menu loop", findings[0][1])

    def test_legacy_dropdown_in_a_loop_fails(self):
        source = """
UIDropDownMenu_Initialize(dropdown, function(_, level)
	for _, choice in ipairs(choices) do
		local info = UIDropDownMenu_CreateInfo()
		info.text = choice[2]
		UIDropDownMenu_AddButton(info, level)
	end
	local info = UIDropDownMenu_CreateInfo()
	UIDropDownMenu_AddButton(info, level)
end)
"""
        findings = check_menu_scroll.check(source)
        self.assertEqual([line for line, _ in findings], [6])
        self.assertIn("cannot scroll", findings[0][1])

    def test_legacy_dropdown_suppression(self):
        source = """
UIDropDownMenu_Initialize(dropdown, function(_, level)
	-- menu-scroll-ok: CHOICES holds the three sizes
	for _, choice in ipairs(CHOICES) do
		UIDropDownMenu_AddButton(choice, level)
	end
end)
"""
        self.assertEqual(lines(source), [])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def test_addon_files_skip_tests_tools_types_libs_and_dot_folders(self):
        kept = [self.write("Core.lua", ""), self.write("UI/Menu.lua", "")]
        for skipped in ("tests/a_spec.lua", "tools/x.lua", "types/t.lua", "Libs/Lib/lib.lua", ".release/UI/Menu.lua"):
            self.write(skipped, "")
        self.assertEqual(check_menu_scroll.addon_files(self.root), sorted(kept))

    def test_run_prints_file_and_line_and_fails(self):
        menu = self.write(
            "UI/Menu.lua", "local function F(m, xs)\n\tfor _, x in ipairs(xs) do\n\t\tm:CreateButton(x)\n\tend\nend\n"
        )
        self.write("UI/Fine.lua", "local function F(m)\n\tm:CreateButton('a')\nend\n")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = check_menu_scroll.run(self.root, check_menu_scroll.addon_files(self.root))
        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue().splitlines()[0].split(": ", 1)[0], "UI/Menu.lua:3")
        menu.write_text("local function F(m)\n\tm:CreateButton('a')\nend\n")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = check_menu_scroll.run(self.root, check_menu_scroll.addon_files(self.root))
        self.assertEqual(status, 0)
        self.assertIn("2 Lua files checked", output.getvalue())

    def test_run_reports_a_syntax_error(self):
        self.write("UI/Broken.lua", 'local function F(m)\n\tm:CreateButton("a)\nend\n')
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            status = check_menu_scroll.run(self.root, check_menu_scroll.addon_files(self.root))
        self.assertEqual(status, 1)
        self.assertIn("UI/Broken.lua", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
