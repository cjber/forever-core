import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from forever_tools import changelog, release_check


class PatrolCliTests(unittest.TestCase):
    def test_release_help_needs_no_environment_or_network(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(release_check.subprocess, "check_output") as request,
        ):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
                release_check.main(["--help"])
            self.assertEqual(result.exception.code, 0)
            request.assert_not_called()

    def test_missing_release_environment_is_usage_error(self):
        with patch.dict("os.environ", {}, clear=True), contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as result:
                release_check.main([])
            self.assertEqual(result.exception.code, 2)
            self.assertIn("GITHUB_REPOSITORY and GITHUB_SHA", error.getvalue())

    def test_release_tags_are_numeric_and_filter_nonversions(self):
        with patch.object(changelog.subprocess, "run") as run:
            run.return_value.stdout = "v0.10.0 v0.2.0 v0.18.10 v0.18.2 vnext v1.0.0-rc1"
            self.assertEqual(changelog.released(Path(".")), ["0.2.0", "0.10.0", "0.18.2", "0.18.10"])
