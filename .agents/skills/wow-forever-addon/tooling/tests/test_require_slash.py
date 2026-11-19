import tempfile
import unittest
from pathlib import Path

from forever_tools import core_pin, require_slash

SHARED = "function ns.ForeverRequire(ready, slash)\n\treturn ready\nend\n"


class RequireSlashTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.write("Core/ForeverRequire.lua", SHARED)
        self.write(
            "Core/Core.lua",
            'SLASH_DEMOFOREVER1 = "/demo"\nSLASH_DEMOFOREVER2 = "/demoforever"\n'
            "SlashCmdList.DEMOFOREVER = function() end\n"
            # A helper command another addon may own is never required.
            'SLASH_DEMOFOREVER_RELOAD1 = "/rl"\nSlashCmdList.DEMOFOREVER_RELOAD = function() end\n'
            # A conditional claim is not a literal word.
            'SLASH_DEMOWAY1 = claim and "/way" or nil\n',
        )
        # A spec or the embedded library registering words is not the addon's own code.
        self.write("tests/slash_spec.lua", 'SLASH_DEMOFOREVER3 = "/spec"\n')
        self.write("Libs/ForeverCore/Expose.lua", 'SLASH_DEMOFOREVER4 = "/library"\n')

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def require(self, call):
        self.write("Core/Require.lua", "local addonName, ns = ...\nlocal ready = ForeverCore ~= nil\n" + call)

    def test_the_words_the_addon_registers_pass(self):
        self.require(
            'ns.Slash = { key = "DEMOFOREVER", "/demo", "/demoforever" }\n\nns.ForeverRequire(ready, ns.Slash)\n'
        )
        self.assertEqual(require_slash.check(self.root, "DemoForever"), [])

    def test_an_inline_table_passes(self):
        self.require('ns.ForeverRequire(ready, { key = "DEMOFOREVER", "/demo", "/demoforever" })\n')
        self.assertEqual(require_slash.check(self.root, "DemoForever"), [])

    def test_a_call_with_no_slash_words_fails_naming_the_fix(self):
        self.require("ns.ForeverRequire(ready)\n")
        failures = require_slash.check(self.root, "DemoForever")
        self.assertEqual(len(failures), 1)
        self.assertIn("Core/Require.lua:3: ns.ForeverRequire gets no slash words", failures[0])
        self.assertIn('{ key = "DEMOFOREVER", "/demo", "/demoforever" }', failures[0])
        self.assertIn("Core/Core.lua:1", failures[0])

    def test_different_words_fail(self):
        self.require(
            'local slash = { key = "DEMOFOREVER", "/demoforever", "/demo" }\nns.ForeverRequire(ready, slash)\n'
        )
        failures = require_slash.check(self.root, "DemoForever")
        self.assertEqual(len(failures), 1)
        self.assertIn("differ from what the addon registers", failures[0])

    def test_a_missing_word_fails(self):
        self.require('ns.ForeverRequire(ready, { key = "DEMOFOREVER", "/demo" })\n')
        self.assertEqual(len(require_slash.check(self.root, "DemoForever")), 1)

    def test_another_key_fails(self):
        self.require('ns.ForeverRequire(ready, { key = "DEMOFOREVER_RELOAD", "/rl" })\n')
        self.assertIn("differ from what", require_slash.check(self.root, "DemoForever")[0])

    def test_words_spread_over_two_files_and_global_prefix_are_read_in_number_order(self):
        self.write(
            "Core/Core.lua",
            '_G.SLASH_DEMOFOREVER2 = "/demoforever"\nSlashCmdList["DEMOFOREVER"] = function() end\n',
        )
        self.write("UI/Settings.lua", '\t_G.SLASH_DEMOFOREVER1 = "/demo"\n')
        self.assertEqual(require_slash.registered(self.root, "DEMOFOREVER")[0], ["/demo", "/demoforever"])

    def test_an_addon_with_no_command_of_its_own_needs_no_words(self):
        self.write("Core/Core.lua", 'SLASH_OTHERADDON1 = "/other"\n')
        self.require("ns.ForeverRequire(ready)\n")
        self.assertEqual(require_slash.check(self.root, "DemoForever"), [])

    def test_the_pin_gate_runs_the_rule(self):
        self.write("DemoForever.toc", "## Interface: 16001\n## Title: Demo\nCore\\Require.lua\n")
        self.require("ns.ForeverRequire(ready)\n")
        failures = core_pin.check(self.root)
        self.assertTrue(any("gets no slash words" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
