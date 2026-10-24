import unittest

from forever_tools import readable


def codes(source, policy=readable.DEFAULT_POLICY):
    return [message.split(":", 1)[0] for _, message in readable.check(source, policy)]


class ReadableTest(unittest.TestCase):
    def test_an_unguarded_source_is_flagged(self):
        for source in (
            "local guid = UnitGUID(unit)\n",
            'local id = guid:match("%d+")(UnitGUID("mouseover"))\n',
            "local name = UnitName(unit)\n",
            "local name = TooltipUtil.GetDisplayedUnit(tooltip)\n",
            "local id = Model.NpcId(UnitGUID(unit))\n",
            'local name = UnitName"mouseover"\n',
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), ["secret-unguarded"])

    def test_a_guard_the_player_and_a_definition_are_clean(self):
        for source in (
            "local guid = ns.Readable(UnitGUID(unit))\n",
            "local guid = Readable(UnitGUID(unit))\n",
            'local me = UnitName("player")\n',
            "local function UnitGUID(unit) return unit end\n",
            "function ns.UnitName(unit) return unit end\n",
            "-- UnitGUID(unit) in a comment\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_a_guard_must_take_the_whole_value(self):
        self.assertEqual(codes("local x = ns.Readable(UnitGUID(unit), 1)\n"), ["secret-unguarded"])
        self.assertEqual(codes("local x = ns.Readable(UnitGUID(unit) .. 'x')\n"), ["secret-unguarded"])

    def test_policy_names_the_guard_and_safe_units(self):
        policy = readable.Policy(guards=frozenset({"Safe"}), safe_units=frozenset({"player", "pet"}))
        self.assertEqual(codes("local g = Safe(UnitGUID(u))\nlocal p = UnitName('pet')\n", policy), [])
        self.assertEqual(codes("local g = Readable(UnitGUID(u))\n", policy), ["secret-unguarded"])

    def test_a_tooltip_hook_must_skip_forbidden_tooltips(self):
        hook = (
            "TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Unit, function(tooltip, data)\n"
            "{guard}"
            "\tif ok then tooltip:AddLine(ns.Readable(data.guid)) end\n"
            "end)\n"
        )
        self.assertEqual(codes(hook.format(guard="")), ["secret-forbidden"])
        self.assertEqual(codes(hook.format(guard="\tif tooltip:IsForbidden() then return end\n")), [])

    def test_a_named_callback_is_checked_where_it_is_defined(self):
        clean = (
            "local function AddUses(tooltip)\n\tif tooltip:IsForbidden() then return end\nend\n"
            "TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, AddUses)\n"
        )
        self.assertEqual(codes(clean), [])
        self.assertEqual(codes(clean.replace("tooltip:IsForbidden()", "false")), ["secret-forbidden"])
        self.assertEqual(
            codes("TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, ns.Elsewhere)\n"),
            ["secret-forbidden"],
        )
        self.assertEqual(
            codes('GameTooltip:HookScript("OnTooltipSetUnit", function(self) self:Show() end)\n'),
            ["secret-forbidden"],
        )
        self.assertEqual(codes('frame:HookScript("OnShow", function(self) self:Show() end)\n'), [])
        self.assertEqual(
            codes('GameTooltip:SetScript("OnTooltipSetUnit", function(self) self:Show() end)\n'),
            ["secret-forbidden"],
        )

    def test_the_forbidden_check_comes_first(self):
        late = (
            "TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Unit, function(tooltip)\n"
            "\ttooltip:AddLine(x)\n\tif tooltip:IsForbidden() then return end\nend)\n"
        )
        self.assertEqual(codes(late), ["secret-forbidden"])
        either = late.replace(
            "\ttooltip:AddLine(x)\n\tif tooltip:IsForbidden()", "\tif not ok or tooltip:IsForbidden()"
        )
        self.assertEqual(codes(either), [])
        usable = late.replace("\ttooltip:AddLine(x)\n\tif tooltip:IsForbidden()", "\tif not ns.Usable(tooltip)")
        self.assertEqual(codes(usable), [])
        self.assertEqual(
            codes(usable, readable.Policy(forbidden_checks=frozenset({"IsForbidden"}))), ["secret-forbidden"]
        )

    def test_hook_data_fields_need_a_guard(self):
        source = (
            "TooltipDataProcessor.AddTooltipPreCall(Enum.TooltipDataType.Unit, function(tooltip, data)\n"
            "\tif tooltip:IsForbidden() then return end\n"
            "\tlocal guid = data.guid\n"
            "\tlocal safe = ns.Readable(data.guid)\n"
            "\tlocal other = entry.guid\n"
            '\tlocal bracket = data["guid"]\n'
            "end)\n"
        )
        found = readable.check(source)
        self.assertEqual(
            found,
            [
                (3, "secret-unguarded: data.guid may be a secret; read it through a guard"),
                (6, "secret-unguarded: data.guid may be a secret; read it through a guard"),
            ],
        )

    def test_a_waiver_excuses_its_line_and_must_excuse_something(self):
        self.assertEqual(codes("local g = UnitGUID(u) -- secret-ok: own pet, never secret\n"), [])
        self.assertEqual(codes("-- secret-ok: own pet, never secret\nlocal g = UnitGUID(u)\n"), [])
        self.assertEqual(codes("local x = 1 -- secret-ok: nothing\n"), ["secret-unused"])
        self.assertEqual(codes("local g = UnitGUID(u) -- secret-ok:\n"), ["secret-unguarded", "secret-unused"])

    def test_malformed_lua_raises(self):
        with self.assertRaises(readable.LuaSyntaxError):
            readable.check("TooltipDataProcessor.AddTooltipPostCall(x, function(t)\n")


if __name__ == "__main__":
    unittest.main()
