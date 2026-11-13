"""Specs for tools/headless/forever_client.py: the parts that hold without a game client."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import importlib.util
import io
import os
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
    return argparse.Namespace(wait=False, timeout=5, manual_launcher=False)


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
        self.runtime = self.state / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.enterContext(mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.runtime)}))

    def test_runtime_directory_fallback_is_existing_owned_private_directory(self):
        root = self.state / "users"
        root.mkdir()
        target = root / str(os.getuid())
        with self.assertRaises(fc.ClientError):
            fc.runtime_dir({}, os.getuid(), root)
        self.assertFalse(target.exists())
        target.mkdir(mode=0o700)
        for value in ({}, {"XDG_RUNTIME_DIR": ""}):
            with contextlib.redirect_stderr(io.StringIO()) as warning:
                self.assertEqual(fc.runtime_dir(value, os.getuid(), root), target)
            self.assertIn("using", warning.getvalue())

    def test_explicit_runtime_directory_fails_closed(self):
        link = self.state / "runtime-link"
        link.symlink_to(self.runtime)
        regular = self.state / "file"
        regular.touch()
        for path in (Path("relative"), link, regular, self.state / "missing"):
            with self.subTest(path=path), self.assertRaises(fc.ClientError):
                fc.runtime_dir({"XDG_RUNTIME_DIR": str(path)}, os.getuid())
        with self.assertRaises(fc.ClientError):
            fc.runtime_dir({"XDG_RUNTIME_DIR": str(self.runtime)}, os.getuid() + 1)
        self.runtime.chmod(0o755)
        with self.assertRaises(fc.ClientError):
            fc.runtime_dir({"XDG_RUNTIME_DIR": str(self.runtime)}, os.getuid())
        self.assertEqual(self.runtime.stat().st_mode & 0o777, 0o755)

    def test_shot_requires_recorded_runtime_directory(self):
        with self.assertRaisesRegex(fc.ClientError, "restart"):
            fc.shot({"gamescope_socket": "wayland-9"}, self.state / "shot.png")

    def test_shot_uses_recorded_runtime_instead_of_calling_shell(self):
        for host in ("", "/different/runtime"):
            with (
                self.subTest(host=host),
                mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": host}),
                mock.patch.object(fc.subprocess, "run") as run,
                mock.patch.object(fc, "_complete_png", return_value=True),
            ):
                fc.shot(
                    {"gamescope_socket": "wayland-9", "runtime_dir": str(self.runtime)},
                    self.state / "shot.png",
                )
                self.assertEqual(run.call_args.kwargs["env"]["XDG_RUNTIME_DIR"], str(self.runtime))

    def test_up_rejects_invalid_runtime_before_network_or_spawn(self):
        with (
            mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "relative"}),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection") as connect,
            mock.patch.object(fc.subprocess, "Popen") as spawn,
            self.assertRaisesRegex(fc.ClientError, "invalid XDG_RUNTIME_DIR"),
        ):
            fc.up(args())
        connect.assert_not_called()
        spawn.assert_not_called()

    def test_up_records_runtime_and_keeps_gamescope_off_host_display(self):
        config = self.state / "env.json"
        config.write_text(
            '{"WINE":"/runner/bin/wine","DISPLAY":":host","WAYLAND_DISPLAY":"host","XDG_RUNTIME_DIR":"/stale/runtime"}'
        )
        client = self.state / "client"
        (client / "Interface/AddOns").mkdir(parents=True)
        with (
            mock.patch.object(fc, "CONFIG", config),
            mock.patch.object(fc, "CLIENT", client),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection"),
            mock.patch.object(fc.signal, "signal"),
            mock.patch.object(fc.signal, "alarm"),
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "child_env", return_value={"DISPLAY": ":3", "GAMESCOPE_WAYLAND_DISPLAY": "private"}),
            mock.patch.object(fc, "wait_for_world") as wait,
            mock.patch.object(fc, "client_pid", return_value=None) as client_pid,
            mock.patch.object(fc, "press_play") as press_play,
            mock.patch.object(fc, "x") as x,
            mock.patch.object(fc, "teardown"),
            mock.patch.object(fc.subprocess, "Popen") as spawn,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            spawn.return_value.pid = 123

            def waiting(*unused, nudge):
                nudge()
                press_play.assert_not_called()
                client_pid.return_value = 456
                nudge()
                return Path("ready.png")

            wait.side_effect = waiting
            options = args()
            options.manual_launcher = True
            self.assertEqual(fc.up(options, after_ready=lambda state: state["runtime_dir"]), str(self.runtime))
            self.assertEqual(x.call_args.args[1:], ("key", "Return"))
        env = spawn.call_args.kwargs["env"]
        self.assertEqual(env["XDG_RUNTIME_DIR"], str(self.runtime))
        self.assertNotIn("DISPLAY", env)
        self.assertNotIn("WAYLAND_DISPLAY", env)
        self.assertIn(str(self.runtime), (self.state / "session.json").read_text())
        self.assertIn('"manual_launcher": true', (self.state / "session.json").read_text())

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
        (addons / "!!DevSmoke").mkdir(parents=True)
        (addons / "!!DevSmoke/Core.lua").write_text('SLASH_DEVSMOKE1 = "/devsmoke"\n')
        (addons / "FieldGuideForever").mkdir(parents=True)
        (addons / "FieldGuideForever/Core.lua").write_text('SLASH_FIELDGUIDEFOREVER1 = "/fgf"\n')
        (addons / "ForeverCore").mkdir()
        (addons / "ForeverCore/Expose.lua").write_text('SLASH_FOREVERCORE1 = "/fcore"\n')
        (addons / "SomeoneElse").mkdir()
        (addons / "SomeoneElse/Core.lua").write_text('SLASH_OTHER1 = "/other"\n')
        for ok in ("/fgf", "/FGF reset", "/fcore", "/reload", "/devsmoke eval"):
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

    def test_press_play_clicks_the_screenshot_bound_play_label(self):
        state = {"display": ":1"}
        found = mock.Mock(stdout="12345\n")
        tsv = "level\tpage\tblock\tpar\tline\tword\tleft\ttop\twidth\theight\tconf\ttext\n"
        tsv += "5\t1\t1\t1\t1\t1\t1390\t580\t72\t24\t96.5\tPlay\n"
        ocr = mock.Mock(returncode=0, stdout=tsv, stderr="")
        with (
            mock.patch.object(fc.subprocess, "run", side_effect=[found, ocr]),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(fc, "x") as x,
            mock.patch.object(fc.time, "sleep"),
        ):
            fc.press_play(state)
        self.assertEqual(
            x.call_args_list,
            [
                mock.call(state, "mousemove", "1426", "592"),
                mock.call(state, "click", "1"),
            ],
        )
        self.assertNotIn("--window", x.call_args_list[0].args)
        self.assertTrue((self.state / "last-input").exists())

    def test_press_play_waits_for_a_loading_launcher_without_clicking(self):
        state = {"display": ":1"}
        found = mock.Mock(stdout="12345\n")
        ocr = mock.Mock(returncode=0, stdout="header\n", stderr="")
        with (
            mock.patch.object(fc.subprocess, "run", side_effect=[found, ocr, found, ocr]),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(fc, "x") as x,
            contextlib.redirect_stderr(io.StringIO()) as warning,
        ):
            fc.press_play(state)
            fc.press_play(state)
        x.assert_not_called()
        self.assertEqual(warning.getvalue().count("no visible Play label"), 1)
        self.assertIn(str(self.state / "launcher.png"), warning.getvalue())
        self.assertIn("--manual-launcher", warning.getvalue())

    def test_manual_launcher_cli_only_allows_shot_and_left_click_before_ready(self):
        state = {"manual_launcher": True}
        with (
            mock.patch.object(fc, "load_state", return_value=state),
            mock.patch.object(fc, "shot", return_value=self.state / "frame.png") as shot,
            mock.patch.object(fc, "click") as click,
            mock.patch.object(fc, "press") as press,
            mock.patch.object(fc, "slash") as slash,
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(fc.main(["shot"]), 0)
            self.assertEqual(fc.main(["click", "100", "200"]), 0)
            for command in (["click", "100", "200", "--button", "3"], ["key", "Return"], ["slash", "/fgf"]):
                self.assertEqual(fc.main(command), 2)
            shot.assert_called_once()
            click.assert_called_once_with(state, 100, 200, "1")
            press.assert_not_called()
            slash.assert_not_called()

    def test_default_launcher_still_blocks_actions_before_ready(self):
        with (
            mock.patch.object(fc, "load_state", return_value={}),
            mock.patch.object(fc, "shot") as shot,
            mock.patch.object(fc, "click") as click,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(fc.main(["shot"]), 2)
            self.assertEqual(fc.main(["click", "100", "200"]), 2)
            shot.assert_not_called()
            click.assert_not_called()

    def test_manual_launcher_flag_reaches_up_and_run(self):
        with mock.patch.object(fc, "up", return_value=0) as up:
            self.assertEqual(fc.main(["up", "--manual-launcher"]), 0)
            self.assertTrue(up.call_args.args[0].manual_launcher)
            self.assertEqual(fc.main(["run", "--manual-launcher", "--", "true"]), 0)
            self.assertTrue(up.call_args.args[0].manual_launcher)

    def test_press_play_refuses_ambiguous_ocr_targets(self):
        state = {"display": ":1"}
        found = mock.Mock(stdout="12345\n")
        row = "5\t1\t1\t1\t1\t1\t100\t100\t40\t20\t90\tPlay\n"
        ocr = mock.Mock(returncode=0, stdout="header\n" + row + row, stderr="")
        with (
            mock.patch.object(fc.subprocess, "run", side_effect=[found, ocr]),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(fc, "x") as x,
            self.assertRaisesRegex(fc.ClientError, "expected one visible Play target"),
        ):
            fc.press_play(state)
        x.assert_not_called()

    def test_shot_does_not_return_a_stale_or_incomplete_png(self):
        target = self.state / "launcher.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"stale")
        with (
            mock.patch.object(fc.subprocess, "run"),
            mock.patch.object(fc.time, "sleep"),
            self.assertRaisesRegex(fc.ClientError, "wrote no screenshot"),
        ):
            fc.shot({"gamescope_socket": "wayland-9", "runtime_dir": str(self.runtime)}, target)
        self.assertFalse(target.exists())

    def test_complete_png_requires_the_iend_crc(self):
        signature = b"\x89PNG\r\n\x1a\n"
        iend = b"\x00\x00\x00\x00IEND"
        self.assertFalse(fc._complete_png(self.state / "missing.png"))
        truncated = self.state / "truncated.png"
        truncated.write_bytes(signature + iend)
        self.assertFalse(fc._complete_png(truncated))
        complete = self.state / "complete.png"
        complete.write_bytes(signature + iend + b"crc!")
        self.assertTrue(fc._complete_png(complete))

    def test_a_click_needs_a_screenshot_since_the_last_input(self):
        with mock.patch.object(fc, "x") as x, mock.patch.object(fc, "INPUT_GAP", 0):
            with self.assertRaisesRegex(fc.ClientError, "take a `shot`"):
                fc.click({}, 10, 10, "1")
            (self.state / "last-shot").touch()
            fc.click({}, 10, 10, "1")
            with self.assertRaisesRegex(fc.ClientError, "take a `shot`"):
                fc.click({}, 20, 20, "1")
        self.assertEqual(x.call_count, 1)

    def test_manual_launcher_click_refuses_when_game_process_has_started(self):
        (self.state / "last-input").touch()
        (self.state / "last-shot").touch()
        started = False

        def start_game(unused):
            nonlocal started
            started = True

        with (
            mock.patch.object(
                fc, "mark", side_effect=lambda name: fc.time.time() + (0.1 if name == "last-shot" else 0)
            ),
            mock.patch.object(fc.time, "sleep", side_effect=start_game),
            mock.patch.object(fc, "client_pid", side_effect=lambda: 456 if started else None),
            mock.patch.object(fc, "x") as x,
            self.assertRaisesRegex(fc.ClientError, "game has started"),
        ):
            fc.click({"manual_launcher": True}, 100, 100, "1")
        x.assert_not_called()

    def test_inputs_are_spaced_out(self):
        sleeps = []
        with mock.patch.object(fc, "x"), mock.patch.object(fc.time, "sleep", sleeps.append):
            fc.send({}, "key", "Escape")
            fc.send({}, "key", "Escape")
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], fc.INPUT_GAP - 0.5)

    def prefix_scans(self, scans):
        remaining = iter(scans)
        return mock.patch.object(
            fc, "prefix_snapshot", side_effect=lambda: {pid: fc.read_environ(pid) for pid in next(remaining, scans[-1])}
        )

    def test_prefix_ownership_keeps_one_environment_snapshot_when_process_exits(self):
        env = {"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": "owned"}
        with (
            mock.patch.object(fc, "pids", return_value=[42]),
            mock.patch.object(fc, "read_environ", side_effect=[env, {}]) as read,
        ):
            snapshot = fc.prefix_snapshot()
            self.assertEqual(fc.prefix_ownership(snapshot, "owned"), ([42], []))
            read.assert_called_once_with(42)

    def test_teardown_logs_out_only_from_the_world(self):
        game = mock.Mock(pid=1, **{"poll.return_value": None})
        with (
            mock.patch.object(fc, "log_out") as log_out,
            mock.patch.object(fc, "client_pid", return_value=9),
            mock.patch.object(fc, "prefix_snapshot", return_value={}),
            mock.patch.object(fc.os, "killpg"),
            mock.patch.object(fc.subprocess, "run"),
        ):
            fc.teardown(game, {}, None, {"display": ":1"})
            log_out.assert_not_called()
            fc.teardown(game, {}, None, {"display": ":1", "ready": 1.0})
            log_out.assert_called_once()

    def test_teardown_reaps_owned_children_that_respawn(self):
        game = mock.Mock(pid=1, **{"poll.return_value": None})
        clock = FakeClock()
        with (
            mock.patch.object(fc, "client_pid", return_value=None),
            self.prefix_scans([[42], [42], [43], [], [], [], [], []]),
            mock.patch.object(
                fc,
                "read_environ",
                side_effect=lambda pid: {"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": "owned"},
            ),
            mock.patch.object(fc.os, "killpg"),
            mock.patch.object(fc, "kill_owned_pid") as kill,
            mock.patch.object(fc.subprocess, "run"),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
        ):
            fc.teardown(game, {}, None, {"display": ":1", "token": "owned"})
        self.assertEqual(
            kill.call_args_list,
            [
                mock.call(42, "owned", Path("wineserver").resolve()),
                mock.call(43, "owned", Path("wineserver").resolve()),
            ],
        )

    def test_teardown_retains_state_and_link_when_owned_processes_survive(self):
        clock = FakeClock()
        state = self.state / "session.json"
        state.write_text('{"pid": 7}')
        link = self.state / "addon"
        link.symlink_to(self.state / "build")
        with (
            self.prefix_scans([[42]]),
            mock.patch.object(
                fc,
                "read_environ",
                return_value={"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": "owned"},
            ),
            mock.patch.object(fc, "kill_owned_pid", return_value=False),
            mock.patch.object(fc.subprocess, "run"),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            self.assertRaisesRegex(fc.ClientError, "processes survived: 42"),
        ):
            fc.teardown(None, {}, link, {"token": "owned"})
        self.assertTrue(state.exists())
        self.assertTrue(link.is_symlink())

    def test_teardown_refuses_foreign_same_prefix_processes_before_wineserver(self):
        game = mock.Mock(pid=1, **{"poll.return_value": None})
        with (
            self.prefix_scans([[42]]),
            mock.patch.object(
                fc,
                "read_environ",
                return_value={"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": "foreign"},
            ),
            mock.patch.object(fc.os, "killpg") as killpg,
            mock.patch.object(fc.os, "kill") as kill,
            mock.patch.object(fc, "log_out") as logout,
            mock.patch.object(fc.subprocess, "run") as run,
            self.assertRaisesRegex(fc.ClientError, "foreign or unowned.*42"),
        ):
            fc.teardown(game, {}, None, {"token": "owned"})
        run.assert_not_called()
        killpg.assert_not_called()
        kill.assert_not_called()
        logout.assert_not_called()
        game.terminate.assert_not_called()
        game.kill.assert_not_called()

    def test_teardown_stops_before_killing_when_foreign_process_appears(self):
        game = mock.Mock(pid=1, **{"poll.return_value": None})
        with (
            self.prefix_scans([[42], [43]]),
            mock.patch.object(
                fc,
                "read_environ",
                side_effect=lambda pid: {
                    "WINEPREFIX": str(fc.PREFIX),
                    "FOREVER_CLIENT_SESSION": "owned" if pid == 42 else "foreign",
                },
            ),
            mock.patch.object(fc, "kill_owned_pid") as kill,
            mock.patch.object(fc.time, "monotonic", side_effect=[0, 0, 0]),
            self.assertRaisesRegex(fc.ClientError, "foreign or unowned.*43"),
        ):
            fc.teardown(game, {}, None, {"token": "owned"})
        kill.assert_not_called()
        game.terminate.assert_not_called()
        game.kill.assert_not_called()

    def test_owned_pid_signal_preserves_shared_server_and_foreign_process(self):
        server = Path("/runner/bin/wineserver")
        cases = [
            ("owned", Path("/runner/bin/wine"), True),
            ("owned", server, False),
            ("foreign", Path("/runner/bin/wine"), False),
        ]
        for token, executable, should_signal in cases:
            with (
                self.subTest(token=token, executable=executable),
                mock.patch.object(fc.os, "pidfd_open", return_value=11) as opened,
                mock.patch.object(fc.os, "close") as closed,
                mock.patch.object(fc.signal, "pidfd_send_signal") as signal_pid,
                mock.patch.object(Path, "readlink", return_value=executable),
                mock.patch.object(
                    fc, "read_environ", return_value={"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": token}
                ),
            ):
                self.assertEqual(fc.kill_owned_pid(42, "owned", server), should_signal)
                opened.assert_called_once_with(42)
                closed.assert_called_once_with(11)
                if should_signal:
                    signal_pid.assert_called_once_with(11, fc.signal.SIGKILL)
                else:
                    signal_pid.assert_not_called()

    def test_verbs_without_a_session_say_how_to_start_one(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(fc.main(["shot"]), 2)
        self.assertIn("forever_client.py up", err.getvalue())

    def saved_smoke(self, eval_table: str | None) -> Path:
        saved = fc.CLIENT / "WTF/Account/1/SavedVariables"
        saved.mkdir(parents=True)
        path = saved / "!!DevSmoke.lua"
        body = "DevSmokeDB = {\n"
        if eval_table is not None:
            body += '\t["eval"] = ' + eval_table + ",\n"
        path.write_text(body + "}\n")
        return path

    def eval_tool(self, error=Exception):
        tool = mock.Mock(
            write_snippet=mock.Mock(
                return_value={
                    "chunk": Path("/checkout/!!DevSmokeInbox/Eval.lua"),
                    "snippet": Path("probe.lua"),
                    "lines": 2,
                }
            )
        )
        tool.EvalError = error
        return tool

    def test_eval_writes_reloads_and_reports_the_saved_output(self):
        client = self.state / "client"
        with mock.patch.object(fc, "CLIENT", client):
            self.saved_smoke('{\n\t["ran"] = 1763000000,\n\t["ok"] = true,\n\t["out"] = { "a printed line", "42" },\n}')
            tool = self.eval_tool()
            state = {"ready": 1.0}
            out = io.StringIO()
            with (
                mock.patch.object(fc, "load_state", return_value=state),
                mock.patch.object(fc, "devsmoke_eval", return_value=tool),
                mock.patch.object(fc, "reload") as reload,
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(fc.main(["eval", "probe.lua"]), 0)
        reload.assert_called_once_with(state)
        tool.write_snippet.assert_called_once_with(Path("probe.lua"), addons=client / "Interface/AddOns")
        printed = out.getvalue()
        self.assertIn("wrote /checkout/!!DevSmokeInbox/Eval.lua from probe.lua (2 lines)", printed)
        self.assertIn("DevSmokeDB.eval: ok, ran 1763000000\na printed line\n42", printed)

    def test_eval_reports_a_failed_snippet_and_exits_one(self):
        with mock.patch.object(fc, "CLIENT", self.state / "client"):
            self.saved_smoke(
                '{\n\t["ran"] = 7,\n\t["ok"] = false,\n\t["out"] = { "before" },\n\t["err"] = "boom\\nstack",\n}'
            )
            out = io.StringIO()
            with (
                mock.patch.object(fc, "load_state", return_value={"ready": 1.0}),
                mock.patch.object(fc, "devsmoke_eval", return_value=self.eval_tool()),
                mock.patch.object(fc, "reload"),
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(fc.main(["eval", "probe.lua"]), 1)
        self.assertIn("DevSmokeDB.eval: failed, ran 7\nbefore\nerror:\nboom\nstack", out.getvalue())

    def test_eval_refuses_a_snippet_the_compiler_rejects(self):
        class Refused(Exception):
            pass

        tool = self.eval_tool(Refused)
        tool.write_snippet.side_effect = Refused("probe.lua:2: 'end' expected")
        err = io.StringIO()
        with (
            mock.patch.object(fc, "load_state", return_value={"ready": 1.0}),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "reload") as reload,
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(fc.main(["eval", "probe.lua"]), 2)
        reload.assert_not_called()
        self.assertIn("probe.lua:2: 'end' expected", err.getvalue())

    def test_eval_without_a_session_says_how_to_start_one(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(fc.main(["eval", "probe.lua"]), 2)
        self.assertIn("forever_client.py up", err.getvalue())

    def test_eval_without_saved_variables_says_so(self):
        err = io.StringIO()
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "load_state", return_value={"ready": 1.0}),
            mock.patch.object(fc, "devsmoke_eval", return_value=self.eval_tool()),
            mock.patch.object(fc, "reload"),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(fc.main(["eval", "probe.lua"]), 2)
        self.assertIn("no SavedVariables for !!DevSmoke", err.getvalue())

    def test_format_eval_orders_the_saved_lines(self):
        report, ok = fc.format_eval({"ran": 7, "ok": True, "out": {2: "second", 1: "first"}})
        self.assertTrue(ok)
        self.assertEqual(report, "DevSmokeDB.eval: ok, ran 7\nfirst\nsecond")

    def test_format_eval_puts_the_error_after_the_output(self):
        report, ok = fc.format_eval({"ran": 7, "ok": False, "out": {1: "before"}, "err": "boom\nstack"})
        self.assertFalse(ok)
        self.assertEqual(report, "DevSmokeDB.eval: failed, ran 7\nbefore\nerror:\nboom\nstack")

    def test_saved_eval_is_missing_when_the_snippet_did_not_run(self):
        with mock.patch.object(fc, "CLIENT", self.state / "client"):
            self.saved_smoke(None)
            with self.assertRaisesRegex(fc.ClientError, "DevSmokeDB.eval is missing"):
                fc.saved_eval()


if __name__ == "__main__":
    unittest.main()
