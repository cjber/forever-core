"""Specs for tools/headless/forever_client.py: the parts that hold without a game client."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import importlib.util
import io
import json
import os
import signal
import subprocess
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


def dead_pid() -> int:
    """A pid no process owns any more: a child that has exited and been reaped, so it reads as gone."""
    for _attempt in range(5):
        child = subprocess.Popen(["true"])
        child.wait()
        try:
            os.kill(child.pid, 0)
        except ProcessLookupError:
            return child.pid
    raise AssertionError("no exited child's pid reads as gone")


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
            '{"umu_run":"/faugus/umu-run","env":{"PROTONPATH":"/runner","GAMEID":"umu-x","DISPLAY":":host",'
            '"WAYLAND_DISPLAY":"host","XDG_RUNTIME_DIR":"/stale/runtime"}}'
        )
        client = self.state / "client"
        (client / "Interface/AddOns").mkdir(parents=True)
        with (
            mock.patch.object(fc, "CONFIG", config),
            mock.patch.object(fc, "CLIENT", client),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection"),
            mock.patch.object(fc.signal, "signal") as install,
            mock.patch.object(fc.signal, "alarm"),
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "child_env", return_value={"DISPLAY": ":3", "GAMESCOPE_WAYLAND_DISPLAY": "private"}),
            mock.patch.object(fc, "wait_for_world") as wait,
            mock.patch.object(fc, "client_pid", return_value=None) as client_pid,
            mock.patch.object(fc, "game_focused", return_value=True),
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
        handled = {call.args[0] for call in install.call_args_list}
        self.assertEqual(handled, {fc.signal.SIGTERM, fc.signal.SIGHUP, fc.signal.SIGINT, fc.signal.SIGALRM})
        env = spawn.call_args.kwargs["env"]
        command = spawn.call_args.args[0]
        self.assertEqual(command[command.index("--") + 1 :], ["/faugus/umu-run", str(fc.LAUNCHER), *fc.LAUNCH_ARGS])
        self.assertEqual(env["WINEPREFIX"], str(fc.PREFIX))
        self.assertEqual((env["PROTONPATH"], env["GAMEID"]), ("/runner", "umu-x"))
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

    def test_up_asks_for_a_faugus_capture_over_an_older_wine_launch(self):
        config = self.state / "env.json"
        config.write_text('{"WINE":"/runner/bin/wine"}')
        with (
            mock.patch.object(fc, "CONFIG", config),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection"),
            mock.patch.object(fc.subprocess, "Popen") as spawn,
            self.assertRaisesRegex(fc.ClientError, "start Battle.net from Faugus"),
        ):
            fc.up(args())
        spawn.assert_not_called()

    def test_proton_pfx_link_counts_as_the_prefix(self):
        prefix = self.state / "battlenet"
        prefix.mkdir()
        (prefix / "pfx").symlink_to(".")
        self.assertTrue(fc.in_prefix({"WINEPREFIX": f"{prefix}/pfx/"}, prefix))
        self.assertTrue(fc.in_prefix({"WINEPREFIX": str(prefix)}, prefix))
        self.assertFalse(fc.in_prefix({"WINEPREFIX": str(self.state)}, prefix))
        self.assertFalse(fc.in_prefix({}, prefix))

    def test_capture_env_records_faugus_umu_launch(self):
        config = self.state / "env.json"
        environ = {
            "WINEPREFIX": str(fc.PREFIX),
            "PROTONPATH": "/runner",
            "GAMEID": "umu-x",
            "UMU_USE_STEAM": "1",
            "UMU_INVOCATION_ID": "once",
            "HOME": "/home/x",
        }
        with (
            mock.patch.object(fc, "CONFIG", config),
            mock.patch.object(fc, "umu_launch", return_value=(7, "/faugus/umu-run")),
            mock.patch.object(fc, "read_environ", return_value=environ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.capture_env(), 0)
        recorded = json.loads(config.read_text())
        self.assertEqual(recorded["umu_run"], "/faugus/umu-run")
        self.assertEqual(
            recorded["env"],
            {"WINEPREFIX": str(fc.PREFIX), "PROTONPATH": "/runner", "GAMEID": "umu-x", "UMU_USE_STEAM": "1"},
        )

    def test_up_refuses_while_the_players_client_runs(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[42, 43]),
            mock.patch.object(fc, "client_pid", return_value=43),
            self.assertRaisesRegex(fc.ClientError, r"player's client is running .*pid 43"),
        ):
            fc.up(args())

    def test_up_puts_back_a_record_a_stopped_session_left_before_it_checks_the_client(self):
        addons = self.state / "AddOns"
        addons.mkdir()
        slot = addons / "LegacyForever"
        slot.symlink_to(self.state / "build")
        fc.link_record_path().write_text(
            json.dumps({"owner": {"pid": dead_pid(), "started": 1}, "links": [{"slot": str(slot), "was": None}]})
        )
        with mock.patch.object(fc, "prefix_users", return_value=[42]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(fc.ClientError, "in use"):
                fc.up(args())
        self.assertFalse(slot.is_symlink())
        self.assertFalse(fc.link_record_path().exists())

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

    def test_character_select_nudge_waits_while_the_launcher_has_focus(self):
        state = {"display": ":1"}
        with (
            mock.patch.object(fc, "client_pid", return_value=456),
            mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(stdout="Battle.net\n")),
            mock.patch.object(fc, "x") as x,
        ):
            fc.at_character_select(state, False)
        x.assert_not_called()

    def test_character_select_nudge_enters_the_world_when_the_game_has_focus(self):
        state = {"display": ":1"}
        with (
            mock.patch.object(fc, "client_pid", return_value=456),
            mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(stdout="World of Warcraft\n")),
            mock.patch.object(fc, "x") as x,
        ):
            fc.at_character_select(state, False)
        self.assertEqual(x.call_args_list, [mock.call(state, "key", "Return")])

    def test_character_select_nudge_presses_play_with_the_automatic_launcher(self):
        state = {"display": ":1"}
        with (
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "press_play") as press_play,
            mock.patch.object(fc, "x") as x,
        ):
            fc.at_character_select(state, False)
        press_play.assert_called_once_with(state)
        x.assert_not_called()

    def test_character_select_nudge_leaves_the_manual_launcher_alone(self):
        state = {"display": ":1"}
        with (
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "press_play") as press_play,
            mock.patch.object(fc, "x") as x,
        ):
            fc.at_character_select(state, True)
        press_play.assert_not_called()
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
            fc.teardown(game, {"PROTONPATH": "/runner"}, None, {"display": ":1", "token": "owned"})
        server = Path("/runner/files/bin/wineserver").resolve()
        self.assertEqual(kill.call_args_list, [mock.call(42, "owned", server), mock.call(43, "owned", server)])

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


class BuildDevTest(unittest.TestCase):
    """The dev build rebuild-dev.sh made, now one function: the commit's tree, stripped and stamped."""

    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "WORKSPACE", self.workspace))
        self.enterContext(mock.patch.object(fc, "BUILD_ROOT", self.workspace / "test-artifacts"))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.workspace / "state"))
        self.repo = self.workspace / "legacy-forever"
        (self.repo / "Core").mkdir(parents=True)
        (self.repo / "tools").mkdir()
        (self.repo / "docs").mkdir()
        (self.repo / "LegacyForever.toc").write_bytes(b"## Version: @project-version@\r\nCore\\Core.lua\r\n")
        (self.repo / "Core/Core.lua").write_text("-- the addon\n")
        (self.repo / "Core/Spec.lua").write_text("-- shipped\n")
        (self.repo / "tools/spec.py").write_text("print(1)\n")
        (self.repo / "docs/readme.md").write_text("# docs\n")
        (self.repo / ".pkgmeta").write_text("package-as: LegacyForever\n")
        (self.repo / "reference").mkdir()
        (self.repo / "reference/Other.toc").write_text("## Version: @project-version@\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-qm", "one")
        self.git("tag", "v1.2.3")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def test_the_build_is_the_tree_without_the_development_folders(self):
        built = fc.build_dev("legacy-forever", "HEAD")
        self.assertEqual(built, self.workspace / "test-artifacts/legacy-forever-dev")
        self.assertEqual((built / "Core/Core.lua").read_text(), "-- the addon\n")
        self.assertFalse((built / "tools").exists())
        self.assertFalse((built / "docs").exists())
        self.assertFalse((built / ".pkgmeta").exists())
        stamped = (built / "LegacyForever.toc").read_bytes()
        self.assertNotIn(b"@project-version@", stamped)
        self.assertTrue(stamped.endswith(b"Core\\Core.lua\r\n"), stamped)
        self.assertRegex(stamped, rb"## Version: v1\.2\.3-dev\+[0-9a-f]{1,}\r\n")

    def test_the_build_replaces_the_previous_one_atomically(self):
        first = fc.build_dev("legacy-forever", "HEAD")
        (self.repo / "Core/Core.lua").write_text("-- changed\n")
        self.git("-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-qam", "two")
        again = fc.build_dev("legacy-forever", "HEAD")
        self.assertEqual(first, again)
        self.assertEqual((again / "Core/Core.lua").read_text(), "-- changed\n")
        self.assertFalse((self.workspace / "test-artifacts/legacy-forever-dev.new").exists())
        self.assertFalse((self.workspace / "test-artifacts/legacy-forever-dev.old").exists())

    def test_a_build_that_fails_leaves_the_previous_build_in_place(self):
        built = fc.build_dev("legacy-forever", "HEAD")
        with self.assertRaisesRegex(fc.ClientError, "git"):
            fc.build_dev("legacy-forever", "no-such-ref")
        self.assertEqual((built / "Core/Core.lua").read_text(), "-- the addon\n")

    def test_a_repository_with_no_release_is_stamped_v0_0_0(self):
        self.git("tag", "-d", "v1.2.3")
        built = fc.build_dev("legacy-forever", "HEAD")
        self.assertRegex((built / "LegacyForever.toc").read_bytes(), rb"## Version: v0\.0\.0-dev\+")

    def test_build_dev_cli_refuses_a_release_tag(self):
        out = io.StringIO()
        with (
            mock.patch.object(fc, "WORKSPACE", self.workspace),
            mock.patch.object(fc, "build_dev") as build,
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(fc.main(["build-dev", "legacy-forever", "v1.2.3"]), 0)
        build.assert_not_called()
        self.assertIn("is release v1.2.3", out.getvalue())

    def test_build_dev_cli_puts_back_a_record_a_stopped_session_left(self):
        # The build is linked by hand next, so the leftover record is replayed before anything links this one.
        addons = self.workspace / "AddOns"
        addons.mkdir()
        slot = addons / "LegacyForever"
        slot.symlink_to(self.workspace / "test-artifacts/legacy-forever-dev")
        fc.link_record_path().parent.mkdir(parents=True)
        fc.link_record_path().write_text(
            json.dumps({"owner": {"pid": dead_pid(), "started": 1}, "links": [{"slot": str(slot), "was": None}]})
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fc.main(["build-dev", "legacy-forever", "v1.2.3"]), 0)
        self.assertFalse(slot.is_symlink())
        self.assertFalse(fc.link_record_path().exists())
        self.assertIn("LegacyForever (the link removed)", out.getvalue())


class AddonFoldersTest(unittest.TestCase):
    def test_package_as_names_the_one_folder_the_build_ships(self):
        build = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (build / "LegacyForever.toc").write_text("")
        (build / "reference").mkdir()
        (build / "reference/Other.toc").write_text("")
        (build / "LibAHTab").mkdir()
        (build / "LibAHTab/LibAHTab.toc").write_text("")
        self.assertEqual(fc.addon_folders(build, "LegacyForever"), [("LegacyForever", build)])

    def test_a_repository_without_pkgmeta_links_every_non_library_toc_folder(self):
        build = Path(self.enterContext(tempfile.TemporaryDirectory()))
        addon = build / "addon/KilnForever"
        addon.mkdir(parents=True)
        (addon / "KilnForever.toc").write_text("")
        (build / "LibAHTab").mkdir()
        (build / "LibAHTab/LibAHTab.toc").write_text("")
        self.assertEqual(fc.addon_folders(build), [("KilnForever", addon)])

    def test_package_name_reads_the_addon_out_of_pkgmeta(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        (root / ".pkgmeta").write_text("package-as: FieldGuideForever\n")
        (root / "FieldGuideForever.toc").write_text("")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.email=t@e.com", "-c", "user.name=T", "commit", "-qm", "one"],
            check=True,
        )
        self.assertEqual(fc.package_name(root, "HEAD"), "FieldGuideForever")
        self.assertIsNone(fc.package_name(root, "HEAD~5"))


class LinkBuildTest(unittest.TestCase):
    """The AddOns folder is shared, so every borrowed slot goes back exactly as it was."""

    def setUp(self):
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))
        self.addons = self.state / "AddOns"
        self.addons.mkdir()
        self.build = self.state / "build"
        self.build.mkdir()
        self.folders = [("LegacyForever", self.build)]

    def test_a_link_is_put_back_at_the_very_target_it_had(self):
        store = self.state / "store/LegacyForever"
        store.mkdir(parents=True)
        slot = self.addons / "LegacyForever"
        slot.symlink_to("../store/LegacyForever")
        records = fc.link_build(self.folders, self.addons)
        self.assertEqual(slot.readlink(), self.build)
        self.assertTrue(fc.link_record_path().exists())
        fc.restore_links(records)
        self.assertEqual(os.readlink(slot), "../store/LegacyForever")
        self.assertFalse(fc.link_record_path().exists())

    def test_a_store_install_is_moved_aside_and_moved_back(self):
        slot = self.addons / "LegacyForever"
        slot.mkdir()
        (slot / "LegacyForever.toc").write_text("## Version: 1.0.0\n")
        records = fc.link_build(self.folders, self.addons)
        self.assertEqual(slot.readlink(), self.build)
        self.assertTrue((self.addons / "LegacyForever.smoke-backup/LegacyForever.toc").exists())
        fc.restore_links(records)
        self.assertFalse(slot.is_symlink())
        self.assertTrue((slot / "LegacyForever.toc").exists())
        self.assertFalse((self.addons / "LegacyForever.smoke-backup").exists())

    def test_nothing_there_is_a_link_a_smoke_removes_again(self):
        records = fc.link_build(self.folders, self.addons)
        self.assertTrue((self.addons / "LegacyForever").is_symlink())
        fc.restore_links(records)
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.assertFalse((self.addons / "LegacyForever").is_symlink())

    def test_restoring_twice_changes_nothing_and_a_foreign_slot_is_left_alone(self):
        records = fc.link_build(self.folders, self.addons)
        fc.restore_links(records)
        fc.restore_links(records)
        self.assertFalse((self.addons / "LegacyForever").exists())
        slot = self.addons / "LegacyForever"
        slot.symlink_to(self.build)
        other = [{"slot": str(slot), "was": {"link": "/somewhere/else"}}]
        slot.unlink()
        slot.mkdir()  # something else took the slot after the smoke died
        with contextlib.redirect_stderr(io.StringIO()) as warning:
            fc.restore_links(other)
        self.assertIn("left alone", warning.getvalue())
        self.assertTrue(slot.is_dir())

    def test_a_leftover_backup_refuses_before_anything_changes(self):
        (self.addons / "LegacyForever.smoke-backup").mkdir()
        with self.assertRaisesRegex(fc.ClientError, "left over from an earlier smoke session"):
            fc.link_build(self.folders, self.addons)
        self.assertFalse((self.addons / "LegacyForever").exists())

    def killed_session(self, store: bool = True) -> Path:
        """What a session SIGKILLed after it linked leaves: its link in the slot and a record naming a gone process."""
        slot = self.addons / "LegacyForever"
        slot.symlink_to(self.build)
        if store:
            aside = self.addons / "LegacyForever.smoke-backup"
            aside.mkdir()
            (aside / "LegacyForever.toc").write_text("## Version: 1.0.0\n")
            was = {"moved": str(aside)}
        else:
            was = {"link": "/store/LegacyForever"}
        fc.link_record_path().write_text(
            json.dumps({"owner": {"pid": dead_pid(), "started": 1}, "links": [{"slot": str(slot), "was": was}]})
        )
        return slot

    def test_the_record_names_the_session_that_wrote_it(self):
        records = fc.link_build(self.folders, self.addons)
        record = json.loads(fc.link_record_path().read_text())
        self.assertEqual(record["owner"], {"pid": os.getpid(), "started": fc.process_start(os.getpid())})
        self.assertEqual(record["links"], records)

    def test_a_record_from_a_killed_session_puts_the_store_install_back(self):
        slot = self.killed_session()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(slot.is_symlink())
        self.assertTrue((slot / "LegacyForever.toc").exists())
        self.assertFalse((self.addons / "LegacyForever.smoke-backup").exists())
        self.assertFalse(fc.link_record_path().exists())
        self.assertIn("put back the AddOns links a stopped session left behind", out.getvalue())
        self.assertIn("LegacyForever (store install back)", out.getvalue())

    def test_a_record_from_a_killed_session_puts_a_link_back_at_its_own_target(self):
        slot = self.killed_session(store=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fc.recover_links(), 1)
        self.assertEqual(os.readlink(slot), "/store/LegacyForever")
        self.assertFalse(fc.link_record_path().exists())

    def older_record(self) -> Path:
        """A record an older version wrote: the bare list of links, naming no owner."""
        slot = self.killed_session()
        record = json.loads(fc.link_record_path().read_text())
        fc.link_record_path().write_text(json.dumps(record["links"]))
        return slot

    def test_a_record_an_older_version_wrote_without_an_owner_is_replayed(self):
        slot = self.older_record()
        with (
            mock.patch.object(fc, "client_in_use", return_value=None),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(slot.is_symlink())
        self.assertTrue((slot / "LegacyForever.toc").exists())

    def test_an_ownerless_record_is_left_alone_while_a_session_holds_the_client(self):
        # An older version's live smoke writes this record too, so it may not be stale while the client is held.
        slot = self.older_record()
        err = io.StringIO()
        with (
            mock.patch.object(fc, "client_in_use", return_value="another session holds the client"),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(fc.recover_links(), 0)
        self.assertTrue(slot.is_symlink())
        self.assertTrue(fc.link_record_path().exists())
        self.assertIn("belongs to a running session", err.getvalue())

    def test_the_session_that_wrote_a_record_leaves_its_own_links_alone(self):
        # The smoke reads the record back when its own `up` starts: it must not undo the links it has just made.
        fc.link_build(self.folders, self.addons)
        self.assertEqual(fc.recover_links(), 0)
        self.assertTrue((self.addons / "LegacyForever").is_symlink())
        self.assertTrue(fc.link_record_path().exists())

    def test_a_record_from_a_session_that_still_runs_is_left_alone(self):
        slot = self.killed_session()
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(sleeper.wait)
        self.addCleanup(sleeper.kill)
        record = json.loads(fc.link_record_path().read_text())
        record["owner"] = {"pid": sleeper.pid, "started": fc.process_start(sleeper.pid)}
        fc.link_record_path().write_text(json.dumps(record))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(fc.recover_links(), 0)
        self.assertTrue(slot.is_symlink())
        self.assertTrue(fc.link_record_path().exists())
        self.assertIn("belongs to a running session", err.getvalue())

    def test_a_reused_pid_does_not_keep_a_dead_sessions_links_in_place(self):
        slot = self.killed_session()
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(sleeper.wait)
        self.addCleanup(sleeper.kill)
        record = json.loads(fc.link_record_path().read_text())
        record["owner"] = {"pid": sleeper.pid, "started": fc.process_start(sleeper.pid) - 1}
        fc.link_record_path().write_text(json.dumps(record))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(slot.is_symlink())

    def test_an_empty_record_is_removed_with_nothing_to_put_back(self):
        fc.link_record_path().write_text(json.dumps({"owner": {"pid": dead_pid(), "started": 1}, "links": []}))
        self.assertEqual(fc.recover_links(), 0)
        self.assertFalse(fc.link_record_path().exists())

    def test_a_record_that_cannot_be_read_refuses_instead_of_guessing(self):
        for text in ("{", "{}", '{"links": [{"was": null}]}'):
            with self.subTest(record=text):
                fc.link_record_path().write_text(text)
                with self.assertRaisesRegex(fc.ClientError, "put the AddOns folder back by hand"):
                    fc.recover_links()


class ClientInUseTest(unittest.TestCase):
    def setUp(self):
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))

    def test_the_players_client_is_named(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[43]),
            mock.patch.object(fc, "client_pid", return_value=43),
        ):
            self.assertIn("player's client is running", fc.client_in_use())

    def test_another_sessions_lock_is_named(self):
        holder = open(self.state / "lock", "w")
        self.addCleanup(holder.close)
        fcntl.flock(holder, fcntl.LOCK_EX)
        with mock.patch.object(fc, "prefix_users", return_value=[]):
            self.assertEqual(fc.client_in_use(), "another session holds the client")

    def test_a_free_client_is_none(self):
        with mock.patch.object(fc, "prefix_users", return_value=[]):
            self.assertIsNone(fc.client_in_use())


class StopHandlersTest(unittest.TestCase):
    """A stop aimed at the Python process always puts the AddOns links back, however it arrives."""

    def test_a_ctrl_c_a_sigterm_and_a_hangup_all_raise_the_restore(self):
        previous = fc.stop_handlers()
        try:
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                handler = signal.getsignal(signum)
                with self.assertRaises(KeyboardInterrupt):
                    handler(signum, None)
        finally:
            fc.restore_handlers(previous)


class SmokeTest(unittest.TestCase):
    """The release smoke: build, selftest, errors per folder, one commit status, links put back."""

    def setUp(self):
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))
        self.client = self.state / "client"
        self.addons = self.client / "Interface/AddOns"
        self.addons.mkdir(parents=True)
        self.enterContext(mock.patch.object(fc, "CLIENT", self.client))
        self.build = self.state / "build"
        self.build.mkdir()
        self.workspace = self.state / "workspace"
        (self.workspace / "legacy-forever").mkdir(parents=True)
        self.enterContext(mock.patch.object(fc, "WORKSPACE", self.workspace))
        self.posted = mock.Mock()
        self.up = mock.Mock(side_effect=self.start_session)

    def start_session(self, options, after_ready=None):
        state = {"started": 1.0, "ready": 2.0, "display": ":1"}
        return after_ready(state) if after_ready else 0

    def report(self, *counts):
        """`errors --addon` answering with one live group per count, as forever_errors.py --json does."""
        answers = [
            mock.Mock(returncode=1 if count else 0, stdout=json.dumps([{"signature": "x"}] * count), stderr="")
            for count in counts
        ]
        return mock.patch.object(fc, "errors", side_effect=answers)

    def smoke(self, argv=None):
        options = {"repo": "legacy-forever", "ref": "main", "timeout": 600, "manual_launcher": False}
        options.update(argv or {})
        return fc.smoke(argparse.Namespace(**options))

    def run_smoke(self, answers=(0,), busy=None, later=None, up=None, main_argv=None):
        with (
            mock.patch.object(fc, "git", return_value="0123456789abcdef0123456789abcdef01234567"),
            mock.patch.object(fc, "client_in_use", side_effect=[busy, later, None, None]),
            mock.patch.object(fc, "build_dev", return_value=self.build) as build,
            mock.patch.object(fc, "package_name", return_value="LegacyForever"),
            mock.patch.object(fc, "addon_folders", return_value=[("LegacyForever", self.build)]),
            mock.patch.object(fc, "up", up or self.up),
            mock.patch.object(fc, "slash"),
            mock.patch.object(fc, "post_status", self.posted),
            mock.patch.object(fc, "stop_handlers", return_value={}),
            mock.patch.object(fc, "restore_handlers"),
            self.report(*answers),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            code = fc.main(main_argv) if main_argv else self.smoke()
        return code, out.getvalue(), build

    def test_a_clean_commit_posts_success_and_exits_zero(self):
        code, printed, _build = self.run_smoke()
        self.assertEqual(code, 0)
        self.posted.assert_called_once_with(
            "legacy-forever",
            "0123456789abcdef0123456789abcdef01234567",
            True,
            "clean: no Lua errors in 1 addon folder",
        )
        self.assertIn("headless-smoke posted", printed)
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_manual_launcher_flag_reaches_up(self):
        argv = ["smoke", "--repo", "legacy-forever", "--ref", "main"]
        code, _printed, _build = self.run_smoke(main_argv=argv)
        self.assertEqual(code, 0)
        self.assertFalse(self.up.call_args.args[0].manual_launcher)
        code, _printed, _build = self.run_smoke(main_argv=[*argv, "--manual-launcher"])
        self.assertEqual(code, 0)
        self.assertTrue(self.up.call_args.args[0].manual_launcher)

    def test_errors_post_failure_with_the_count(self):
        code, _printed, _build = self.run_smoke(answers=(3,))
        self.assertEqual(code, 1)
        self.posted.assert_called_once()
        self.assertFalse(self.posted.call_args.args[2])
        self.assertEqual(self.posted.call_args.args[3], "3 Lua errors: 3 LegacyForever")

    def test_a_client_in_use_posts_nothing_and_exits_three(self):
        code, printed, build = self.run_smoke(busy="the player's client is running (Wow.exe, pid 43)")
        self.assertEqual(code, 3)
        self.posted.assert_not_called()
        build.assert_not_called()
        self.assertIn("client in use", printed)

    def test_the_session_stops_at_once_when_wine_fills_with_the_players_client(self):
        def start(_options, after_ready=None):
            raise fc.ClientError("the Wine prefix is in use")

        code, _printed, _build = self.run_smoke(up=start, later="the player's client is running")
        self.assertEqual(code, 3)
        self.posted.assert_not_called()
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_session_that_cannot_start_posts_failure(self):
        def start(_options, after_ready=None):
            raise fc.ClientError("the world did not load within 600 s")

        code, _printed, _build = self.run_smoke(up=start)
        self.assertEqual(code, 1)
        self.assertEqual(self.posted.call_args.args[2], False)
        self.assertIn("no result: the world did not load", self.posted.call_args.args[3])
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_client_in_use_that_clears_during_the_build_still_posts(self):
        code, _printed, _build = self.run_smoke(busy=None)
        self.assertEqual(code, 0)
        self.posted.assert_called_once()

    def leftover(self) -> Path:
        """What a SIGKILLed smoke leaves: the store install aside, its link in the slot, and the record."""
        slot = self.addons / "LegacyForever"
        slot.symlink_to(self.build)
        aside = self.addons / "LegacyForever.smoke-backup"
        aside.mkdir()
        (aside / "LegacyForever.toc").write_text("## Version: 1.0.0\n")
        fc.link_record_path().write_text(
            json.dumps(
                {
                    "owner": {"pid": dead_pid(), "started": 1},
                    "links": [{"slot": str(slot), "was": {"moved": str(aside)}}],
                }
            )
        )
        return slot

    def test_a_leftover_record_is_put_back_before_the_smoke_links(self):
        slot = self.leftover()
        code, printed, _build = self.run_smoke()
        self.assertEqual(code, 0)
        self.posted.assert_called_once()
        self.assertFalse(slot.is_symlink())
        self.assertTrue((slot / "LegacyForever.toc").exists())
        self.assertFalse(fc.link_record_path().exists())
        self.assertIn("store install back", printed)

    def test_a_leftover_record_is_put_back_even_when_the_client_is_in_use(self):
        slot = self.leftover()
        code, _printed, build = self.run_smoke(busy="the player's client is running (Wow.exe, pid 43)")
        self.assertEqual(code, 3)
        build.assert_not_called()
        self.posted.assert_not_called()
        self.assertFalse(slot.is_symlink())
        self.assertTrue((slot / "LegacyForever.toc").exists())
        self.assertFalse(fc.link_record_path().exists())

    def test_a_sigterm_restores_the_links_and_posts_nothing(self):
        def stop(_options, after_ready=None):
            raise KeyboardInterrupt

        code, _printed, _build = self.run_smoke(up=stop)
        self.assertEqual(code, 1)
        self.posted.assert_not_called()
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_session_up_returns_from_without_a_result_posts_nothing(self):
        # `up` turns SIGTERM into a normal return after its own teardown, so an empty result is a stopped session.
        code, _printed, _build = self.run_smoke(up=lambda _options, after_ready=None: 0)
        self.assertEqual(code, 1)
        self.posted.assert_not_called()
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_the_selftest_runs_before_the_errors_are_read(self):
        calls = []

        def start(_options, after_ready=None):
            return after_ready({"started": 1.0, "ready": 2.0})

        with (
            mock.patch.object(fc, "git", return_value="a" * 40),
            mock.patch.object(fc, "client_in_use", return_value=None),
            mock.patch.object(fc, "build_dev", return_value=self.build),
            mock.patch.object(fc, "package_name", return_value="LegacyForever"),
            mock.patch.object(fc, "addon_folders", return_value=[("LegacyForever", self.build)]),
            mock.patch.object(fc, "up", side_effect=start),
            mock.patch.object(fc, "slash", side_effect=lambda _state, command: calls.append(command)),
            mock.patch.object(fc, "errors", return_value=mock.Mock(returncode=0, stdout="[]", stderr="")) as read,
            mock.patch.object(fc, "post_status"),
            mock.patch.object(fc, "stop_handlers", return_value={}),
            mock.patch.object(fc, "restore_handlers"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(self.smoke(), 0)
        self.assertEqual(calls, ["/forever selftest"])
        read.assert_called_once_with(mock.ANY, "LegacyForever", as_json=True)

    def test_a_smoke_rejects_a_repository_name_that_is_a_path(self):
        with self.assertRaisesRegex(fc.ClientError, "repository name"):
            self.smoke({"repo": "../etc"})

    def test_a_missing_checkout_says_where_it_looked(self):
        with self.assertRaisesRegex(fc.ClientError, "no checkout of other-repo"):
            self.smoke({"repo": "other-repo"})

    def test_an_errors_read_that_prints_no_json_fails_the_smoke(self):
        with (
            mock.patch.object(fc, "git", return_value="a" * 40),
            mock.patch.object(fc, "client_in_use", return_value=None),
            mock.patch.object(fc, "build_dev", return_value=self.build),
            mock.patch.object(fc, "package_name", return_value="LegacyForever"),
            mock.patch.object(fc, "addon_folders", return_value=[("LegacyForever", self.build)]),
            mock.patch.object(fc, "up", side_effect=self.start_session),
            mock.patch.object(fc, "slash"),
            mock.patch.object(fc, "errors", return_value=mock.Mock(returncode=0, stdout="oops", stderr="")),
            mock.patch.object(fc, "post_status") as posted,
            mock.patch.object(fc, "stop_handlers", return_value={}),
            mock.patch.object(fc, "restore_handlers"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = self.smoke()
        self.assertEqual(code, 1)
        self.assertIn("printed no JSON", posted.call_args.args[3])

    def test_a_description_stays_under_the_status_limit(self):
        counts = {f"Addon{index}": 9 for index in range(20)}
        description = fc.smoke_description(counts)
        self.assertLessEqual(len(description), 140)
        self.assertTrue(description.startswith("180 Lua errors"))

    def test_the_status_is_posted_on_the_exact_commit(self):
        with mock.patch.object(
            fc.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="{}", stderr="")
        ) as run:
            fc.post_status("legacy-forever", "a" * 40, False, "2 Lua errors: 2 LegacyForever")
        self.assertEqual(run.call_args.args[0][:2], ["gh", "api"])
        self.assertEqual(run.call_args.args[0][2], f"repos/cjber/legacy-forever/statuses/{'a' * 40}")
        for value in (
            "state=failure",
            "context=headless-smoke",
            "description=2 Lua errors: 2 LegacyForever",
        ):
            self.assertIn(value, run.call_args.args[0])

    def test_a_status_that_cannot_be_posted_is_an_error(self):
        failed = mock.Mock(returncode=1, stdout="", stderr="gh: Bad credentials (HTTP 401)")
        with (
            mock.patch.object(fc.subprocess, "run", return_value=failed),
            self.assertRaisesRegex(fc.ClientError, "could not post headless-smoke.*Bad credentials"),
        ):
            fc.post_status("legacy-forever", "a" * 40, True, "clean")


class ProofHelpersTest(unittest.TestCase):
    """The pieces of `proof` that hold without a client or a network."""

    def setUp(self):
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "PROOF_SCRATCH", self.state / "scratch"))

    def test_parse_flows_takes_a_named_slash_command_and_a_lua_file(self):
        lua = self.state / "notice.lua"
        lua.write_text("print('shown')\n")
        self.assertEqual(
            fc.parse_flows([f"update notice={lua}", "map=/lf"]),
            [("update notice", str(lua)), ("map", "/lf")],
        )
        self.assertEqual(fc.parse_flows([f"absolute={lua.resolve()}"]), [("absolute", str(lua.resolve()))])
        for bad in ("/lf", "= /lf", "map=", "map=missing.lua", "map=lf", "map=/nowhere/missing.lua"):
            with self.subTest(bad=bad), self.assertRaises(fc.ClientError):
                fc.parse_flows([bad])

    def test_flow_slug_is_a_file_name(self):
        self.assertEqual(fc.flow_slug("Update notice!"), "update-notice")
        self.assertEqual(fc.flow_slug("***"), "flow")

    def test_run_flow_sends_a_slash_command_without_an_eval(self):
        with (
            mock.patch.object(fc, "slash") as slash,
            mock.patch.object(fc, "devsmoke_eval") as tool,
            mock.patch.object(fc.time, "sleep") as sleep,
        ):
            fc.run_flow({}, "/lf")
        slash.assert_called_once_with({}, "/lf")
        tool.assert_not_called()
        sleep.assert_called_once_with(fc.SLASH_SETTLE_SECONDS)

    def test_run_flow_writes_reloads_and_checks_a_lua_snippet(self):
        tool = mock.Mock()
        tool.write_snippet.return_value = {
            "chunk": Path("/x/!!DevSmokeInbox/Eval.lua"),
            "snippet": Path("notice.lua"),
            "lines": 3,
        }
        tool.EvalError = Exception
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "reload") as reload,
            mock.patch.object(fc, "saved_eval", return_value={"ok": True, "ran": 1}),
            mock.patch.object(fc, "format_eval", return_value=("DevSmokeDB.eval: ok, ran 1", True)),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            fc.run_flow("state", "notice.lua")
        reload.assert_called_once_with("state")
        tool.write_snippet.assert_called_once_with(Path("notice.lua"), addons=self.state / "client/Interface/AddOns")
        self.assertIn("DevSmokeDB.eval: ok, ran 1", out.getvalue())

    def test_run_flow_runs_a_lua_file_given_by_its_absolute_path(self):
        with (
            mock.patch.object(fc, "slash") as slash,
            mock.patch.object(fc, "devsmoke_eval", side_effect=RuntimeError("evaluated")),
            self.assertRaisesRegex(RuntimeError, "evaluated"),
        ):
            fc.run_flow({}, "/home/me/notice.lua")
        slash.assert_not_called()

    def test_run_flow_reports_a_failed_lua_snippet(self):
        tool = mock.Mock()
        tool.write_snippet.return_value = {"chunk": Path("/x/Eval.lua"), "snippet": Path("notice.lua"), "lines": 3}
        tool.EvalError = Exception
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "reload"),
            mock.patch.object(fc, "saved_eval", return_value={"ok": False}),
            mock.patch.object(fc, "format_eval", return_value=("DevSmokeDB.eval: failed\nerror:\nboom", False)),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(fc.ClientError, "flow snippet notice.lua failed"),
        ):
            fc.run_flow("state", "notice.lua")

    def test_client_build_reads_the_session_log_and_the_toc_interface(self):
        client = self.state / "client"
        (client / "Logs").mkdir(parents=True)
        (client / "Logs/gx.log").write_text("11/13 14:59:14.102  [0] World of Warcraft Retail x86_64 1.60.1.70938\n")
        addon = self.state / "addon"
        addon.mkdir()
        (addon / "LegacyForever.toc").write_text("## Interface: 16001\r\n## Version: 1.0.0\r\n")
        with mock.patch.object(fc, "CLIENT", client):
            self.assertEqual(fc.client_build(addon), "1.60.1.70938 (Interface 16001)")

    def test_client_build_refuses_a_session_log_without_a_build_line(self):
        client = self.state / "client"
        (client / "Logs").mkdir(parents=True)
        (client / "Logs/gx.log").write_text("no build here\n")
        addon = self.state / "addon"
        addon.mkdir()
        with mock.patch.object(fc, "CLIENT", client), self.assertRaisesRegex(fc.ClientError, "wrote no build line"):
            fc.client_build(addon)

    def test_run_tool_reports_the_tools_own_error(self):
        failed = mock.Mock(returncode=1, stdout="", stderr="gh: not logged in")
        with (
            mock.patch.object(fc.subprocess, "run", return_value=failed),
            self.assertRaisesRegex(fc.ClientError, "could not create the proof gist: gh: not logged in"),
        ):
            fc.run_tool(["gh", "gist", "create"], "create the proof gist")

    def test_create_gist_puts_a_readme_in_the_new_secret_gist(self):
        completed = mock.Mock(returncode=0, stdout="https://gist.github.com/cjber/abc123\n", stderr="")
        with mock.patch.object(fc, "run_tool", return_value=completed) as run:
            gist = fc.create_gist("proof for legacy-forever", self.state / "shots")
        self.assertEqual(gist, "abc123")
        self.assertIn("--desc", run.call_args.args[0])
        self.assertIn("# WoW: Forever visual proof", (self.state / "shots/README.md").read_text())

    def test_create_gist_refuses_output_without_a_gist_url(self):
        completed = mock.Mock(returncode=0, stdout="created something\n", stderr="")
        with (
            mock.patch.object(fc, "run_tool", return_value=completed),
            self.assertRaisesRegex(fc.ClientError, "printed no gist URL"),
        ):
            fc.create_gist("proof", self.state / "shots")

    def test_upload_screenshots_pins_each_url_to_the_gist_commit(self):
        shots = self.state / "shots"
        shots.mkdir()
        image = shots / "1-update-notice.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\nbody")
        other = shots / "2-map.png"
        other.write_bytes(b"\x89PNG\r\n\x1a\nmap")

        def fake_run(command, purpose, cwd=None):
            if command[:2] == ["git", "clone"]:
                Path(command[-1]).mkdir(parents=True)
            if "rev-parse" in command:
                return mock.Mock(returncode=0, stdout="f" * 40 + "\n", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(fc, "run_tool", side_effect=fake_run):
            images = fc.upload_screenshots("abc123", [image, other], "proof")
        commit = "f" * 40
        self.assertEqual(
            [item["url"] for item in images],
            [
                f"https://gist.githubusercontent.com/cjber/abc123/raw/{commit}/1-update-notice.png",
                f"https://gist.githubusercontent.com/cjber/abc123/raw/{commit}/2-map.png",
            ],
        )
        self.assertEqual(images[0]["sha256"], fc.hashlib.sha256(image.read_bytes()).hexdigest())
        self.assertEqual(images[1]["sha256"], fc.hashlib.sha256(other.read_bytes()).hexdigest())

    def test_visual_proof_tool_uses_the_checkouts_own_checker(self):
        checkout = self.state / "checkout"
        wrapper = checkout / "tools/check_visual_proof.py"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("")
        self.assertEqual(fc.visual_proof_tool(checkout), [sys.executable, str(wrapper)])
        wrapper.unlink()
        tooling = checkout / "tools/forever_tools/visual_proof.py"
        tooling.parent.mkdir()
        tooling.write_text("")
        self.assertEqual(fc.visual_proof_tool(checkout), [sys.executable, "-m", "tools.forever_tools.visual_proof"])

    def test_visual_proof_tool_falls_back_to_cores_own_checker(self):
        checkout = self.state / "checkout"
        checkout.mkdir()
        self.assertEqual(Path(fc.visual_proof_tool(checkout)[1]).name, "check_visual_proof.py")

    def test_proof_digests_reads_the_json_or_names_the_failure(self):
        ok = mock.Mock(returncode=0, stdout=json.dumps({"input_digest": "a", "candidate": "b"}), stderr="")
        with mock.patch.object(fc, "visual_proof_run", return_value=ok):
            self.assertEqual(fc.proof_digests(self.state), {"input_digest": "a", "candidate": "b"})
        for failed in (
            mock.Mock(returncode=1, stdout="", stderr="unsupported TOC"),
            mock.Mock(returncode=0, stdout="oops", stderr=""),
        ):
            with (
                self.subTest(returncode=failed.returncode),
                mock.patch.object(fc, "visual_proof_run", return_value=failed),
                self.assertRaises(fc.ClientError),
            ):
                fc.proof_digests(self.state)

    def test_proof_compare_accepts_only_an_equivalent_installed_folder(self):
        good = mock.Mock(returncode=0, stdout=json.dumps({"equivalent": True}), stderr="")
        with mock.patch.object(fc, "visual_proof_run", return_value=good):
            self.assertTrue(fc.proof_compare(self.state, self.state / "installed")["equivalent"])
        bad = mock.Mock(
            returncode=1,
            stdout=json.dumps({"equivalent": False, "missing": ["UI/A.lua"], "differing": [], "extra": []}),
            stderr="",
        )
        with (
            mock.patch.object(fc, "visual_proof_run", return_value=bad),
            self.assertRaisesRegex(fc.ClientError, "missing: UI/A.lua"),
        ):
            fc.proof_compare(self.state, self.state / "installed")
        invalid = mock.Mock(returncode=1, stdout="not json", stderr="")
        with (
            mock.patch.object(fc, "visual_proof_run", return_value=invalid),
            self.assertRaisesRegex(fc.ClientError, "printed no JSON"),
        ):
            fc.proof_compare(self.state, self.state / "installed")


class ProofTest(unittest.TestCase):
    """`proof`: smoke's build and links, one reload, a shot per flow, a gist and the checkout's proof file."""

    def setUp(self):
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state / "state"))
        self.enterContext(mock.patch.object(fc, "PROOF_SCRATCH", self.state / "scratch"))
        self.enterContext(mock.patch.object(fc, "BUILD_ROOT", self.state / "builds"))
        self.client = self.state / "client"
        self.addons = self.client / "Interface/AddOns"
        self.addons.mkdir(parents=True)
        self.enterContext(mock.patch.object(fc, "CLIENT", self.client))
        self.workspace = self.state / "workspace"
        (self.workspace / "legacy-forever").mkdir(parents=True)
        self.enterContext(mock.patch.object(fc, "WORKSPACE", self.workspace))
        self.checkout = self.state / "checkout"
        self.checkout.mkdir()
        self.build = self.state / "build"
        (self.build / "UI").mkdir(parents=True)
        (self.build / "LegacyForever.toc").write_text("## Interface: 16001\n## Version: 1.0.0\n")
        (self.build / "UI/WhatsNew.lua").write_text("-- notice\n")
        self.commit = "a" * 40
        self.head = self.commit
        self.git_calls = []
        self.slashes = []
        self.shot_paths = []
        self.busy = [None, None]
        self.slash_error = None
        self.reload = mock.Mock()
        self.proof_digests = mock.Mock(return_value={"input_digest": "digest", "candidate": "candidate"})
        self.create_gist = mock.Mock(return_value="abc123")
        self.upload = mock.Mock(
            return_value=[{"url": "https://gist.example/raw/" + "f" * 40 + "/1-update-notice.png", "sha256": "0" * 64}]
        )
        self.client_build = mock.Mock(return_value="1.60.1.70938 (Interface 16001)")
        self.compare = mock.Mock(return_value={"equivalent": True})
        self.build_dev = mock.Mock(return_value=self.build)
        self.up = mock.Mock(side_effect=self.start_session)

    def start_session(self, options, after_ready=None):
        if after_ready:
            return after_ready({"started": 1.0, "ready": 2.0, "display": ":1"})
        return 0

    def options(self, **overrides):
        values = {
            "repo": "legacy-forever",
            "ref": "main",
            "checkout": self.checkout,
            "flow": ["update notice=/lf"],
            "timeout": 600,
            "manual_launcher": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def fake_git(self, root, *args):
        self.git_calls.append((root, *args))
        return self.head if root == self.checkout else self.commit

    def fake_slash(self, _state, command):
        if self.slash_error:
            raise fc.ClientError(self.slash_error)
        self.slashes.append(command)

    def fake_shot(self, _state, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + path.name.encode())
        self.shot_paths.append(path)
        return path

    def run_proof(self, **overrides):
        up = overrides.pop("up", None)
        with (
            mock.patch.object(fc, "git", side_effect=self.fake_git),
            mock.patch.object(fc, "client_in_use", side_effect=self.busy),
            mock.patch.object(fc, "recover_links"),
            mock.patch.object(fc, "build_dev", self.build_dev),
            mock.patch.object(fc, "package_name", return_value="LegacyForever"),
            mock.patch.object(fc, "addon_folders", return_value=[("LegacyForever", self.build)]),
            mock.patch.object(fc, "up", up or self.up),
            mock.patch.object(fc, "reload", self.reload),
            mock.patch.object(fc, "slash", side_effect=self.fake_slash),
            mock.patch.object(fc, "shot", side_effect=self.fake_shot),
            mock.patch.object(fc, "proof_digests", self.proof_digests),
            mock.patch.object(fc, "create_gist", self.create_gist),
            mock.patch.object(fc, "upload_screenshots", self.upload),
            mock.patch.object(fc, "client_build", self.client_build),
            mock.patch.object(fc, "proof_compare", self.compare),
            mock.patch.object(fc, "stop_handlers", return_value={}),
            mock.patch.object(fc, "restore_handlers"),
            mock.patch.object(fc.time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            code = fc.proof(self.options(**overrides))
        return code, out.getvalue(), err.getvalue()

    def test_the_manual_launcher_flag_reaches_up(self):
        code, _printed, _err = self.run_proof(manual_launcher=True)
        self.assertEqual(code, 0)
        self.assertTrue(self.up.call_args.args[0].manual_launcher)

    def test_the_build_is_the_smokes_build_beside_the_others(self):
        code, _printed, _err = self.run_proof()
        self.assertEqual(code, 0)
        self.assertEqual(self.build_dev.call_args.kwargs["destination"].name, "legacy-forever-proof")

    def test_a_repository_name_that_is_a_path_is_refused(self):
        with self.assertRaisesRegex(fc.ClientError, "repository name"):
            self.run_proof(repo="../etc")

    def test_a_missing_repository_checkout_says_where_it_looked(self):
        with self.assertRaisesRegex(fc.ClientError, "no checkout of other-repo"):
            self.run_proof(repo="other-repo")

    def test_a_proof_records_the_flows_their_screenshots_and_the_digests(self):
        code, printed, _err = self.run_proof()
        self.assertEqual(code, 0)
        proof = json.loads((self.checkout / ".visual-proof.json").read_text())
        self.assertEqual(proof["input_digest"], "digest")
        self.assertEqual(proof["runtime_sha256"], "digest")
        self.assertEqual(proof["candidate"], "candidate")
        self.assertEqual(proof["client_build"], "1.60.1.70938 (Interface 16001)")
        self.assertEqual(proof["tested_artifact"], "source-tree")
        self.assertEqual(proof["source_commit"], self.commit)
        self.assertEqual(proof["flows"], [{"name": "update notice", "steps": ["/lf"], "result": "pass"}])
        self.assertEqual(proof["images"], self.upload.return_value)
        self.assertEqual(self.slashes, ["/lf"])
        self.assertEqual([path.name for path in self.shot_paths], ["1-update-notice.png"])
        self.reload.assert_called_once()
        self.client_build.assert_called_once_with(self.build)
        self.compare.assert_called_once_with(self.checkout, self.build)
        self.assertIn("wrote", printed)
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_proof_compare_that_fails_removes_the_proof_it_wrote(self):
        self.compare.side_effect = fc.ClientError("installed build differs")
        with self.assertRaisesRegex(fc.ClientError, "installed build differs"):
            self.run_proof()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_the_checkout_is_never_committed_or_pushed(self):
        code, _printed, _err = self.run_proof()
        self.assertEqual(code, 0)
        self.assertTrue(all(call[1] == "rev-parse" for call in self.git_calls), self.git_calls)

    def test_a_busy_client_records_nothing(self):
        self.busy = ["the player's client is running (Wow.exe, pid 43)"]
        code, printed, _err = self.run_proof()
        self.assertEqual(code, 3)
        self.build_dev.assert_not_called()
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())
        self.assertIn("client in use", printed)

    def test_proof_needs_a_named_flow(self):
        with self.assertRaisesRegex(fc.ClientError, "needs at least one --flow"):
            fc.proof(self.options(flow=[]))
        self.build_dev.assert_not_called()

    def test_a_checkout_at_another_commit_is_refused(self):
        self.head = "b" * 40
        with self.assertRaisesRegex(fc.ClientError, "check out the proof's commit first"):
            self.run_proof()
        self.build_dev.assert_not_called()

    def test_a_missing_checkout_says_what_it_is_for(self):
        with self.assertRaisesRegex(fc.ClientError, "no checkout at"):
            fc.proof(self.options(checkout=self.state / "missing"))

    def test_a_session_that_stops_before_the_flows_records_nothing(self):
        code, _printed, err = self.run_proof(up=lambda _options, after_ready=None: 0)
        self.assertEqual(code, 1)
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())
        self.assertIn("stopped before it finished", err)

    def test_a_client_that_fills_while_the_build_links_stops_at_once(self):
        def start(_options, after_ready=None):
            raise fc.ClientError("the Wine prefix is in use")

        self.busy = [None, "the player's client is running (Wow.exe, pid 43)"]
        code, printed, _err = self.run_proof(up=start)
        self.assertEqual(code, 3)
        self.create_gist.assert_not_called()
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.assertIn("client in use", printed)

    def test_a_failed_flow_puts_the_links_back_and_records_nothing(self):
        def start(options, after_ready=None):
            return after_ready({"display": ":1"})

        self.slash_error = "refused /lf"
        with self.assertRaisesRegex(fc.ClientError, "refused /lf"):
            self.run_proof(up=start)
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())

    def test_a_flow_that_fails_in_the_world_reports_its_own_error_not_a_busy_client(self):
        # In the world the session holds the client's lock itself, so client_in_use would name it as another's.
        self.busy = [None, "another session holds the client", "another session holds the client"]
        self.slash_error = "refused /lf"
        with self.assertRaisesRegex(fc.ClientError, "refused /lf"):
            self.run_proof()

    def test_a_lua_flow_takes_a_shot_after_the_snippet_ran(self):
        lua = self.state / "notice.lua"
        lua.write_text("print('shown')\n")
        with (
            mock.patch.object(fc, "devsmoke_eval") as tool,
            mock.patch.object(fc, "saved_eval", return_value={"ok": True}),
            mock.patch.object(fc, "format_eval", return_value=("DevSmokeDB.eval: ok", True)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            tool.return_value.write_snippet.return_value = {
                "chunk": Path("/x/Eval.lua"),
                "snippet": lua,
                "lines": 1,
            }
            tool.return_value.EvalError = Exception
            code, _printed, _err = self.run_proof(flow=[f"update notice={lua}"])
        self.assertEqual(code, 0)
        self.assertEqual([path.name for path in self.shot_paths], ["1-update-notice.png"])

    def test_the_cli_passes_the_proof_options_through(self):
        with mock.patch.object(fc, "proof", return_value=3) as proof:
            code = fc.main(
                [
                    "proof",
                    "--repo",
                    "legacy-forever",
                    "--ref",
                    "main",
                    "--checkout",
                    str(self.checkout),
                    "--flow",
                    "update notice=/lf",
                    "--manual-launcher",
                ]
            )
        self.assertEqual(code, 3)
        options = proof.call_args.args[0]
        self.assertEqual(options.repo, "legacy-forever")
        self.assertEqual(options.checkout, self.checkout)
        self.assertEqual(options.flow, ["update notice=/lf"])
        self.assertTrue(options.manual_launcher)


if __name__ == "__main__":
    unittest.main()
