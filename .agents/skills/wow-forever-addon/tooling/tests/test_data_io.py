import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import csvtable, fsio, wago


class CsvTest(unittest.TestCase):
    def test_valid_export_keeps_strings_and_converts_named_columns(self):
        rows = csvtable.parse_csv("ID,N,F,T\n1,2,0.5,x\n", "T", required=["T"], ints=["N"], floats=["F"])
        self.assertEqual(rows, [{"ID": "1", "N": 2, "F": 0.5, "T": "x"}])

    def test_rejects_the_shifted_column_export(self):
        with self.assertRaisesRegex(ValueError, "duplicate columns"):
            csvtable.parse_csv("ID,Value,Value\n1,2,3\n", "T")

    def test_rejections(self):
        for text, options, message in (
            ("ID,A\n1,2\n1,3\n", {}, "duplicate ID 1"),
            ("ID,A\n1,2\n01,3\n", {}, "duplicate ID 1"),
            ("ID,A\n1.0,2\n", {}, "invalid integer ID"),
            ("ID,A\n,2\n", {}, "invalid integer ID"),
            ('"ID,A\n', {}, "invalid CSV header"),
            ("ID,A\n1\n", {}, "malformed CSV row"),
            ("ID,A\n1,2,3\n", {}, "malformed CSV row"),
            ("ID,A\n1,2\n", {"required": ["B"]}, "missing required columns"),
            ("ID,A\n1,2.0\n", {"ints": ["A"]}, "invalid integer"),
            ("ID,A\n1, 2\n", {"ints": ["A"]}, "invalid integer"),
            ("ID,A\n1,1_0\n", {"ints": ["A"]}, "invalid integer"),
            ("ID,A\n1,nan\n", {"floats": ["A"]}, "invalid number"),
            ("ID,A\n1,inf\n", {"floats": ["A"]}, "invalid number"),
            ("ID,A\n", {}, "empty export"),
            ('ID,A\n1,"x\n', {}, "invalid CSV"),
        ):
            with self.subTest(text=text, options=options), self.assertRaisesRegex(ValueError, message):
                csvtable.parse_csv(text, "T", **options)

    def test_empty_export_and_missing_id_column_are_allowed_when_asked(self):
        self.assertEqual(csvtable.parse_csv("ID,A\n", "T", allow_empty=True), [])
        self.assertEqual(len(csvtable.parse_csv("A\n1\n1\n", "T")), 2)

    def test_error_names_the_line_of_the_bad_row(self):
        with self.assertRaisesRegex(ValueError, "T:3:"):
            csvtable.parse_csv("ID,A\n1,2\n2\n", "T")


class AtomicTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def files(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())

    def test_atomic_write_creates_replaces_and_leaves_no_temporary(self):
        path = self.root / "deep" / "x.lua"
        fsio.atomic_write(path, "one")
        fsio.atomic_write(path, b"two")
        self.assertEqual(path.read_bytes(), b"two")
        self.assertEqual(self.files(), ["deep/x.lua"])

    def test_failed_replace_keeps_the_old_file(self):
        path = self.root / "x.lua"
        path.write_text("old")
        with mock.patch.object(Path, "replace", side_effect=OSError("disk")), self.assertRaises(OSError):
            fsio.atomic_write(path, "new")
        self.assertEqual((path.read_text(), self.files()), ("old", ["x.lua"]))

    def test_publish_writes_every_output(self):
        fsio.publish({self.root / "a": "1", self.root / "b" / "c": b"2"})
        self.assertEqual(self.files(), ["a", "b/c"])

    def test_publish_rolls_back_replaced_files_when_a_later_replace_fails(self):
        first, second, third = (self.root / name for name in ("a", "b", "c"))
        first.write_text("old a")
        second.write_text("old b")
        real = Path.replace
        calls = []

        def flaky(source, target):
            calls.append(target.name)
            if len(calls) == 2:
                raise OSError("disk")
            return real(source, target)

        with mock.patch.object(Path, "replace", flaky), self.assertRaises(OSError):
            fsio.publish({first: "new a", second: "new b", third: "new c"})
        self.assertEqual((first.read_text(), second.read_text(), third.exists()), ("old a", "old b", False))
        self.assertEqual(self.files(), ["a", "b"])

    def test_publish_stages_everything_before_replacing_anything(self):
        first = self.root / "a"
        first.write_text("old")
        with self.assertRaises(TypeError):
            fsio.publish({first: "new", self.root / "b": 5})
        self.assertEqual((first.read_text(), self.files()), ("old", ["a"]))


class WagoTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name)

    def test_offline_requires_the_cache(self):
        with self.assertRaisesRegex(ValueError, "Missing cached source"):
            wago.db2_rows("T", "1", self.cache, user_agent="t", offline=True)

    def test_cache_is_read_without_the_network(self):
        (self.cache / "T-1.csv").write_text("ID,A\n1,2\n")
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            self.assertEqual(wago.db2_rows("T", "1", self.cache, user_agent="t"), [{"ID": "1", "A": "2"}])

    def download(self, body):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = body
        return mock.patch("urllib.request.urlopen", return_value=response)

    def test_refresh_downloads_validates_then_caches(self):
        with self.download(b"ID,A\n1,2\n"):
            rows = wago.db2_rows("T", "1", self.cache, user_agent="t", refresh=True)
        self.assertEqual(rows, [{"ID": "1", "A": "2"}])
        self.assertEqual((self.cache / "T-1.csv").read_bytes(), b"ID,A\n1,2\n")

    def test_a_rejected_download_is_never_cached(self):
        for body in (b"ID,A,A\n1,2,3\n", b"<html>no</html>", b""):
            with self.subTest(body=body), self.download(body), self.assertRaises(ValueError):
                wago.db2_rows("T", "1", self.cache, user_agent="t", refresh=True)
            self.assertEqual(list(self.cache.iterdir()), [])

    def test_fetch_validate_hook_rejects_before_caching(self):
        def reject(data):
            raise ValueError("bad")

        with self.download(b"payload"), self.assertRaises(ValueError):
            wago.fetch("u", self.cache / "f", user_agent="t", validate=reject)
        self.assertEqual(list(self.cache.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
