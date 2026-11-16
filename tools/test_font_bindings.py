"""Producer-bound glyph regressions using the pinned client cmap."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools.font_glyphs import check_bindings, main  # noqa: E402

DATA = json.loads((ROOT / ".agents/skills/wow-forever-addon/tooling/forever_tools/font_glyphs.json").read_text())


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        (self.root / "Locales").mkdir()
        self.source = self.root / "Widget.lua"
        self.source.write_text(
            'local text = frame:CreateFontString(nil, "ARTWORK", "GameFontNormal")\ntext:SetText(L["Label"])\n'
        )
        self.manifest = {
            "producers": [
                {
                    "source": "Widget.lua",
                    "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                    "bindings": [{"phrase": "Label", "font": "GameFontNormal", "widget": "text"}],
                }
            ]
        }
        (self.root / "Locales/enUS.lua").write_text('local L = {}\nL["Label"] = "Label"\nL["Unmapped"] = "·"\n')
        self.russian = self.root / "Locales/ruRU.lua"
        self.write_russian("·")

    def write_russian(self, value):
        self.russian.write_text(
            'local _, ns = ...\nif GetLocale() ~= "ruRU" then return end\nlocal L = ns.L\nL["Label"] = "'
            + value
            + '"\n'
        )

    def test_reported_separator_old_fail_new_pass_and_unmapped_excluded(self):
        problems = check_bindings(self.root, DATA, self.manifest)
        self.assertEqual(len(problems), 1)
        self.assertIn("U+00B7 absent in fonts/frizqt___cyr.ttf", problems[0])
        self.assertIn("; text)", problems[0])
        self.write_russian("•")
        self.assertEqual(check_bindings(self.root, DATA, self.manifest), [])

    def test_font_producer_change_requires_review(self):
        self.write_russian("•")
        self.source.write_text(self.source.read_text().replace("GameFontNormal", "NumberFontNormal"))
        self.assertIn("source changed", check_bindings(self.root, DATA, self.manifest)[0])

    def test_xml_producer_without_bindings_still_checks_digest(self):
        self.write_russian("•")
        source = self.root / "Tracker.xml"
        source.write_text("<!-- Reviewed template font -->\n<Ui/>\n")
        self.manifest["producers"].append(
            {
                "source": "Tracker.xml",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "bindings": [],
            }
        )
        self.assertEqual(check_bindings(self.root, DATA, self.manifest), [])
        source.write_text('<Ui><Font name="Changed"/></Ui>\n')
        problems = check_bindings(self.root, DATA, self.manifest)
        self.assertEqual(len(problems), 1)
        self.assertIn("Tracker.xml: font binding source changed", problems[0])

    def test_font_choice_not_inferred_from_characters(self):
        manifest = copy.deepcopy(self.manifest)
        font = next(
            name for name, members in DATA["objects"].items() if members.get("russian") == "fonts/skurri_cyr.ttf"
        )
        manifest["producers"][0]["bindings"][0]["font"] = font
        self.assertEqual(check_bindings(self.root, DATA, manifest), [])
        self.write_russian("•")
        self.assertIn("U+2022", check_bindings(self.root, DATA, manifest)[0])

    def test_missing_translation_checks_english_in_target_font(self):
        self.russian.write_text('local _, ns = ...\nif GetLocale() ~= "ruRU" then return end\nlocal L = ns.L\n')
        (self.root / "Locales/enUS.lua").write_text('local L = {}\nL["Label"] = "·"\n')
        self.assertIn("enUS.lua:2", check_bindings(self.root, DATA, self.manifest)[0])

    def test_runtime_literal_uses_same_exact_font_contract(self):
        binding = self.manifest["producers"][0]["bindings"][0]
        del binding["phrase"]
        binding["literal"] = "·"
        self.assertIn("runtime literal", check_bindings(self.root, DATA, self.manifest)[0])

    def test_unknown_phrase_is_mapping_error(self):
        self.manifest["producers"][0]["bindings"][0]["phrase"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unknown English phrase"):
            check_bindings(self.root, DATA, self.manifest)

    def test_key_fallback_checks_translations_and_missing_translations(self):
        (self.root / "Locales/enUS.lua").write_text(
            "local L = setmetatable({}, {__index = function(_, key) return key end})\n"
        )
        self.assertIn("U+00B7", check_bindings(self.root, DATA, self.manifest)[0])
        self.write_russian("•")
        self.assertEqual(check_bindings(self.root, DATA, self.manifest), [])
        self.russian.write_text('local _, ns = ...\nif GetLocale() ~= "ruRU" then return end\nlocal L = ns.L\n')
        self.assertEqual(check_bindings(self.root, DATA, self.manifest), [])

    def test_key_fallback_requires_exact_decoded_source_literal(self):
        (self.root / "Locales/enUS.lua").write_text("local L = {}\n")
        for source, passes in (
            ('-- "Label"\nlocal x = "Labels"', False),
            ('local x = "La" .. "bel"', False),
            ('local x = "La\\098el"', True),
            ("local x = [=[Label]=]", True),
        ):
            with self.subTest(source=source):
                self.source.write_text(source)
                self.manifest["producers"][0]["sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
                self.write_russian("•")
                if passes:
                    self.assertEqual(check_bindings(self.root, DATA, self.manifest), [])
                else:
                    with self.assertRaisesRegex(ValueError, "absent from enUS entries and producer string literals"):
                        check_bindings(self.root, DATA, self.manifest)

    def test_explicit_english_entry_takes_precedence_without_source_literal(self):
        self.manifest["producers"][0]["bindings"][0]["phrase"] = "Other"
        (self.root / "Locales/enUS.lua").write_text('local L = {}\nL["Other"] = "·"\n')
        self.assertIn("enUS.lua:2", check_bindings(self.root, DATA, self.manifest)[0])

    def test_automatic_cli_gate(self):
        path = self.root / "bindings.json"
        path.write_text(json.dumps(self.manifest))
        args = ["--bindings", str(path)]
        self.assertEqual(main(self.root, args), 1)
        self.write_russian("•")
        self.assertEqual(main(self.root, args), 0)

    def test_typecheck_rejects_bad_glyph_before_toolchain_fetch(self):
        tools = self.root / "tools"
        tools.mkdir()
        for name in ("typecheck.sh", "check_font_glyphs.py"):
            shutil.copyfile(ROOT / "tools" / name, tools / name)
        (tools / "font_bindings.json").write_text(json.dumps(self.manifest))
        (self.root / ".agents").symlink_to(ROOT / ".agents", target_is_directory=True)
        commands = self.root / "bin"
        commands.mkdir()
        git = commands / "git"
        git.write_text("#!/bin/sh\necho toolchain-fetch-attempted >&2\nexit 99\n")
        git.chmod(0o755)
        result = subprocess.run(
            ["bash", str(tools / "typecheck.sh")],
            env={**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"]},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("U+00B7", result.stdout)
        self.assertNotIn("toolchain-fetch-attempted", result.stderr)

    def test_repository_bindings(self):
        self.assertEqual(check_bindings(ROOT, DATA, json.loads((ROOT / "tools/font_bindings.json").read_text())), [])


if __name__ == "__main__":
    unittest.main()
