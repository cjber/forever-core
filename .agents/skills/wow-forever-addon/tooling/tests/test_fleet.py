import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from forever_tools import fleet

EMBEDDED = "## Interface: 16001\n## X-Forever-Core-Embed: 1\n"


def readers(tocs, broken=()):
    """A fake fleet: each addon's `.pkgmeta` names its TOC, whose text is `tocs[repo]`."""

    def reader(repo):
        def read(path):
            if repo in broken:
                raise fleet.FleetUnreadable("HTTP 502")
            if path == ".pkgmeta":
                return "package-as: Addon\n"
            return tocs.get(repo) if path == "Addon.toc" else None

        return read, lambda: ["Addon.toc"]

    return reader


class FleetTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / ".pkgmeta").write_text("package-as: Demo\n")

    def write(self, toc):
        (self.root / "Demo.toc").write_text(toc)

    def test_a_checkout_that_does_not_embed_passes_without_reading_the_fleet(self):
        self.write("## Interface: 16001\n")
        self.assertEqual(fleet.check(self.root, lambda repo: self.fail("no fleet read")), [])

    def test_an_embedding_checkout_waits_for_the_addons_not_opted_in(self):
        self.write(EMBEDDED)
        tocs = dict.fromkeys(fleet.EMBED_FLEET, EMBEDDED)
        tocs["tweaks-forever"] = "## Interface: 16001\n"
        failures = fleet.check(self.root, readers(tocs))
        self.assertEqual(len(failures), 1)
        self.assertTrue(failures[0].endswith("not yet: tweaks-forever"))

    def test_an_unreadable_addon_holds_the_release(self):
        self.write(EMBEDDED)
        tocs = dict.fromkeys(fleet.EMBED_FLEET, EMBEDDED)
        failures = fleet.check(self.root, readers(tocs, broken={"legacy-forever"}))
        self.assertIn("could not read legacy-forever", failures[0])

    def test_a_missing_toc_holds_the_release(self):
        self.write(EMBEDDED)
        tocs = dict.fromkeys(fleet.EMBED_FLEET, EMBEDDED)
        del tocs["skillup-forever"]
        self.assertIn("skillup-forever: no Addon.toc", fleet.check(self.root, readers(tocs))[0])

    def test_the_whole_fleet_opted_in_clears_the_hold(self):
        self.write(EMBEDDED)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fleet.main(self.root, readers(dict.fromkeys(fleet.EMBED_FLEET, EMBEDDED))), 0)


if __name__ == "__main__":
    unittest.main()
