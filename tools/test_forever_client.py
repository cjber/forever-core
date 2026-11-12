"""Specs for tools/headless/forever_client.py: the parts that hold without a game client."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("forever_client", Path(__file__).parent / "headless/forever_client.py")
fc = importlib.util.module_from_spec(SPEC)
sys.modules["forever_client"] = fc
SPEC.loader.exec_module(fc)


def args() -> argparse.Namespace:
    return argparse.Namespace(wait=False, timeout=5)


class FakeClock:
    """A monotonic clock that moves only when something sleeps, so a wait runs without real time."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ForeverClientTest(unittest.TestCase):
    def setUp(self):
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))

    def test_wine_env_keeps_the_launch_and_drops_the_desktop(self):
        env = fc.wine_env(
            {
                "WINE": "/runner/bin/wine",
                "WINEDLLOVERRIDES": "d3d12=n",
                "DXVK_LOG_LEVEL": "error",
                "LD_PRELOAD": "libgamemodeauto.so.0",
                "WAYLAND_DISPLAY": "wayland-1",
                "DISPLAY": ":1",
                "WINESERVERSOCKET": "335",
                "HOME": "/home/x",
            }
        )
        self.assertEqual(
            env,
            {
                "WINE": "/runner/bin/wine",
                "WINEDLLOVERRIDES": "d3d12=n",
                "DXVK_LOG_LEVEL": "error",
                "LD_PRELOAD": "libgamemodeauto.so.0",
            },
        )

    def test_up_refuses_while_the_players_client_runs(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[42, 43]),
            mock.patch.object(fc, "client_pid", return_value=43),
            self.assertRaisesRegex(fc.ClientError, r"player's client is running .*pid 43"),
        ):
            fc.up(args())

    def test_up_fails_fast_without_a_network(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection", side_effect=OSError("Network is unreachable")),
            self.assertRaisesRegex(fc.ClientError, "cannot reach Battle.net.*outside the sandbox"),
        ):
            fc.up(args())

    def test_a_second_session_fails_clearly_unless_it_waits(self):
        (self.state / "session.json").write_text('{"pid": 7}')
        holder = open(self.state / "lock", "w")
        self.addCleanup(holder.close)
        fcntl.flock(holder, fcntl.LOCK_EX)
        with self.assertRaisesRegex(fc.ClientError, r'another agent.*"pid": 7.*--wait'):
            fc.up(args())

    def test_wait_queues_until_the_session_lock_is_free(self):
        clock = FakeClock()
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            mock.patch.object(fc.fcntl, "flock", side_effect=[BlockingIOError(), None]),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection", side_effect=OSError("Network is unreachable")),
            self.assertRaisesRegex(fc.ClientError, "cannot reach Battle.net"),
        ):
            fc.up(argparse.Namespace(wait=True, timeout=600))
        self.assertGreater(clock.now, 0)

    def test_wait_queues_until_the_prefix_is_empty(self):
        clock = FakeClock()
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            mock.patch.object(fc, "prefix_users", side_effect=[[42], []]),
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc.socket, "create_connection", side_effect=OSError("Network is unreachable")),
            self.assertRaisesRegex(fc.ClientError, "cannot reach Battle.net"),
        ):
            fc.up(argparse.Namespace(wait=True, timeout=600))
        self.assertGreater(clock.now, 0)

    def test_wait_times_out_while_the_prefix_stays_in_use(self):
        clock = FakeClock()
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            mock.patch.object(fc, "prefix_users", return_value=[42]),
            mock.patch.object(fc, "client_pid", return_value=None),
            self.assertRaisesRegex(fc.ClientError, r"still in use after waiting 5 s"),
        ):
            fc.up(argparse.Namespace(wait=True, timeout=5))
        self.assertGreaterEqual(clock.now, 5)

    def test_a_run_that_waits_out_its_timeout_exits_non_zero(self):
        (self.state / "session.json").write_text('{"pid": 7}')
        clock = FakeClock()
        err = io.StringIO()
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            mock.patch.object(fc.fcntl, "flock", side_effect=BlockingIOError()),
            mock.patch.object(fc.subprocess, "run") as ran,
            contextlib.redirect_stderr(err),
        ):
            code = fc.main(["run", "--wait", "--timeout", "5", "--", "true"])
        self.assertEqual(code, 2)
        ran.assert_not_called()
        self.assertIn("after waiting 5 s", err.getvalue())

    def test_slash_sends_only_the_addons_commands_and_ui_ones(self):
        addons = self.state / "AddOns"
        (addons / "FieldGuideForever").mkdir(parents=True)
        (addons / "FieldGuideForever/Core.lua").write_text('SLASH_FIELDGUIDEFOREVER1 = "/fgf"\n')
        (addons / "ForeverCore").mkdir()
        (addons / "ForeverCore/Expose.lua").write_text('SLASH_FOREVERCORE1 = "/fcore"\n')
        (addons / "SomeoneElse").mkdir()
        (addons / "SomeoneElse/Core.lua").write_text('SLASH_OTHER1 = "/other"\n')
        for ok in ("/fgf", "/FGF reset", "/fcore", "/reload"):
            fc.allowed_command(ok, addons)
        for refused in (
            "/other",
            "/s hello",
            "/run print(1)",
            "/dump x",
            "/follow",
            "/cast Fireball",
            "/fgf\n/s hi",
            "hello",
            "",
        ):
            with self.subTest(refused), self.assertRaises(fc.ClientError):
                fc.allowed_command(refused, addons)

    def test_slash_reads_a_conditional_and_a_plain_slash_assignment(self):
        addons = self.state / "AddOns"
        (addons / "TweaksForever").mkdir(parents=True)
        (addons / "TweaksForever/UI").mkdir()
        (addons / "TweaksForever/UI/Leaderboards.lua").write_text(
            'local foreverTaken = false\nSLASH_FOREVERLEADERBOARDS1 = not foreverTaken and "/forever" or nil\n'
        )
        (addons / "SkillUpForever").mkdir()
        (addons / "SkillUpForever/Core.lua").write_text('SLASH_SKILLUPFOREVER1 = "/path"\n')
        for ok in ("/forever", "/forever selftest", "/path", "/path reset"):
            fc.allowed_command(ok, addons)
        for refused in ("/run print(1)", "/dump x", "/fgf"):
            with self.subTest(refused), self.assertRaises(fc.ClientError):
                fc.allowed_command(refused, addons)

    def test_slash_releases_an_addon_edit_box_before_it_opens_chat(self):
        calls = []
        with (
            mock.patch.object(fc, "send", side_effect=lambda _state, *args: calls.append(args)),
            mock.patch.object(fc, "allowed_command"),
        ):
            fc.slash({}, "/reload")
        self.assertEqual(
            calls,
            [
                ("key", "Return"),
                ("key", "Escape"),
                ("key", "Return"),
                ("type", "--delay", fc.TYPE_DELAY_MS, "/reload"),
                ("key", "Return"),
            ],
        )

    def test_key_sends_only_ui_keys(self):
        with mock.patch.object(fc, "x") as x, self.assertRaisesRegex(fc.ClientError, "refused w"):
            fc.press({}, ["Escape", "w"])
        x.assert_not_called()

    def test_press_play_moves_in_window_pixels_not_window_relative(self):
        state = {"display": ":1"}
        found = mock.Mock(stdout="12345\n")
        geometry = mock.Mock(stdout="WINDOW=12345\nX=181\nY=328\nWIDTH=1266\nHEIGHT=684\nSCREEN=0\n")
        with (
            mock.patch.object(fc.subprocess, "run", side_effect=[found, geometry]),
            mock.patch.object(fc, "x") as x,
            mock.patch.object(fc.time, "sleep"),
        ):
            fc.press_play(state)
        self.assertEqual(
            x.call_args_list,
            [
                mock.call(state, "mousemove", "921", "367"),
                mock.call(state, "click", "1"),
            ],
        )
        self.assertNotIn("--window", x.call_args_list[0].args)

    def test_a_click_needs_a_screenshot_since_the_last_input(self):
        with mock.patch.object(fc, "x") as x, mock.patch.object(fc, "INPUT_GAP", 0):
            with self.assertRaisesRegex(fc.ClientError, "take a `shot`"):
                fc.click({}, 10, 10, "1")
            (self.state / "last-shot").touch()
            fc.click({}, 10, 10, "1")
            with self.assertRaisesRegex(fc.ClientError, "take a `shot`"):
                fc.click({}, 20, 20, "1")
        self.assertEqual(x.call_count, 1)

    def test_inputs_are_spaced_out(self):
        sleeps = []
        with mock.patch.object(fc, "x"), mock.patch.object(fc.time, "sleep", sleeps.append):
            fc.send({}, "key", "Escape")
            fc.send({}, "key", "Escape")
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], fc.INPUT_GAP - 0.5)

    def test_teardown_logs_out_only_from_the_world(self):
        game = mock.Mock(pid=1, **{"poll.return_value": None})
        with (
            mock.patch.object(fc, "log_out") as log_out,
            mock.patch.object(fc, "client_pid", return_value=9),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.os, "killpg"),
            mock.patch.object(fc.subprocess, "run"),
        ):
            fc.teardown(game, {}, None, {"display": ":1"})
            log_out.assert_not_called()
            fc.teardown(game, {}, None, {"display": ":1", "ready": 1.0})
            log_out.assert_called_once()

    def test_teardown_reaps_children_that_respawn_after_wineserver_shutdown(self):
        game = mock.Mock(pid=1, **{"poll.return_value": None})
        clock = FakeClock()
        with (
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "prefix_users", side_effect=[[42], [43], [], [], [], [], [], [], [], []]),
            mock.patch.object(fc.os, "killpg"),
            mock.patch.object(fc.os, "kill") as kill,
            mock.patch.object(fc.subprocess, "run"),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
        ):
            fc.teardown(game, {}, None, {"display": ":1"})
        self.assertEqual(kill.call_args_list, [mock.call(42, fc.signal.SIGKILL), mock.call(43, fc.signal.SIGKILL)])

    def test_verbs_without_a_session_say_how_to_start_one(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(fc.main(["shot"]), 2)
        self.assertIn("forever_client.py up", err.getvalue())


if __name__ == "__main__":
    unittest.main()
