import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import package, widget_handlers

SHOPPING_LIST = 'local edit = CreateFrame("EditBox")\nedit:SetScript("OnEditFocusGained", edit.HighlightText)\n'


def findings(source, path="Addon/Core.lua"):
    return widget_handlers.check({path: source})


class WidgetHandlerTest(unittest.TestCase):
    def test_a_widget_method_passed_straight_fails(self):
        self.assertEqual(
            findings(SHOPPING_LIST),
            [
                "Addon/Core.lua:2: HighlightText passed straight as a SetScript handler is called with the handler's "
                "arguments; wrap it: function(self) self:HighlightText() end"
            ],
        )

    def test_a_bracket_field_read_fails(self):
        source = 'edit:SetScript("OnEditFocusGained", edit["HighlightText"])\n'
        self.assertEqual(len(findings(source)), 1)
        self.assertIn("HighlightText passed straight as a SetScript handler", findings(source)[0])

    def test_hook_script_fails_too(self):
        source = 'frame:HookScript("OnShow", frame.SetAlpha)\n'
        self.assertEqual(
            findings(source),
            [
                "Addon/Core.lua:1: SetAlpha passed straight as a HookScript handler is called with the handler's "
                "arguments; wrap it: function(self) self:SetAlpha() end"
            ],
        )

    def test_a_zero_parameter_widget_method_passes(self):
        source = (
            'local frame = CreateFrame("Frame")\n'
            'frame:SetScript("OnDragStop", frame.StopMovingOrSizing)\n'
            'local edit = CreateFrame("EditBox")\n'
            'edit:SetScript("OnEscapePressed", edit.ClearFocus)\n'
        )
        self.assertEqual(findings(source), [])

    def test_a_wrapping_closure_passes(self):
        source = (
            'local edit = CreateFrame("EditBox")\n'
            'edit:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)\n'
            'frame:HookScript("OnShow", function(self) self:SetAlpha() end)\n'
        )
        self.assertEqual(findings(source), [])

    def test_a_field_read_of_the_addons_own_function_passes(self):
        source = 'frame:SetScript("OnShow", ns.Refresh)\ncontrols:SetScript("OnShow", self.controls.Refresh)\n'
        self.assertEqual(findings(source), [])

    def test_an_addon_defined_widget_name_passes(self):
        sources = {
            "Addon/Mixin.lua": "local Mixin = {}\nfunction Mixin:SetText()\nend\n",
            "Addon/Core.lua": 'frame:SetScript("OnShow", FrameMixin.SetText)\n',
        }
        self.assertEqual(widget_handlers.check(sources), [])

    def test_an_assigned_function_with_a_widget_name_passes(self):
        sources = {
            "Addon/Mixin.lua": "Mixin.SetText = function(self) self:StartMoving() end\n",
            "Addon/Core.lua": 'frame:SetScript("OnShow", Mixin.SetText)\n',
        }
        self.assertEqual(widget_handlers.check(sources), [])

    def test_a_field_read_that_is_not_the_handler_is_ignored(self):
        source = (
            "print(edit.HighlightText)\n"
            "edit:SetScript(edit.HighlightText)\n"
            'edit:SetScript("OnShow", Wrap(frame.SetText))\n'
            'edit:SetScript("OnShow", frame.SetText ())\n'
        )
        self.assertEqual(findings(source), [])

    def test_the_generator_reads_widget_classes_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Frame").mkdir()
            (root / "Frame/EditBox.lua").write_text(
                "---@class EditBox : Frame\n"
                "---@field width number\n"
                "local EditBox = {}\n"
                "function EditBox:HighlightText(start, stop) end\n"
                "function EditBox:SetText(text) end\n"
                "function EditBox:ClearFocus() end\n",
                encoding="utf-8",
            )
            (root / "Frame/Frame.lua").write_text(
                "---@class Frame\nlocal Frame = {}\nfunction Frame:Show() end\n"
                "function Frame:StartMoving(alwaysStartFromMouse) end\n"
                "local function helper(value) return value end\n",
                encoding="utf-8",
            )
            self.assertEqual(widget_handlers.annotation_methods(root), ["HighlightText", "SetText", "StartMoving"])

    def test_a_method_name_with_one_parameterised_declaration_is_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Frame.lua").write_text(
                "function Frame:Show() end\nfunction EditBox:Show(shown) end\n",
                encoding="utf-8",
            )
            self.assertEqual(widget_handlers.annotation_methods(root), ["Show"])

    def test_the_generated_data_names_its_revision_and_generator(self):
        text = widget_handlers.render(["SetAlpha", "SetText"], "d0b5b51fac4c52c493371b9b18e66ce604ea4326")
        self.assertIn("revision d0b5b51fac4c52c493371b9b18e66ce604ea4326", text)
        self.assertIn("Widget methods that take parameters", text)
        self.assertIn("Generated by tools/gen_widget_methods.py; do not edit by hand.", text)
        self.assertEqual(
            [line for line in text.splitlines() if line and not line.startswith("#")], ["SetAlpha", "SetText"]
        )

    def test_the_committed_data_has_the_methods_the_client_declares(self):
        known = widget_handlers.methods()
        self.assertGreater(len(known), 500)
        for name in ("HighlightText", "SetText", "SetScript", "HookScript", "StartMoving"):
            self.assertIn(name, known)
        for name in ("Show", "Hide", "ClearFocus", "StopMovingOrSizing"):
            self.assertNotIn(name, known)


class CheckRootTest(unittest.TestCase):
    def make(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        return root

    def test_the_lint_follows_the_toc_and_xml_to_what_ships(self):
        root = self.make(
            {
                "Addon/Addon.toc": "## Interface: 16001\nCore.lua\nUI.xml\n",
                "Addon/Core.lua": 'local edit = CreateFrame("EditBox")\nedit:SetScript("OnShow", edit.SetText)\n',
                "Addon/UI.xml": '<Ui><Script file="UI/ui.lua"/></Ui>',
                "Addon/UI/ui.lua": 'frame:HookScript("OnShow", frame.SetAlpha)\n',
                "Addon/Unloaded.lua": 'frame:SetScript("OnShow", frame.SetAlpha)\n',
            }
        )
        self.assertEqual(
            widget_handlers.check_root(root, ("Addon",)),
            [
                "Addon/Core.lua:2: SetText passed straight as a SetScript handler is called with the handler's "
                "arguments; wrap it: function(self) self:SetText() end",
                "Addon/UI/ui.lua:1: SetAlpha passed straight as a HookScript handler is called with the handler's "
                "arguments; wrap it: function(self) self:SetAlpha() end",
            ],
        )

    def test_a_bundled_core_is_not_linted_as_the_addons_code(self):
        root = self.make(
            {
                "Addon/Addon.toc": "Core.lua\n",
                "Addon/Core.lua": "return true\n",
                "ForeverCore/ForeverCore.toc": "Core.lua\n",
                "ForeverCore/Core.lua": 'frame:SetScript("OnShow", frame.SetAlpha)\n',
            }
        )
        self.assertEqual(widget_handlers.check_root(root, ("Addon",)), [])
        self.assertEqual(len(widget_handlers.check_root(root, ("Addon", "ForeverCore"))), 1)

    def test_the_package_job_fails_the_shopping_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / ".release" / "Addon"
            release.mkdir(parents=True)
            (release / "Addon.toc").write_text("## Interface: 16001\nCore.lua\n", encoding="utf-8")
            (release / "Core.lua").write_text(SHOPPING_LIST, encoding="utf-8")
            policy = package.Policy(addons=("Addon",))
            out, err = io.StringIO(), io.StringIO()
            with (
                mock.patch.object(package, "check", return_value=[]),
                mock.patch.object(package, "run_specs", return_value=[]),
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(err),
            ):
                self.assertEqual(package.main(root, policy, []), 1)
            self.assertIn("Addon/Core.lua:2: HighlightText passed straight as a SetScript handler", err.getvalue())


if __name__ == "__main__":
    unittest.main()
