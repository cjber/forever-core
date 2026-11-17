"""Specs for tools/headless/forever_client.py: the parts that hold without a game client."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

from PIL import Image

SPEC = importlib.util.spec_from_file_location("forever_client", Path(__file__).parent / "headless/forever_client.py")
fc = importlib.util.module_from_spec(SPEC)
sys.modules["forever_client"] = fc
SPEC.loader.exec_module(fc)
REAL_REQUIRE_SAFE = fc.require_safe


def setUpModule():
    """Unmocked discovery must fail instead of inspecting the shared client or process table."""
    temporary = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(temporary.cleanup)
    root = Path(temporary.name)
    for name, value in (("STATE_DIR", root / "state"), ("CLIENT", root / "client"), ("CONFIG", root / "env.json")):
        patch = mock.patch.object(fc, name, value)
        patch.start()
        unittest.addModuleCleanup(patch.stop)
    for target, name in ((fc, "pids"), (fc.socket, "create_connection")):
        patch = mock.patch.object(target, name, side_effect=AssertionError(f"unit test must mock {name}"))
        patch.start()
        unittest.addModuleCleanup(patch.stop)


def args() -> argparse.Namespace:
    return argparse.Namespace(wait=False, timeout=5, manual_launcher=False)


def live_state(**extra) -> dict:
    """A session.json a live process wrote, for the verbs that re-check the session after taking the job lock."""
    return {
        "pid": os.getpid(),
        "start_ticks": fc.process_start(os.getpid()),
        "headless_addon_digest": fc.headless_addon_digest(),
        **extra,
    }


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
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.enterContext(mock.patch.object(fc, "require_safe"))
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))
        self.runtime = self.state / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.enterContext(
            mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.runtime), "FOREVER_CLIENT_CALLER": "in-game"})
        )
        # The host GPU is not part of a unit test; the driver-mismatch check has its own tests below.
        self.real_nvidia_mismatch = fc.nvidia_mismatch
        self.enterContext(mock.patch.object(fc, "nvidia_mismatch", return_value=None))

    def test_sign_in_labels_persist_and_block_later_starts(self):
        for label in ("Welcome back", "Email a code", "Use password", "Use passkey"):
            with (
                self.subTest(label=label),
                mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(stdout="12345")),
                mock.patch.object(fc.shutil, "which", return_value="tesseract"),
                mock.patch.object(fc, "client_pid", return_value=None),
                mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
                mock.patch.object(fc, "ocr_words", return_value=[(word, 95, 0, 0, 20, 20) for word in label.split()]),
                mock.patch.object(fc, "x") as send,
                mock.patch.object(fc, "start_serve") as start,
            ):
                with self.assertRaisesRegex(fc.ClientError, "needs the player's sign-in"):
                    fc.press_play({"display": ":1"})
                self.assertTrue((self.state / fc.SIGN_IN_BLOCK).exists())
                with self.assertRaisesRegex(fc.ClientError, "needs the player's sign-in"):
                    fc.ensure_session(5)
                with self.assertRaisesRegex(fc.ClientError, "needs the player's sign-in"):
                    fc.serve(args())
                start.assert_not_called()
                send.assert_not_called()

    def test_detached_serve_preserves_caller_and_drops_job_token(self):
        with (
            mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game", "FOREVER_CLIENT_JOB": "token"}),
            mock.patch.object(fc.subprocess, "Popen") as spawn,
        ):
            fc.start_serve(False)
        env = spawn.call_args.kwargs["env"]
        self.assertEqual(env["FOREVER_CLIENT_CALLER"], "in-game")
        self.assertNotIn("FOREVER_CLIENT_JOB", env)

    def test_manual_start_keeps_block_until_ready(self):
        block = self.state / fc.SIGN_IN_BLOCK
        block.write_text(fc.SIGN_IN_MESSAGE)
        session = {"ready": 1, "headless_addon_digest": fc.headless_addon_digest()}
        with (
            mock.patch.object(fc, "current_session", return_value=session),
            mock.patch.object(fc, "client_ui", return_value={"safety": True, "world": True}),
        ):
            fc.ensure_session(5, manual_launcher=True)
        self.assertTrue(block.exists())
        with (
            mock.patch.object(fc, "wait_for_world", side_effect=fc.ClientError("timeout")),
            mock.patch.object(fc, "shot"),
        ):
            with self.assertRaises(fc.ClientError):
                fc.reach_world({}, set(), 1, True, time.time())
        self.assertTrue(block.exists())
        with mock.patch.object(fc, "wait_for_world", return_value=Path("ready.png")):
            fc.reach_world({}, set(), 1, True, time.time())
        self.assertFalse(block.exists())

    def test_client_verbs_require_caller_before_dispatch(self):
        commands = [
            ["up"],
            ["serve"],
            ["job", "--", "true"],
            ["run", "--", "true"],
            ["lease"],
            ["smoke", "--repo", "x", "--ref", "main"],
            ["proof", "--repo", "x", "--ref", "main", "--checkout", "."],
            ["down"],
            ["shot"],
            ["click", "1", "2"],
            ["scroll", "1", "2", "3"],
            ["key", "Escape"],
            ["slash", "/fgf"],
            ["reload"],
            ["eval", "probe.lua"],
            ["errors"],
            ["release", "token"],
        ]
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(fc, "load_state") as load:
            for command in commands:
                with self.subTest(command=command), contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(fc.main(command), 2)
                    self.assertIn("INGAME request", err.getvalue())
                    self.assertIn("in-game.md#requesting-a-check", err.getvalue())
            load.assert_not_called()

    def test_job_token_and_caller_allow_dispatch_and_status_is_open(self):
        for marker in ("FOREVER_CLIENT_CALLER", "FOREVER_CLIENT_JOB"):
            with (
                mock.patch.dict(os.environ, {marker: "test"}, clear=True),
                mock.patch.object(fc, "down", return_value=0),
            ):
                self.assertEqual(fc.main(["down"]), 0)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(fc, "load_state", return_value={}):
            self.assertEqual(fc.main(["status"]), 0)

    def test_character_config_requires_explicit_identity_and_resting(self):
        valid = {"character": {"name": "Barry", "guid": "Player-1", "require_resting": True}}
        self.assertEqual(fc.character_config(valid)["guid"], "Player-1")
        for value in ({}, {"character": {}}, {"character": {"name": "Barry", "guid": "Player-1"}}):
            with self.assertRaises(fc.ClientError):
                fc.character_config(value)

    def test_lua_string_preserves_unicode_quotes_and_backslashes(self):
        self.assertEqual(fc.lua_string('Hé said "hi" \\'), '"Hé said \\"hi\\" \\\\"')
        with self.assertRaises(fc.ClientError):
            fc.lua_string("Barry\x00")

    def test_generated_addon_cleanup_is_atomic(self):
        source = self.state / "source-addon"
        source.mkdir()
        (source / "!!ForeverHeadless.toc").write_text("ForeverHeadless.lua\n")
        (source / "ForeverHeadless.lua").write_text("-- fixture\n")
        with mock.patch.object(fc, "ADDON", source):
            with self.assertRaises(fc.ClientError):
                fc.prepare_headless_addon({"name": "Bad\x00", "guid": "Player-1", "require_resting": True})
        self.assertFalse((self.state / "headless-addon").exists())

    def test_readiness_marker_accepts_native_jpeg_and_rejects_incomplete_png(self):
        def marker_image():
            image = Image.new("RGB", (32, 32), (0, 0, 0))
            for row, bits in enumerate(fc.HEADLESS_MARKER):
                for column, bit in enumerate(bits):
                    if bit == "1":
                        for x in range(column * fc.MARKER_CELL, (column + 1) * fc.MARKER_CELL):
                            for y in range(row * fc.MARKER_CELL, (row + 1) * fc.MARKER_CELL):
                                image.putpixel((x, y), (255, 255, 255))
            return image

        def png(image):
            raw = b"".join(
                b"\0" + b"".join(bytes(image.getpixel((x, y))) for x in range(image.width)) for y in range(image.height)
            )

            def chunk(kind, payload):
                checksum = struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
                return struct.pack(">I", len(payload)) + kind + payload + checksum

            header = chunk(b"IHDR", struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0))
            body = chunk(b"IDAT", zlib.compress(raw))
            return b"\x89PNG\r\n\x1a\n" + header + body + chunk(b"IEND", b"")

        marker_path = self.state / "marker.png"
        marker_path.write_bytes(png(marker_image()))
        self.assertTrue(fc.has_headless_marker(marker_path))
        plain = self.state / "plain.png"
        plain.write_bytes(png(Image.new("RGB", (32, 32), (0, 0, 0))))
        self.assertFalse(fc.has_headless_marker(plain))
        image = Image.new("RGB", (64, 64), (0, 0, 0))
        marker = marker_image()
        image.paste(marker, (16, 16))
        for quality in (10, 50, 95):
            for subsampling in (0, 2):
                jpeg = self.state / f"marker-{quality}-{subsampling}.jpg"
                image.save(jpeg, format="JPEG", quality=quality, subsampling=subsampling)
                self.assertTrue(fc.has_headless_marker(jpeg), f"quality={quality}, subsampling={subsampling}")
        near = self.state / "near.jpg"
        for x in range(16, 20):
            for y in range(16, 20):
                image.putpixel((x, y), (0, 0, 0))
        image.save(near, format="JPEG", quality=95)
        self.assertFalse(fc.has_headless_marker(near))
        jpeg_plain = self.state / "plain.jpg"
        Image.new("RGB", (64, 64), (0, 0, 0)).save(jpeg_plain, format="JPEG", quality=95)
        self.assertFalse(fc.has_headless_marker(jpeg_plain))
        truncated = self.state / "truncated.jpg"
        truncated.write_bytes((self.state / "marker-95-2.jpg").read_bytes()[:-32])
        with self.assertRaises(fc.ClientError):
            fc.has_headless_marker(truncated)
        partial = self.state / "partial.png"
        partial.write_bytes(marker_path.read_bytes()[:-4])
        with self.assertRaises(fc.ClientError):
            fc.has_headless_marker(partial)

    def test_readiness_marker_protocol_matches_lua_producer(self):
        source = Path(__file__).parent / "headless/!!ForeverHeadless/ForeverHeadless.lua"
        lua = source.read_text()
        match = re.search(r"local MARKER = \{(?P<table>.*?)\n\}", lua, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertEqual(tuple(re.findall(r'"([01]{8})"', match.group("table"))), fc.HEADLESS_MARKER)
        size = len(fc.HEADLESS_MARKER) * fc.MARKER_CELL
        self.assertIn(f"marker:SetSize({size}, {size})", lua)
        self.assertIn(f"texture:SetSize({fc.MARKER_CELL}, {fc.MARKER_CELL})", lua)

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
            fc.runtime_dir({"XDG_RUNTIME_DIR": str(self.runtime), "FOREVER_CLIENT_CALLER": "in-game"}, os.getuid() + 1)
        self.runtime.chmod(0o755)
        with self.assertRaises(fc.ClientError):
            fc.runtime_dir({"XDG_RUNTIME_DIR": str(self.runtime), "FOREVER_CLIENT_CALLER": "in-game"}, os.getuid())
        self.assertEqual(self.runtime.stat().st_mode & 0o777, 0o755)

    def test_nvidia_mismatch_names_the_loaded_module_and_the_userspace(self):
        module = self.state / "nvidia-version"
        module.write_text("615.78.08\n")
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout="620.70.06\n", stderr=""))
        self.assertEqual(
            self.real_nvidia_mismatch(module_path=module, run=run),
            "the NVIDIA kernel module (615.78.08) does not match its userspace (620.70.06): reboot first",
        )
        run.return_value = mock.Mock(returncode=0, stdout="615.78.08\n", stderr="")
        self.assertIsNone(self.real_nvidia_mismatch(module_path=module, run=run), "matching versions are not a failure")

    def test_nvidia_mismatch_reads_nvidias_own_mismatch_line(self):
        module = self.state / "nvidia-version"
        module.write_text("615.78.08\n")
        failed = mock.Mock(returncode=9, stdout="", stderr="Failed to initialize NVML: Driver/library version mismatch")
        run = mock.Mock(return_value=failed)
        with mock.patch.object(fc, "nvidia_userspace_version", return_value="620.70.06"):
            self.assertEqual(
                self.real_nvidia_mismatch(module_path=module, run=run),
                "the NVIDIA kernel module (615.78.08) does not match its userspace (620.70.06): reboot first",
            )

    def test_a_gamescope_vulkan_failure_carries_the_driver_mismatch(self):
        (self.state / "session.log").write_text("[gamescope] [Error] vulkan: vkCreateInstance failed (VkResult: -9)\n")
        with mock.patch.object(
            fc,
            "nvidia_mismatch",
            return_value="the NVIDIA kernel module (615.78.08) does not match its userspace (620.70.06): reboot first",
        ):
            hint = fc.gamescope_failure_hint()
        self.assertIn("615.78.08", hint)
        self.assertIn("620.70.06", hint)
        self.assertIn("reboot first", hint)

    def test_up_refuses_a_mismatched_nvidia_driver_before_starting_anything(self):
        message = "the NVIDIA kernel module (615.78.08) does not match its userspace (620.70.06): reboot first"
        with (
            mock.patch.object(fc, "nvidia_mismatch", return_value=message),
            mock.patch.object(fc.subprocess, "Popen") as spawn,
            self.assertRaisesRegex(fc.ClientError, "reboot first"),
        ):
            fc.up(args())
        spawn.assert_not_called()

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

    def test_up_releases_its_lock_before_reporting_a_startup_failure(self):
        config = self.state / "env.json"
        config.write_text(
            '{"umu_run":"/faugus/umu-run","env":{"PROTONPATH":"/runner"},"character":{"name":"Tester","guid":"Player-1","require_resting":true}}'
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
            mock.patch.object(fc, "wait_for_world", side_effect=fc.ClientError("startup timed out")),
            mock.patch.object(fc, "shot", return_value=Path("failed.png")),
            mock.patch.object(fc, "teardown"),
            mock.patch.object(fc.subprocess, "Popen") as spawn,
        ):
            spawn.return_value.pid = 123
            with self.assertRaisesRegex(fc.ClientError, "startup timed out"):
                fc.up(args())
        with mock.patch.object(fc, "prefix_users", return_value=[]):
            self.assertIsNone(fc.client_in_use())

    def test_up_records_runtime_and_keeps_gamescope_off_host_display(self):
        config = self.state / "env.json"
        config.write_text(
            '{"umu_run":"/faugus/umu-run","env":{"PROTONPATH":"/runner","GAMEID":"umu-x","DISPLAY":":host",'
            '"WAYLAND_DISPLAY":"host","XDG_RUNTIME_DIR":"/stale/runtime"},"character":{"name":"Tester","guid":"Player-1","require_resting":true}}'
        )
        client = self.state / "client"
        (client / "Interface/AddOns").mkdir(parents=True)
        with (
            mock.patch.object(fc, "CONFIG", config),
            mock.patch.object(fc, "CLIENT", client),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection"),
            mock.patch.object(fc.signal, "signal") as install,
            mock.patch.object(fc.signal, "alarm") as alarm,
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "child_env", return_value={"DISPLAY": ":3", "GAMESCOPE_WAYLAND_DISPLAY": "private"}),
            mock.patch.object(fc, "wait_for_world") as wait,
            mock.patch.object(fc, "client_pid", return_value=None) as client_pid,
            mock.patch.object(fc, "game_focused", return_value=True),
            mock.patch.object(fc, "enter_world") as enter_world,
            mock.patch.object(fc, "press_play") as press_play,
            mock.patch.object(fc, "x") as x,
            mock.patch.object(fc, "teardown"),
            mock.patch.object(fc.subprocess, "Popen") as spawn,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            spawn.return_value.pid = 123

            def waiting(*unused, nudge, require_marker):
                self.assertTrue(require_marker)
                nudge()
                press_play.assert_not_called()
                client_pid.return_value = 456
                nudge()
                enter_world.assert_called_once()
                return Path("ready.png")

            wait.side_effect = waiting
            options = args()
            options.manual_launcher = True
            self.assertEqual(fc.up(options, after_ready=lambda state: state["runtime_dir"]), str(self.runtime))
            x.assert_not_called()
        handled = {call.args[0] for call in install.call_args_list}
        self.assertEqual(handled, {fc.signal.SIGTERM, fc.signal.SIGHUP, fc.signal.SIGINT})
        alarm.assert_not_called()
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
        self.assertIn('"start_ticks"', (self.state / "session.json").read_text())

    def test_an_interrupt_right_after_spawn_still_gives_teardown_the_session_token(self):
        config = self.state / "env.json"
        config.write_text(
            '{"umu_run":"/faugus/umu-run","env":{"PROTONPATH":"/runner"},"character":{"name":"Tester","guid":"Player-1","require_resting":true}}'
        )
        client = self.state / "client"
        (client / "Interface/AddOns").mkdir(parents=True)

        class InterruptedGamescope:
            @property
            def pid(self):
                raise KeyboardInterrupt

        def spawn(*_args, **kwargs):
            recorded = json.loads(fc.state_file().read_text())
            self.assertEqual(recorded["token"], kwargs["env"]["FOREVER_CLIENT_SESSION"])
            return InterruptedGamescope()

        with (
            mock.patch.object(fc, "CONFIG", config),
            mock.patch.object(fc, "CLIENT", client),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection"),
            mock.patch.object(fc.signal, "signal"),
            mock.patch.object(fc.signal, "alarm"),
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc.subprocess, "Popen", side_effect=spawn),
            mock.patch.object(fc, "teardown") as teardown,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.up(args()), 0)
        state = teardown.call_args.args[3]
        self.assertIsInstance(state, dict, "the session owns its token before its first child exists")
        self.assertTrue(state.get("token"))
        self.assertEqual(state.get("wine"), {"PROTONPATH": "/runner"})

    def test_silenced_disables_wine_audio_and_keeps_existing_overrides(self):
        self.assertEqual(
            fc.silenced({"WINEDLLOVERRIDES": "d3d12=n", "WINE": "/w"}),
            {"WINEDLLOVERRIDES": "d3d12=n;winepulse.drv=d;winealsa.drv=d", "WINE": "/w"},
        )
        self.assertEqual(fc.silenced({})["WINEDLLOVERRIDES"], "winepulse.drv=d;winealsa.drv=d")

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
            mock.patch.object(fc, "read_environ", return_value={"WINEPREFIX": str(fc.PREFIX)}),
            self.assertRaisesRegex(fc.ClientError, r"player's client is running .*pid 43"),
        ):
            fc.up(args())

    def test_up_refuses_while_a_headless_session_holds_the_client(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[43]),
            mock.patch.object(fc, "client_pid", return_value=43),
            mock.patch.object(fc, "read_environ", return_value={"FOREVER_CLIENT_SESSION": "another-session"}),
            self.assertRaisesRegex(fc.ClientError, r"a headless session holds the client \(Wow.exe, pid 43\)"),
        ):
            fc.up(args())

    def test_wait_names_a_headless_session_that_keeps_the_prefix_in_use(self):
        clock = FakeClock()
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            mock.patch.object(fc, "prefix_users", return_value=[43]),
            mock.patch.object(fc, "client_pid", return_value=43),
            mock.patch.object(fc, "read_environ", return_value={"FOREVER_CLIENT_SESSION": "another-session"}),
            self.assertRaisesRegex(fc.ClientError, r"a headless session holds the client \(Wow.exe, pid 43\)"),
        ):
            fc.up(argparse.Namespace(wait=True, timeout=5))

    def test_up_puts_back_a_record_a_stopped_session_left_before_it_checks_the_client(self):
        addons = self.state / "AddOns"
        addons.mkdir()
        slot = addons / "LegacyForever"
        slot.symlink_to(self.state / "build")
        fc.link_record_path().write_text(
            json.dumps({"owner": {"pid": dead_pid(), "started": 1}, "links": [{"slot": str(slot), "was": None}]})
        )
        with (
            mock.patch.object(fc, "prefix_users", return_value=[42]),
            mock.patch.object(fc, "client_pid", return_value=None),
            contextlib.redirect_stdout(io.StringIO()),
        ):
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
            mock.patch.object(fc.fcntl, "flock", side_effect=[None, BlockingIOError(), None]),
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

    def test_a_job_that_waits_out_its_timeout_exits_non_zero(self):
        holder = open(self.state / "job.lock", "w")
        self.addCleanup(holder.close)
        fcntl.flock(holder, fcntl.LOCK_EX)
        fc.write_job_record(
            {
                "pid": os.getpid(),
                "start_ticks": fc.process_start(os.getpid()),
                "token": "held",
                "label": "smoke legacy-forever",
                "started": time.time(),
            }
        )
        clock = FakeClock()
        err = io.StringIO()
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            mock.patch.object(fc.subprocess, "run") as ran,
            contextlib.redirect_stderr(err),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = fc.main(["job", "--timeout", "5", "--", "true"])
        self.assertEqual(code, 2)
        ran.assert_not_called()
        self.assertIn("after waiting 5 s", err.getvalue())
        self.assertIn("smoke legacy-forever", err.getvalue())

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

    def test_live_protocol_decodes_exact_bits_without_authorizing_a_click(self):
        row = bytearray(52 * 3)
        for index, bit in enumerate([0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 0, 0]):
            row[(index * 4 + 2) * 3 : (index * 4 + 2) * 3 + 3] = bytes([bit * 255]) * 3
        with (
            mock.patch.object(fc, "shot", return_value=Path("frame.png")) as shot,
            mock.patch.object(fc, "png_pixels", return_value=(52, 4, 3, [bytes(row)] * 4)),
        ):
            self.assertEqual(
                fc.client_ui({}),
                {"world": True, "menu": True, "chat": False, "safety": True, "dead": False, "combat": False},
            )
        self.assertFalse(shot.call_args.kwargs["mark_read"])

    def test_failed_live_captures_report_no_ui(self):
        failures = [subprocess.CalledProcessError(1, "gamescopectl"), fc.ClientError("capture failed")]
        for error in failures:
            with self.subTest(error=error), mock.patch.object(fc, "shot", side_effect=error):
                self.assertEqual(
                    fc.client_ui({}),
                    {"world": False, "menu": False, "chat": False, "safety": False, "dead": True, "combat": True},
                )
        image = self.state / "truncated.png"
        image.write_bytes(fc.PNG_SIGNATURE + b"broken")
        with mock.patch.object(fc, "shot", return_value=image):
            self.assertEqual(
                fc.client_ui({}),
                {"world": False, "menu": False, "chat": False, "safety": False, "dead": True, "combat": True},
            )

    def test_a_live_capture_is_removed_once_decoded(self):
        def capture(_state, path, mark_read=True):
            path.write_bytes(b"frame")
            return path

        for pixels in ({"return_value": (52, 4, 3, [bytes(52 * 3)] * 4)}, {"side_effect": OSError("unreadable")}):
            with (
                self.subTest(pixels=pixels),
                mock.patch.object(fc, "STATE_DIR", self.state),
                mock.patch.object(fc, "shot", side_effect=capture),
                mock.patch.object(fc, "png_pixels", **pixels),
            ):
                fc.client_ui({})
                self.assertEqual(list(self.state.glob("client-state-*.png")), [])

    def test_unreleased_changelog_is_one_bullet_list(self):
        changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text()
        unreleased = changelog.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0].strip()
        self.assertNotIn("\n\n- ", unreleased)
        self.assertNotRegex(unreleased, "[\u2013\u2014]")

    def test_resident_world_check_waits_for_interval_and_job_release_without_changing_ready(self):
        state = {"ready": 1}
        with (
            mock.patch.object(fc.time, "monotonic", return_value=100),
            mock.patch.object(fc, "job_holder", return_value={"pid": 42}) as holder,
            mock.patch.object(fc, "client_ui", return_value={"world": False}) as ui,
        ):
            self.assertEqual(fc.resident_world_check(state, 0), (0, None))
            holder.return_value = None
            self.assertEqual(fc.resident_world_check(state, 100 - fc.WORLD_CHECK + 1), (100 - fc.WORLD_CHECK + 1, None))
            ui.assert_not_called()
            self.assertEqual(fc.resident_world_check(state, 100 - fc.WORLD_CHECK), (100, "the client left the world"))
            self.assertEqual(state, {"ready": 1})

    def test_game_menu_click_is_refused_before_any_mouse_input(self):
        with (
            mock.patch.object(fc, "mark", side_effect=lambda name: 2 if name == "last-shot" else 0),
            mock.patch.object(fc, "client_ui", return_value={"world": True, "menu": True}),
            mock.patch.object(fc, "x") as x,
        ):
            with self.assertRaisesRegex(fc.ClientError, "Game Menu"):
                fc.click({"ready": True}, 960, 540, "1")
        x.assert_not_called()

    def test_logout_never_types_into_a_login_screen(self):
        with (
            mock.patch.object(fc, "client_ui", return_value={"world": False, "menu": False, "chat": False}),
            mock.patch.object(fc, "send") as send,
            mock.patch.object(fc, "client_pid", return_value=None),
        ):
            fc.log_out({})
        send.assert_not_called()

    def test_slash_requires_confirmed_chat_focus(self):
        with (
            mock.patch.object(fc, "send") as send,
            mock.patch.object(fc, "allowed_command"),
            mock.patch.object(fc.time, "sleep"),
            mock.patch.object(
                fc,
                "client_ui",
                side_effect=[
                    {"world": True, "menu": False, "chat": False},
                    {"world": True, "menu": False, "chat": False},
                    {"world": True, "menu": False, "chat": True},
                ],
            ),
        ):
            fc.slash({}, "/reload")
        self.assertEqual(
            send.call_args_list,
            [
                mock.call({}, "key", "Return"),
                mock.call({}, "type", "--delay", fc.TYPE_DELAY_MS, "/reload"),
                mock.call({}, "key", "Return"),
            ],
        )

    def test_slash_refuses_a_menu_that_will_not_close_without_typing(self):
        with (
            mock.patch.object(fc, "send") as send,
            mock.patch.object(fc, "allowed_command"),
            mock.patch.object(fc.time, "sleep"),
            mock.patch.object(fc, "client_ui", return_value={"world": True, "menu": True, "chat": False}),
        ):
            with self.assertRaisesRegex(fc.ClientError, "Game Menu"):
                fc.slash({}, "/reload")
        self.assertEqual(send.call_args_list, [mock.call({}, "key", "Escape")] * fc.MENU_CLOSE_TRIES)

    def test_slash_closes_a_game_menu_an_earlier_job_left_open(self):
        # #727: a job that ended at the Game Menu must not make the next job's slash refuse.
        with (
            mock.patch.object(fc, "send") as send,
            mock.patch.object(fc, "allowed_command"),
            mock.patch.object(fc.time, "sleep"),
            mock.patch.object(
                fc,
                "client_ui",
                side_effect=[
                    {"world": True, "menu": True, "chat": False},
                    {"world": True, "menu": False, "chat": False},
                    {"world": True, "menu": False, "chat": False},
                    {"world": True, "menu": False, "chat": True},
                ],
            ),
        ):
            fc.slash({}, "/forever selftest")
        self.assertEqual(
            send.call_args_list,
            [
                mock.call({}, "key", "Escape"),
                mock.call({}, "key", "Return"),
                mock.call({}, "type", "--delay", fc.TYPE_DELAY_MS, "/forever selftest"),
                mock.call({}, "key", "Return"),
            ],
        )

    def test_closing_the_menu_sends_nothing_outside_the_world(self):
        with (
            mock.patch.object(fc, "send") as send,
            mock.patch.object(fc, "client_ui", return_value={"world": False, "menu": True, "chat": False}),
        ):
            fc.close_game_menu({})
        send.assert_not_called()

    def test_reload_waits_only_for_a_screenshot_taken_after_the_command_was_sent(self):
        earlier = self.state / "earlier.jpg"
        present = set()

        def typed(_state, _command):
            present.add(earlier)  # a screenshot an earlier flow left lands while the command is typed

        with (
            mock.patch.object(fc, "screenshots", side_effect=lambda: set(present)),
            mock.patch.object(fc, "slash", side_effect=typed),
            mock.patch.object(fc, "wait_for_world", return_value=earlier) as wait,
        ):
            fc.reload({})
        self.assertIn(earlier, wait.call_args.args[0], "it cannot pass as this reload's world load")

    def test_key_sends_only_ui_keys(self):
        with mock.patch.object(fc, "x") as x, self.assertRaisesRegex(fc.ClientError, "refused w"):
            fc.press({}, ["Escape", "w"])
        x.assert_not_called()

    def test_press_play_clicks_the_screenshot_bound_play_label(self):
        state = {"display": ":1"}
        found = mock.Mock(stdout="12345\n")
        with (
            mock.patch.object(fc.subprocess, "run", side_effect=[found]),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "ocr_words", return_value=[]),
            mock.patch.object(fc, "play_targets", return_value=[(1390, 580, 72, 24, 96.5)]) as targets,
            mock.patch.object(fc, "x") as x,
            mock.patch.object(fc.time, "sleep"),
        ):
            fc.press_play(state)
        targets.assert_called_once_with(self.state / "launcher.png")
        self.assertEqual(
            x.call_args_list,
            [
                mock.call(state, "mousemove", "1426", "592"),
                mock.call(state, "click", "1"),
            ],
        )
        self.assertNotIn("--window", x.call_args_list[0].args)
        self.assertTrue((self.state / "last-input").exists())

    def test_press_play_stops_on_exact_update_labels_before_sending_input(self):
        for label in ("Installation Required",):
            with (
                self.subTest(label=label),
                mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(stdout="12345")),
                mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
                mock.patch.object(fc, "client_pid", return_value=None),
                mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
                mock.patch.object(fc, "ocr_words", return_value=[(word, 95.0, 0, 0, 20, 20) for word in label.split()]),
                mock.patch.object(fc, "play_targets") as targets,
                mock.patch.object(fc, "x") as x,
                self.assertRaisesRegex(fc.ClientError, "needs an update in Battle.net.*launcher.png"),
            ):
                fc.press_play({"display": ":1"})
            x.assert_not_called()
            targets.assert_not_called()

    def test_press_play_ignores_the_upgrade_available_banner(self):
        # The banner advertises an account upgrade beside a working Play button, so it must not stop startup.
        with (
            mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(stdout="12345")),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(
                fc, "ocr_words", return_value=[(w, 95.0, 0, 0, 20, 20) for w in ("Upgrade", "Available")]
            ),
            mock.patch.object(fc, "play_targets", return_value=[]) as targets,
            mock.patch.object(fc, "x"),
        ):
            try:
                fc.press_play({"display": ":1"})
            except fc.ClientError as error:
                self.assertNotIn("needs an update", str(error))
            targets.assert_called()

    def test_press_play_caps_attempts_without_a_game_process(self):
        state = {"display": ":1"}
        with (
            mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(stdout="12345")),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(fc, "ocr_words", return_value=[]),
            mock.patch.object(fc, "play_targets", return_value=[(100, 100, 40, 20, 95.0)]),
            mock.patch.object(fc, "x") as x,
            mock.patch.object(fc.time, "sleep"),
            mock.patch.object(fc.time, "monotonic") as now,
        ):
            for attempt in range(fc.MAX_PLAY_CLICKS):
                now.return_value = attempt * fc.PLAY_RETRY_WAIT
                fc.press_play(state)
                fc.press_play(state)  # The same frame time cannot trigger another attempt.
            now.return_value = fc.MAX_PLAY_CLICKS * fc.PLAY_RETRY_WAIT
            with self.assertRaisesRegex(fc.ClientError, "no game process.*launcher.png"):
                fc.press_play(state)
        self.assertEqual(x.call_args_list.count(mock.call(state, "click", "1")), fc.MAX_PLAY_CLICKS)

    def test_press_play_dismisses_a_launcher_dialog_before_retrying(self):
        state = {"display": ":1"}
        found = mock.Mock(stdout="12345\n")
        with (
            mock.patch.object(fc.subprocess, "run", side_effect=[found, found]),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "ocr_words", return_value=[]),
            mock.patch.object(fc, "play_targets", return_value=[]),
            mock.patch.object(fc, "x") as x,
            contextlib.redirect_stderr(io.StringIO()) as warning,
        ):
            fc.press_play(state)
            fc.press_play(state)
        self.assertEqual(
            x.call_args_list,
            [mock.call(state, "key", "--window", "12345", "Escape")] * 2,
        )
        self.assertEqual(warning.getvalue().count("no visible Play label"), 1)
        self.assertIn(str(self.state / "launcher.png"), warning.getvalue())
        self.assertIn("--manual-launcher", warning.getvalue())

    def test_manual_launcher_cli_only_allows_shot_and_left_click_before_ready(self):
        state = live_state(manual_launcher=True)
        with (
            mock.patch.object(fc, "load_state", return_value=state),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "own")),
            mock.patch.object(fc, "release_job"),
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

    def test_launcher_verbs_skip_the_job_lock_a_starting_manual_session_holds(self):
        # `job`, `lease`, `smoke` and `proof` hold the job lock while `ensure_session` waits for READY, and the agent
        # that clicks Play is what lets them get there: its own shot and left click must not queue behind them (#646).
        holder = open(self.state / "job.lock", "w")
        self.addCleanup(holder.close)
        fcntl.flock(holder, fcntl.LOCK_EX)
        state = live_state(manual_launcher=True)
        err = io.StringIO()
        with (
            mock.patch.object(fc, "load_state", return_value=state),
            mock.patch.object(fc, "shot", return_value=self.state / "frame.png") as shot,
            mock.patch.object(fc, "click") as click,
            mock.patch.object(fc, "press") as press,
            mock.patch.object(fc, "slash") as slash,
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(err),
        ):
            # The held lock is never waited for: a zero-second timeout still takes the launcher verbs.
            self.assertEqual(fc.main(["shot", "--timeout", "0"]), 0)
            self.assertEqual(fc.main(["click", "100", "200", "--timeout", "0"]), 0)
            shot.assert_called_once()
            click.assert_called_once_with(state, 100, 200, "1")
            # Every other verb refuses before READY, as it did, and says why rather than naming the lock.
            fcntl.flock(holder, fcntl.LOCK_UN)
            for command in (["key", "Return"], ["slash", "/fgf"], ["click", "100", "200", "--button", "3"]):
                self.assertEqual(fc.main(command), 2)
            self.assertIn("not in the world yet", err.getvalue())
            press.assert_not_called()
            slash.assert_not_called()
            self.assertEqual(click.call_args_list, [mock.call(state, 100, 200, "1")])

    def test_default_launcher_still_blocks_actions_before_ready(self):
        with (
            mock.patch.object(fc, "load_state", return_value=live_state()),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "own")),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "shot") as shot,
            mock.patch.object(fc, "click") as click,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(fc.main(["shot"]), 2)
            self.assertEqual(fc.main(["click", "100", "200"]), 2)
            shot.assert_not_called()
            click.assert_not_called()

    def test_manual_launcher_flag_reaches_up_and_job(self):
        with mock.patch.object(fc, "up", return_value=0) as up:
            self.assertEqual(fc.main(["up", "--manual-launcher"]), 0)
            self.assertTrue(up.call_args.args[0].manual_launcher)
        with mock.patch.object(fc, "job", return_value=0) as job:
            self.assertEqual(fc.main(["run", "--manual-launcher", "--", "true"]), 0)
            self.assertTrue(job.call_args.args[0].manual_launcher)
            self.assertEqual(job.call_args.args[0].command, ["--", "true"])
            self.assertEqual(fc.main(["job", "--label", "probe", "--", "true"]), 0)
            self.assertEqual(job.call_args.args[0].label, "probe")

    def test_press_play_refuses_ambiguous_ocr_targets(self):
        state = {"display": ":1"}
        found = mock.Mock(stdout="12345\n")
        targets = [(100, 100, 40, 20, 90.0), (300, 300, 40, 20, 90.0)]
        with (
            mock.patch.object(fc.subprocess, "run", side_effect=[found]),
            mock.patch.object(fc.shutil, "which", return_value="/usr/bin/tesseract"),
            mock.patch.object(fc, "shot", return_value=self.state / "launcher.png"),
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "ocr_words", return_value=[]),
            mock.patch.object(fc, "play_targets", return_value=targets),
            mock.patch.object(fc, "x") as x,
            self.assertRaisesRegex(fc.ClientError, "expected one visible Play target"),
        ):
            fc.press_play(state)
        x.assert_not_called()

    def test_the_saved_launcher_frame_draws_the_play_button_as_its_own_region(self):
        fixture = Path(__file__).parent / "headless/launcher-play.png"
        width, height, channels, rows = fc.png_pixels(fixture)
        self.assertEqual((width, height, channels), (380, 190, 3), "the saved frame is the cropped launcher page")
        regions = fc.fill_regions(width, height, channels, rows)
        self.assertEqual(
            regions[0][1:],
            (71, 100, 232, 56),
            "the largest fill the launcher draws is the Play button, not the gear drawn beside it",
        )
        self.assertGreaterEqual(regions[1][1], 71 + 232, "the gear is the next region, to the right of Play")

    def test_play_targets_requires_exactly_one_play_word_in_the_region(self):
        fixture = Path(__file__).parent / "headless/launcher-play.png"
        play = ("Play", 96.0, 10, 10, 40, 20)
        now = ("Now", 95.0, 55, 10, 35, 20)
        for words, expected in (([play, now], []), ([play, play], []), ([play], [(81, 110, 40, 20, 96.0)])):
            with (
                self.subTest(words=words),
                mock.patch.object(fc, "fill_regions", return_value=[(12992, 71, 100, 232, 56)]),
                mock.patch.object(fc, "ocr_words", return_value=words),
            ):
                self.assertEqual(fc.play_targets(fixture), expected)

    @unittest.skipUnless(shutil.which("tesseract"), "needs tesseract to read the saved launcher frame")
    def test_the_play_label_is_read_inside_the_button_the_launcher_draws(self):
        fixture = Path(__file__).parent / "headless/launcher-play.png"
        targets = fc.play_targets(fixture)
        self.assertEqual(len(targets), 1, "the saved frame holds one Play button")
        left, top, width, height, confidence = targets[0]
        self.assertGreaterEqual(confidence, 0)
        self.assertTrue(71 <= left and left + width <= 71 + 232, f"the label {left}..{left + width} is in the button")
        self.assertTrue(100 <= top and top + height <= 100 + 56, f"the label {top}..{top + height} is in the button")

    @unittest.skipUnless(shutil.which("tesseract"), "needs tesseract to read the saved launcher frame")
    def test_press_play_accepts_the_saved_launcher_frame_without_an_update(self):
        fixture = Path(__file__).parent / "headless/launcher-play.png"
        words = fc.ocr_words(fixture)
        state = {"display": ":1"}
        with (
            mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(stdout="12345")),
            mock.patch.object(fc, "client_pid", return_value=None),
            mock.patch.object(fc, "shot", return_value=fixture),
            mock.patch.object(fc, "ocr_words", return_value=words),
            mock.patch.object(fc, "play_targets", return_value=[(81, 110, 40, 20, 96.0)]),
            mock.patch.object(fc, "x") as x,
            mock.patch.object(fc.time, "sleep"),
        ):
            fc.press_play(state)
        x.assert_any_call(state, "click", "1")

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
            mock.patch.object(fc, "enter_world") as enter_world,
            mock.patch.object(fc, "x") as x,
        ):
            fc.at_character_select(state, False)
        enter_world.assert_called_once_with(state)
        x.assert_not_called()

    def test_character_select_nudge_does_not_send_return_on_login_frame(self):
        state = {"display": ":1"}
        with (
            mock.patch.object(fc, "client_pid", return_value=456),
            mock.patch.object(fc, "game_focused", return_value=True),
            mock.patch.object(fc, "shot"),
            mock.patch.object(fc, "enter_world_targets", return_value=[]),
            mock.patch.object(fc, "x") as x,
        ):
            fc.enter_world(state)
        x.assert_not_called()

    def test_enter_world_targets_requires_adjacent_enter_and_world_words(self):
        with (
            mock.patch.object(fc, "png_pixels", return_value=(1, 1, 1, [b"\x00"])),
            mock.patch.object(fc, "ocr_words_with_lines", return_value=[("EnterWorld", 51.4, 896, 716, 127, 30, 1001)]),
        ):
            self.assertEqual(fc.enter_world_targets(Path("frame.png")), [(896, 716, 127, 30, 51.4)])

    def test_enter_world_targets_fails_closed_on_ambiguous_exact_labels(self):
        with (
            mock.patch.object(fc, "png_pixels", return_value=(1, 1, 1, [b"\x00"])),
            mock.patch.object(
                fc,
                "ocr_words_with_lines",
                return_value=[
                    ("EnterWorld", 51.4, 896, 716, 127, 30, 1001),
                    ("EnterWorld", 51.4, 896, 600, 127, 30, 1002),
                ],
            ),
        ):
            self.assertEqual(len(fc.enter_world_targets(Path("frame.png"))), 2)

    def test_enter_world_targets_fails_closed_on_exact_and_split_labels(self):
        with (
            mock.patch.object(fc, "png_pixels", return_value=(1, 1, 1, [b"\x00"])),
            mock.patch.object(
                fc,
                "ocr_words_with_lines",
                return_value=[
                    ("EnterWorld", 51.4, 896, 716, 127, 30, (1, 1, 1)),
                    ("Enter", 51.4, 896, 600, 55, 30, (2, 1, 1)),
                    ("World", 51.4, 960, 600, 60, 30, (2, 1, 1)),
                ],
            ),
        ):
            self.assertEqual(len(fc.enter_world_targets(Path("frame.png"))), 2)

    def test_ocr_line_identity_preserves_all_tsv_components(self):
        tsv = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
1\t1\t1\t1\t1\t1\t10\t20\t30\t40\t95\tEnter
1\t1\t1\t1\t101\t1\t10\t20\t30\t40\t95\tWorld
"""
        with mock.patch.object(fc.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=tsv, stderr="")):
            words = fc.ocr_words_with_lines(Path("frame.png"), psm=6)
        self.assertEqual(words[0][-1], (1, 1, 1))
        self.assertEqual(words[1][-1], (1, 1, 101))

    def test_enter_world_targets_ignores_login_labels(self):
        with (
            mock.patch.object(fc, "png_pixels", return_value=(1, 1, 4, [b"\0\0\0\0"])),
            mock.patch.object(
                fc,
                "ocr_words_with_lines",
                return_value=[
                    ("Email", 96.0, 700, 400, 120, 24, 1001),
                    ("Password", 96.0, 700, 450, 150, 24, 1002),
                ],
            ),
        ):
            self.assertEqual(fc.enter_world_targets(Path("login.png")), [])

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

    def test_scroll_turns_the_wheel_at_a_freshly_seen_point(self):
        with (
            mock.patch.object(
                fc, "mark", side_effect=lambda name: fc.time.time() + (0.1 if name == "last-shot" else 0)
            ),
            mock.patch.object(fc, "send") as send,
        ):
            fc.scroll({}, 960, 540, 3)
            fc.scroll({}, 960, 540, -2)
        self.assertEqual(
            send.call_args_list,
            [
                mock.call({}, "mousemove", "960", "540", "click", "--repeat", "3", "--delay", fc.WHEEL_DELAY_MS, "4"),
                mock.call({}, "mousemove", "960", "540", "click", "--repeat", "2", "--delay", fc.WHEEL_DELAY_MS, "5"),
            ],
        )

    def test_scroll_needs_a_shot_and_a_non_zero_point(self):
        with (
            mock.patch.object(fc, "mark", return_value=0),
            mock.patch.object(fc, "send") as send,
            self.assertRaisesRegex(fc.ClientError, "take a `shot`"),
        ):
            fc.scroll({}, 960, 540, 1)
        (self.state / "last-shot").touch()
        (self.state / "last-input").touch()
        with (
            mock.patch.object(fc, "mark", side_effect=lambda name: 2 if name == "last-shot" else 1),
            mock.patch.object(fc, "send") as send,
            self.assertRaisesRegex(fc.ClientError, "non-zero"),
        ):
            fc.scroll({}, 960, 540, 0)
        with (
            mock.patch.object(fc, "mark", side_effect=lambda name: 2 if name == "last-shot" else 1),
            mock.patch.object(fc, "send") as send,
            self.assertRaisesRegex(fc.ClientError, "outside"),
        ):
            fc.scroll({}, 2000, 540, 1)
        send.assert_not_called()

    def test_scroll_cli_reaches_the_wheel_verb(self):
        state = live_state(ready=1.0)
        with (
            mock.patch.object(fc, "load_state", return_value=state),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "own")),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "scroll") as scroll,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.main(["scroll", "960", "540", "-4"]), 0)
        scroll.assert_called_once_with(state, 960, 540, -4)

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

    def test_a_dead_owners_gamescope_is_stopped_by_its_recorded_pid(self):
        with (
            mock.patch.object(fc, "gamescope_running", side_effect=[True, False]),
            mock.patch.object(fc, "signal_pid", return_value=True) as signal_pid,
            mock.patch.object(fc, "wait_for_pid", return_value=True) as wait,
        ):
            fc.stop_gamescope(1234, {"gamescope_start": 99})
        signal_pid.assert_called_once_with(1234, 99, fc.signal.SIGTERM)
        wait.assert_called_once_with(1234, 99, 20)

    def test_down_tears_down_what_a_dead_owner_left_behind(self):
        dead = dead_pid()
        link = self.state / "!!ForeverHeadless"
        link.symlink_to(self.state / "build")
        state = {
            "pid": dead,
            "owner_start": 1,
            "gamescope": 4321,
            "gamescope_start": 7,
            "token": "owned",
            "wine": {"PROTONPATH": "/runner"},
            "link": str(link),
        }
        fc.state_file().write_text(json.dumps(state))
        with (
            mock.patch.object(fc, "recover_links") as recover,
            mock.patch.object(fc, "teardown") as teardown,
        ):
            self.assertEqual(fc.down(), 0)
        recover.assert_called_once_with()
        teardown.assert_called_once_with(4321, {"PROTONPATH": "/runner"}, link, state)

    def test_down_never_signals_a_reused_owner_pid(self):
        # The state file records the owner's start time, so a pid now owned by another process is already gone.
        state = {"pid": os.getpid(), "owner_start": -1, "token": "owned", "gamescope": None}
        fc.state_file().write_text(json.dumps(state))
        with (
            mock.patch.object(fc, "recover_links"),
            mock.patch.object(fc, "teardown") as teardown,
        ):
            self.assertEqual(fc.down(), 0)
        teardown.assert_called_once()

    def test_down_pins_the_owner_identity_when_signalling(self):
        state = {"pid": 1234, "owner_start": 99, "token": "owned", "gamescope": None}
        fc.state_file().write_text(json.dumps(state))
        with (
            mock.patch.object(fc, "owner_alive", side_effect=[True, False]),
            mock.patch.object(fc, "signal_pid", return_value=False) as send_signal,
            mock.patch.object(fc.os, "kill") as kill,
            mock.patch.object(fc, "recover_links"),
            mock.patch.object(fc, "teardown"),
            mock.patch.object(fc.time, "monotonic", side_effect=[0, 999]),
        ):
            self.assertEqual(fc.down(), 0)
        send_signal.assert_called_once_with(1234, 99, fc.signal.SIGTERM)
        kill.assert_not_called()

    def test_signal_pid_refuses_missing_start_identity(self):
        with mock.patch.object(fc.os, "pidfd_open") as open_pid:
            self.assertFalse(fc.signal_pid(1234, None, fc.signal.SIGTERM))
        open_pid.assert_not_called()

    def test_down_retains_state_when_live_owner_cannot_be_signalled(self):
        state = {"pid": 1234, "owner_start": 99, "token": "owned", "gamescope": None}
        fc.state_file().write_text(json.dumps(state))
        with (
            mock.patch.object(fc, "owner_alive", return_value=True),
            mock.patch.object(fc, "signal_pid", return_value=False),
            mock.patch.object(fc, "teardown") as teardown,
            self.assertRaisesRegex(fc.ClientError, "cannot safely signal"),
        ):
            fc.down()
        teardown.assert_not_called()
        self.assertTrue(fc.state_file().exists())

    def test_down_never_cleans_a_dead_record_while_another_session_holds_lock(self):
        fc.state_file().write_text(json.dumps({"pid": dead_pid(), "token": "old"}))
        with open(self.state / "lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with (
                mock.patch.object(fc, "recover_links"),
                mock.patch.object(fc, "teardown") as teardown,
                self.assertRaisesRegex(fc.ClientError, "holds the client"),
            ):
                fc.down()
        teardown.assert_not_called()
        self.assertTrue(fc.state_file().exists())

    def test_stop_gamescope_retains_unverifiable_live_process(self):
        with (
            mock.patch.object(fc, "gamescope_running", return_value=True),
            mock.patch.object(fc, "signal_pid", return_value=False),
            self.assertRaisesRegex(fc.ClientError, "cannot safely stop gamescope"),
        ):
            fc.stop_gamescope(1234, {})

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
                    "token": "run-1",
                }
            )
        )
        tool.EvalError = error
        return tool

    def test_eval_writes_reloads_and_reports_the_saved_output(self):
        client = self.state / "client"
        with mock.patch.object(fc, "CLIENT", client):
            self.saved_smoke(
                '{\n\t["run"] = "run-1",\n\t["ran"] = 1763000000,\n\t["ok"] = true,\n'
                '\t["out"] = { "a printed line", "42" },\n}'
            )
            tool = self.eval_tool()
            state = live_state(ready=1.0)
            out = io.StringIO()
            with (
                mock.patch.object(fc, "load_state", return_value=state),
                mock.patch.object(fc, "devsmoke_eval", return_value=tool),
                mock.patch.object(fc, "reload") as reload,
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(fc.main(["eval", "probe.lua"]), 0)
        self.assertEqual(
            reload.call_args_list,
            [mock.call(state), mock.call(state)],
            "the reload that runs the snippet, then the one that saves its result to disk",
        )
        tool.write_snippet.assert_called_once_with(Path("probe.lua"), addons=client / "Interface/AddOns", capture=False)
        printed = out.getvalue()
        self.assertIn("wrote /checkout/!!DevSmokeInbox/Eval.lua from probe.lua (2 lines)", printed)
        self.assertIn("DevSmokeDB.eval: ok, ran 1763000000\na printed line\n42", printed)

    def test_eval_never_reports_an_earlier_runs_result(self):
        # The SavedVariables file holds the session before this one until the next reload, and the first reader
        # answered with it: a passing snippet was called failed, and a failing one passed (#580).
        with mock.patch.object(fc, "CLIENT", self.state / "client"):
            self.saved_smoke('{\n\t["run"] = "earlier",\n\t["ran"] = 1763000000,\n\t["ok"] = true,\n}')
            err = io.StringIO()
            with (
                mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
                mock.patch.object(fc, "devsmoke_eval", return_value=self.eval_tool()),
                mock.patch.object(fc, "reload"),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(err),
            ):
                self.assertEqual(fc.main(["eval", "probe.lua"]), 2)
        self.assertIn("holds the run 'earlier', not this snippet's 'run-1'", err.getvalue())
        self.assertNotIn("DevSmokeDB.eval: ok", err.getvalue())

    def test_eval_reports_a_failed_snippet_and_exits_one(self):
        with mock.patch.object(fc, "CLIENT", self.state / "client"):
            self.saved_smoke(
                '{\n\t["run"] = "run-1",\n\t["ran"] = 7,\n\t["ok"] = false,\n\t["out"] = { "before" },\n'
                '\t["err"] = "boom\\nstack",\n}'
            )
            out = io.StringIO()
            with (
                mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
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
            mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "reload") as reload,
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(fc.main(["eval", "probe.lua"]), 2)
        reload.assert_not_called()
        self.assertIn("probe.lua:2: 'end' expected", err.getvalue())

    def test_eval_clears_the_inbox_before_the_reload_that_saves_its_result(self):
        # The first reload runs the snippet; leaving the inbox for the second would run it again and report the second
        # run's output, and its delayed flow screenshot could be mistaken for the saving reload's world load (#588).
        with mock.patch.object(fc, "CLIENT", self.state / "client"):
            self.saved_smoke('{\n\t["run"] = "run-1",\n\t["ran"] = 7,\n\t["ok"] = true,\n\t["out"] = { "shown" },\n}')
            cleared = []
            with (
                mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
                mock.patch.object(fc, "devsmoke_eval", return_value=self.eval_tool()),
                mock.patch.object(fc, "reload", side_effect=lambda _state: cleared.append(clear.called)),
                mock.patch.object(fc, "clear_eval_inbox") as clear,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(fc.main(["eval", "probe.lua"]), 0)
        self.assertEqual(cleared, [False, True], "the inbox is gone before the saving reload")
        clear.assert_called_once_with()

    def test_eval_clears_the_inbox_even_when_its_snippet_is_refused(self):
        class Refused(Exception):
            pass

        tool = self.eval_tool(Refused)
        tool.write_snippet.side_effect = Refused("probe.lua:2: 'end' expected")
        with (
            mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "reload") as reload,
            mock.patch.object(fc, "clear_eval_inbox") as clear,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(fc.main(["eval", "probe.lua"]), 2)
        reload.assert_not_called()
        clear.assert_called_once_with(quiet=True)

    def test_eval_without_a_session_says_how_to_start_one(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(fc.main(["eval", "probe.lua"]), 2)
        self.assertIn("forever_client.py up", err.getvalue())

    def test_eval_without_saved_variables_says_so(self):
        err = io.StringIO()
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
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

    def test_saved_eval_reads_the_record_its_run_token_wrote(self):
        with mock.patch.object(fc, "CLIENT", self.state / "client"):
            self.saved_smoke('{\n\t["run"] = "run-1",\n\t["ran"] = 7,\n\t["ok"] = true,\n}')
            self.assertEqual(fc.saved_eval("run-1")["ran"], 7)

    def test_saved_eval_refuses_another_runs_record(self):
        # The file still holds the eval before this run's until a reload saves the new one (#580).
        with mock.patch.object(fc, "CLIENT", self.state / "client"):
            self.saved_smoke('{\n\t["run"] = "earlier",\n\t["ran"] = 1,\n\t["ok"] = true,\n}')
            with self.assertRaisesRegex(fc.ClientError, "holds the run 'earlier', not this snippet's 'run-1'") as error:
                fc.saved_eval("run-1")
        self.assertIn("the snippet's own result was not saved", str(error.exception))


class BuildDevTest(unittest.TestCase):
    """The dev build rebuild-dev.sh made, now one function: the commit's tree, stripped and stamped."""

    def setUp(self):
        self.enterContext(mock.patch.object(fc, "prefix_users", return_value=[]))
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
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
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))
        self.addons = self.state / "AddOns"
        self.addons.mkdir()
        self.enterContext(mock.patch.object(fc, "addons_dir", return_value=self.addons))
        self.build = self.state / "build"
        self.build.mkdir()
        self.folders = [("LegacyForever", self.build)]
        self.enterContext(mock.patch.object(fc, "prefix_users", return_value=[]))
        self.enterContext(mock.patch.object(fc, "client_in_use", return_value=None))

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
        self.assertEqual(
            record["owner"],
            {"pid": os.getpid(), "started": fc.process_start(os.getpid()), "boot_id": fc.boot_id()},
        )
        self.assertEqual(record["links"], records)

    def test_state_writes_fsync_the_file_and_state_directory(self):
        with mock.patch.object(fc.os, "fsync") as fsync:
            fc.write_job_record({"pid": os.getpid()})
        self.assertEqual(fsync.call_count, 2)
        self.assertEqual(fc.read_job_record(), {"pid": os.getpid()})

    def test_an_empty_record_recovers_store_backups_after_a_reboot(self):
        slot = self.addons / "LegacyForever"
        slot.symlink_to(self.build)
        backup = self.addons / "LegacyForever.smoke-backup"
        backup.mkdir()
        (backup / "LegacyForever.toc").write_text("store")
        fc.link_record_path().write_text("")
        with (
            mock.patch.object(fc, "addons_dir", return_value=self.addons),
            mock.patch.object(fc, "client_in_use", return_value=None),
        ):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(slot.is_symlink())
        self.assertEqual((slot / "LegacyForever.toc").read_text(), "store")

    def test_dead_smoke_recovers_during_live_resident_session_without_deleting_addon(self):
        slot = self.killed_session()
        stale = self.state / "headless-addon"
        stale.mkdir()
        fc.state_file().write_text(json.dumps({"headless_addon": str(stale)}))
        with mock.patch.object(fc, "current_session", return_value={"ready": 1}):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(slot.is_symlink())
        self.assertTrue(stale.is_dir())

    def test_headless_addon_cleanup_respects_starting_session_lock_and_prefix_users(self):
        for replay in (False, True):
            for guard in ("session_lock_held", "prefix_users"):
                with self.subTest(replay=replay, guard=guard):
                    stale = self.state / "headless-addon"
                    stale.mkdir(exist_ok=True)
                    if replay:
                        fc.link_record_path().write_text(json.dumps({"owner": None, "links": []}))
                    with (
                        mock.patch.object(fc, "current_session", return_value=None),
                        mock.patch.object(fc, "client_in_use", return_value=None),
                        mock.patch.object(fc, guard, return_value=True if guard == "session_lock_held" else [42]),
                    ):
                        fc.recover_links()
                    self.assertTrue(stale.is_dir())

    def test_torn_record_recovers_backup_regardless_of_target_but_keeps_unbacked_link(self):
        slot = self.addons / "LegacyForever"
        slot.symlink_to(self.state.parent / "arbitrary-build")
        backup = self.addons / "LegacyForever.smoke-backup"
        backup.mkdir()
        unbacked = self.addons / "UserBuild"
        unbacked.symlink_to(self.state / "test-artifacts/user")
        fc.link_record_path().write_text("{")
        with (
            mock.patch.object(fc, "addons_dir", return_value=self.addons),
            mock.patch.object(fc, "client_in_use", return_value=None),
        ):
            self.assertEqual(fc.recover_links(), 1)
        self.assertTrue(slot.is_dir())
        self.assertFalse(slot.is_symlink())
        self.assertTrue(unbacked.is_symlink())

    def test_a_stale_headless_addon_without_a_record_is_removed(self):
        stale = self.state / "headless-addon"
        stale.mkdir()
        with mock.patch.object(fc, "client_in_use", return_value=None):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(stale.exists())

    def test_a_record_from_another_boot_is_recovered_even_if_pid_is_live(self):
        slot = self.killed_session()
        record = json.loads(fc.link_record_path().read_text())
        record["owner"] = {"pid": os.getpid(), "started": fc.process_start(os.getpid()), "boot_id": "old-boot"}
        fc.link_record_path().write_text(json.dumps(record))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(slot.is_symlink())

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

    def test_an_ownerless_record_is_left_alone_while_a_job_holds_the_lock(self):
        slot = self.older_record()
        with open(fc.job_lock_path(), "a+") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            self.assertEqual(fc.recover_links(), 0)
        self.assertTrue(slot.is_symlink())
        self.assertTrue(fc.link_record_path().exists())

    def test_live_pid_without_job_lock_does_not_prevent_recovery(self):
        fc.link_build(self.folders, self.addons)
        with mock.patch.object(fc, "owner_alive", return_value=True):
            self.assertEqual(fc.recover_links(), 1)
        self.assertFalse(fc.link_record_path().exists())

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
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))

    def test_the_players_client_is_named(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[43]),
            mock.patch.object(fc, "client_pid", return_value=43),
            mock.patch.object(fc, "read_environ", return_value={"WINEPREFIX": str(fc.PREFIX)}),
        ):
            self.assertIn("player's client is running", fc.client_in_use())

    def test_a_headless_clients_wow_exe_outside_the_users_is_not_the_players(self):
        # #652: a live session's Wow.exe ran beside a dead session's leftovers, and the proof blamed the player.
        processes = {
            43: {"WINEPREFIX": str(fc.PREFIX)},
            44: {"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": "another-session"},
        }
        with (
            mock.patch.object(fc, "prefix_users", return_value=[43]),
            mock.patch.object(fc, "client_pid", return_value=44),
            mock.patch.object(fc, "read_environ", side_effect=lambda pid: processes[pid]),
        ):
            reason = fc.client_in_use()
        self.assertNotIn("player", reason)
        self.assertEqual(reason, "a headless session holds the client (Wow.exe, pid 44)")

    def test_a_headless_clients_wow_exe_among_the_users_is_not_the_players_either(self):
        # `up --wait` refuses over every prefix process, so the session's own client is in `users` here.
        with (
            mock.patch.object(fc, "prefix_users", return_value=[44]),
            mock.patch.object(fc, "client_pid", return_value=44),
            mock.patch.object(fc, "read_environ", return_value={"FOREVER_CLIENT_SESSION": "another-session"}),
        ):
            reason = fc.client_in_use()
        self.assertEqual(reason, "a headless session holds the client (Wow.exe, pid 44)")

    def test_leftover_processes_only_give_the_count(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[41, 42]),
            mock.patch.object(fc, "client_pid", return_value=None),
        ):
            self.assertEqual(fc.client_in_use(), "2 Wine processes still run in it")

    def test_a_wow_exe_outside_the_users_without_a_session_is_not_the_players(self):
        with (
            mock.patch.object(fc, "prefix_users", return_value=[41, 42]),
            mock.patch.object(fc, "client_pid", return_value=44),
            mock.patch.object(fc, "read_environ", return_value={"WINEPREFIX": str(fc.PREFIX)}),
        ):
            self.assertEqual(fc.client_in_use(), "2 Wine processes still run in it")

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

    def test_smoke_refuses_live_unsafe_state_before_build_or_input(self):
        with (
            mock.patch.object(fc, "require_safe", REAL_REQUIRE_SAFE),
            mock.patch.object(fc, "client_ui", return_value={"safety": True, "dead": False, "combat": True}),
            mock.patch.object(fc, "x") as inputs,
            self.assertRaisesRegex(fc.SafetyRefusal, "player is in combat"),
        ):
            self.run_smoke()
        inputs.assert_not_called()
        self.reload.assert_not_called()
        self.released.assert_called_once()

    def setUp(self):
        self.enterContext(mock.patch.object(fc, "prefix_users", return_value=[]))
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.enterContext(mock.patch.object(fc, "require_safe"))
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
        (self.workspace / "forever-core").mkdir()
        self.enterContext(mock.patch.object(fc, "WORKSPACE", self.workspace))
        self.released_folder = self.state / "released/LegacyForever"
        self.released_folder.mkdir(parents=True)
        self.posted = mock.Mock()
        self.reload = mock.Mock()
        self.ensure = mock.Mock(side_effect=self.start_session)
        self.released = mock.Mock()

    def start_session(self, _timeout, _manual_launcher=False):
        return {"started": 1.0, "ready": 2.0, "display": ":1", "runtime_dir": "/run/user/1"}

    def report(self, *counts):
        """`errors --addon` answering with one live group per count, as forever_errors.py --json does."""
        answers = [
            mock.Mock(returncode=1 if count else 0, stdout=json.dumps([{"signature": "x"}] * count), stderr="")
            for count in counts
        ]
        return mock.patch.object(fc, "errors", side_effect=answers)

    def smoke(self, argv=None):
        options = {
            "repo": "legacy-forever",
            "ref": "main",
            "timeout": 600,
            "manual_launcher": False,
            "no_post": False,
        }
        options.update(argv or {})
        return fc.smoke(argparse.Namespace(**options))

    def run_smoke(
        self,
        answers=(0,),
        busy=None,
        later=None,
        ensure=None,
        main_argv=None,
        repo=None,
        folders=None,
        registrations=None,
        startup=None,
        slash=None,
    ):
        folders = folders or [("LegacyForever", self.build)]
        startup = startup if startup is not None else mock.Mock(return_value=registrations or [])
        with (
            mock.patch.object(fc, "git", return_value="0123456789abcdef0123456789abcdef01234567"),
            mock.patch.object(fc, "foreign_client", side_effect=[busy, later]),
            mock.patch.object(fc, "build_dev", return_value=self.build) as build,
            mock.patch.object(fc, "package_name", return_value="LegacyForever"),
            mock.patch.object(fc, "addon_folders", return_value=folders),
            mock.patch.object(fc, "ensure_session", ensure or self.ensure),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "release_job", self.released),
            mock.patch.object(fc, "reload", self.reload),
            mock.patch.object(fc, "job_started", return_value=3.0),
            mock.patch.object(fc, "slash", slash or mock.Mock()),
            mock.patch.object(fc, "post_status", self.posted),
            mock.patch.object(fc, "stop_handlers", return_value={}),
            mock.patch.object(fc, "restore_handlers"),
            mock.patch.object(fc, "smoke_registrations", startup),
            self.report(*answers),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            code = fc.main(main_argv) if main_argv else self.smoke({"repo": repo} if repo else None)
        return code, out.getvalue(), build

    def test_sign_in_unavailable_posts_nothing(self):
        code, printed, build = self.run_smoke(ensure=mock.Mock(side_effect=fc.SignInRequired(fc.SIGN_IN_MESSAGE)))
        self.assertEqual(code, 3)
        self.assertIn("needs the player's sign-in", printed)
        self.posted.assert_not_called()
        build.assert_not_called()
        self.released.assert_called_once()

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
        self.reload.assert_called_once()
        self.released.assert_called_once()

    def test_a_smoke_clears_the_eval_inbox_when_it_starts_and_ends(self):
        with mock.patch.object(fc, "clear_eval_inbox") as clear:
            code, _printed, _build = self.run_smoke()
        self.assertEqual(code, 0)
        self.assertEqual(clear.call_args_list, [mock.call(), mock.call(quiet=True)])

    def test_manual_launcher_flag_reaches_the_session(self):
        argv = ["smoke", "--repo", "legacy-forever", "--ref", "main"]
        code, _printed, _build = self.run_smoke(main_argv=argv)
        self.assertEqual(code, 0)
        self.assertFalse(self.ensure.call_args.args[1])
        code, _printed, _build = self.run_smoke(main_argv=[*argv, "--manual-launcher"])
        self.assertEqual(code, 0)
        self.assertTrue(self.ensure.call_args.args[1])

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
        def start(_timeout, _manual_launcher=False):
            raise fc.ClientError("the Wine prefix is in use")

        code, _printed, _build = self.run_smoke(ensure=start, later="the player's client is running")
        self.assertEqual(code, 3)
        self.posted.assert_not_called()
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_session_that_cannot_start_posts_nothing(self):
        # #727: a sign-in or a start that timed out says nothing about the commit, so no status is posted.
        def start(_timeout, _manual_launcher=False):
            raise fc.ClientError("the world did not load within 600 s")

        code, printed, _build = self.run_smoke(ensure=start)
        self.assertEqual(code, 2)
        self.posted.assert_not_called()
        self.assertIn("no result, nothing posted: the world did not load", printed)
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_refused_selftest_posts_nothing(self):
        refused = mock.Mock(side_effect=fc.ClientError("slash refused: outside the world or Game Menu is shown"))
        code, printed, _build = self.run_smoke(slash=refused)
        self.assertEqual(code, 2)
        self.posted.assert_not_called()
        self.assertIn("nothing posted: slash refused", printed)
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_client_that_is_not_in_use_smokes(self):
        # A resident session's own Wine processes are not a busy client: only the player's game is.
        code, _printed, _build = self.run_smoke(busy=None)
        self.assertEqual(code, 0)
        self.posted.assert_called_once()

    def released_tool(self):
        """A stand-in for tools/released_consumers.py: one consumer's released folder, no network."""
        folder = self.released_folder

        class Tool:
            class ReleasedError(RuntimeError):
                pass

            @staticmethod
            def released_folders(destination=None):
                return [("LegacyForever", folder)]

        return Tool

    def test_the_smoke_folders_add_the_released_builds_for_core_only(self):
        core = self.state / "core"
        core.mkdir()
        with mock.patch.object(fc, "released_consumers_tool", side_effect=self.released_tool):
            self.assertEqual(
                fc.smoke_folders("forever-core", [("ForeverCore", core)]),
                (
                    [("ForeverCore", core), ("LegacyForever", self.released_folder)],
                    [("LegacyForever", self.released_folder)],
                ),
            )
        with mock.patch.object(fc, "released_consumers_tool", side_effect=AssertionError("no release download")):
            self.assertEqual(
                fc.smoke_folders("legacy-forever", [("LegacyForever", self.build)]),
                ([("LegacyForever", self.build)], []),
            )

    def test_the_smoke_folders_unpack_the_released_builds_into_a_smoke_private_folder(self):
        core = self.state / "core"
        core.mkdir()
        captured = {}

        class Tool:
            class ReleasedError(RuntimeError):
                pass

            @staticmethod
            def released_folders(destination):
                captured["destination"] = destination
                return [("LegacyForever", self.released_folder)]

        with mock.patch.object(fc, "BUILD_ROOT", self.state / "builds"):
            with mock.patch.object(fc, "released_consumers_tool", return_value=Tool):
                fc.smoke_folders("forever-core", [("ForeverCore", core)])
        self.assertEqual(captured["destination"], self.state / "builds" / "forever-core-smoke-released")

    def test_a_core_smoke_links_the_consumers_released_builds_and_counts_them(self):
        core = self.state / "core"
        core.mkdir()
        with mock.patch.object(fc, "released_consumers_tool", side_effect=self.released_tool):
            code, printed, _build = self.run_smoke(answers=(0, 0), repo="forever-core", folders=[("ForeverCore", core)])
        self.assertEqual(code, 0)
        self.posted.assert_called_once_with(
            "forever-core",
            "0123456789abcdef0123456789abcdef01234567",
            True,
            "clean: no Lua errors in 2 addon folders",
        )
        self.assertIn("linking 1 released consumer folder", printed)
        self.assertFalse((self.addons / "ForeverCore").exists())
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_released_consumer_that_did_not_start_fails_the_status(self):
        core = self.state / "core"
        core.mkdir()
        with mock.patch.object(fc, "released_consumers_tool", side_effect=self.released_tool):
            code, printed, _build = self.run_smoke(
                answers=(0, 0),
                repo="forever-core",
                folders=[("ForeverCore", core)],
                registrations=["LegacyForever"],
            )
        self.assertEqual(code, 1)
        self.posted.assert_called_once_with(
            "forever-core",
            "0123456789abcdef0123456789abcdef01234567",
            False,
            "1 did not start: LegacyForever",
        )
        self.assertIn("1 did not start: LegacyForever", printed)

    def test_smoke_description_names_lua_errors_and_unstarted_addons(self):
        self.assertEqual(
            fc.smoke_description({"LegacyForever": 2, "SkillUpForever": 0}, ["TweaksForever"]),
            "2 Lua errors: 2 LegacyForever; 1 did not start: TweaksForever",
        )

    def test_the_startup_check_asks_after_every_released_folder(self):
        source = fc.registration_source(["LegacyForever", "TweaksForever"])
        self.assertIn("core.Registered(name)", source)
        self.assertIn('"LegacyForever"', source)
        self.assertIn('"TweaksForever"', source)
        self.assertIn('print("not registered: "', source)

    def test_only_the_startup_checks_own_lines_name_unstarted_folders(self):
        lines = ["not registered: TweaksForever", "something else", "not registered: LegacyForever", 7]
        self.assertEqual(fc.not_registered(lines), ["TweaksForever", "LegacyForever"])

    def test_smoke_registrations_reads_the_snippet_own_eval_record(self):
        class Tool:
            class EvalError(RuntimeError):
                pass

            @staticmethod
            def lua_string(value):
                return f'"{value}"'

            @staticmethod
            def write_snippet(path, addons=None, capture=False):
                self.assertEqual(capture, False)
                return {"token": "run-token"}

        record = {"ok": True, "out": {1: "not registered: TweaksForever"}}
        with (
            mock.patch.object(fc, "devsmoke_eval", return_value=Tool),
            mock.patch.object(fc, "reload") as reloaded,
            mock.patch.object(fc, "clear_eval_inbox") as cleared,
            mock.patch.object(fc, "saved_eval", return_value=record) as saved,
        ):
            names = fc.smoke_registrations({"started": 1.0}, [("TweaksForever", self.released_folder)])
        self.assertEqual(names, ["TweaksForever"])
        self.assertEqual(reloaded.call_count, 2)
        self.assertEqual(cleared.call_count, 2)
        saved.assert_called_once_with("run-token")

    def test_a_startup_check_snippet_that_raises_is_an_error(self):
        class Tool:
            class EvalError(RuntimeError):
                pass

            @staticmethod
            def lua_string(value):
                return f'"{value}"'

            @staticmethod
            def write_snippet(path, addons=None, capture=False):
                return {"token": "run-token"}

        with (
            mock.patch.object(fc, "devsmoke_eval", return_value=Tool),
            mock.patch.object(fc, "reload"),
            mock.patch.object(fc, "clear_eval_inbox"),
            mock.patch.object(
                fc, "saved_eval", return_value={"ok": False, "out": [], "err": "ForeverCore.Registered is missing"}
            ),
            self.assertRaisesRegex(fc.ClientError, "startup check failed"),
        ):
            fc.smoke_registrations({"started": 1.0}, [("TweaksForever", self.released_folder)])

    def test_the_startup_check_runs_for_released_folders_only(self):
        core = self.state / "core"
        core.mkdir()
        registrations = mock.Mock(return_value=[])
        with mock.patch.object(fc, "released_consumers_tool", side_effect=self.released_tool):
            self.run_smoke(answers=(0, 0), repo="forever-core", folders=[("ForeverCore", core)], startup=registrations)
        registrations.assert_called_once()
        self.assertEqual(registrations.call_args.args[1], [("LegacyForever", self.released_folder)])

    def test_a_startup_check_that_could_not_run_fails_the_status(self):
        core = self.state / "core"
        core.mkdir()
        with mock.patch.object(fc, "released_consumers_tool", side_effect=self.released_tool):
            code, printed, _build = self.run_smoke(
                answers=(0, 0),
                repo="forever-core",
                folders=[("ForeverCore", core)],
                startup=mock.Mock(side_effect=fc.ClientError("no !!DevSmoke link")),
            )
        self.assertEqual(code, 1)
        self.posted.assert_called_once_with(
            "forever-core",
            "0123456789abcdef0123456789abcdef01234567",
            False,
            "smoke did not finish: no !!DevSmoke link",
        )
        self.assertIn("no !!DevSmoke link", printed)

    def test_a_core_smoke_that_cannot_fetch_the_released_builds_posts_nothing(self):
        class Broken:
            class ReleasedError(RuntimeError):
                pass

            @staticmethod
            def released_folders(destination=None):
                raise Broken.ReleasedError("could not read legacy-forever's latest release")

        with (
            mock.patch.object(fc, "git", return_value="a" * 40),
            mock.patch.object(fc, "foreign_client", return_value=None),
            mock.patch.object(fc, "build_dev", return_value=self.build),
            mock.patch.object(fc, "package_name", return_value="ForeverCore"),
            mock.patch.object(fc, "addon_folders", return_value=[("ForeverCore", self.build)]),
            mock.patch.object(fc, "ensure_session", side_effect=self.start_session),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "release_job") as release_job,
            mock.patch.object(fc, "post_status", self.posted),
            mock.patch.object(fc, "released_consumers_tool", return_value=Broken),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            code = fc.main(["smoke", "--repo", "forever-core", "--ref", "main"])
        self.assertEqual(code, 2)
        self.posted.assert_not_called()
        self.assertIn("could not read legacy-forever's latest release", err.getvalue())
        release_job.assert_called_once()

    def test_no_post_prints_the_result_and_posts_nothing(self):
        argv = ["smoke", "--repo", "legacy-forever", "--ref", "main", "--no-post"]
        code, printed, _build = self.run_smoke(main_argv=argv)
        self.assertEqual(code, 0)
        self.posted.assert_not_called()
        self.assertIn("clean: no Lua errors in 1 addon folder (not posted)", printed)

    def test_no_post_still_exits_one_on_errors(self):
        argv = ["smoke", "--repo", "legacy-forever", "--ref", "main", "--no-post"]
        code, printed, _build = self.run_smoke(answers=(2,), main_argv=argv)
        self.assertEqual(code, 1)
        self.posted.assert_not_called()
        self.assertIn("2 Lua errors: 2 LegacyForever (not posted)", printed)

    def test_a_no_post_result_with_no_counts_is_printed_and_not_posted(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = fc.report_smoke("legacy-forever", "a" * 40, {"counts": {}, "error": "boom"}, post=False)
        self.assertEqual(code, 2)
        self.posted.assert_not_called()
        self.assertIn("no result, nothing posted: boom", out.getvalue())

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
        self.reload.side_effect = KeyboardInterrupt
        code, _printed, _build = self.run_smoke()
        self.assertEqual(code, 1)
        self.posted.assert_not_called()
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.released.assert_called_once()

    def test_a_result_with_no_counts_and_no_error_posts_nothing(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = fc.report_smoke("legacy-forever", "a" * 40, {"counts": {}, "error": None})
        self.assertEqual(code, 1)
        self.posted.assert_not_called()
        self.assertIn("stopped before it finished", err.getvalue())

    def test_the_linked_build_is_reloaded_then_selftested_then_read(self):
        calls = []

        def selftest(_state, command):
            calls.append(command)
            # The linked candidate is what the client just reloaded, before the selftest runs.
            self.assertTrue((self.addons / "LegacyForever").is_symlink())

        with (
            mock.patch.object(fc, "git", return_value="a" * 40),
            mock.patch.object(fc, "foreign_client", return_value=None),
            mock.patch.object(fc, "build_dev", return_value=self.build),
            mock.patch.object(fc, "package_name", return_value="LegacyForever"),
            mock.patch.object(fc, "addon_folders", return_value=[("LegacyForever", self.build)]),
            mock.patch.object(fc, "ensure_session", side_effect=self.start_session),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "reload", side_effect=lambda _state: calls.append("reload")),
            mock.patch.object(fc, "slash", side_effect=selftest),
            mock.patch.object(fc, "errors", return_value=mock.Mock(returncode=0, stdout="[]", stderr="")) as read,
            mock.patch.object(fc, "post_status"),
            mock.patch.object(fc, "stop_handlers", return_value={}),
            mock.patch.object(fc, "restore_handlers"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(self.smoke(), 0)
        self.assertEqual(calls, ["reload", "/forever selftest"])
        read.assert_called_once_with(mock.ANY, "LegacyForever", as_json=True)
        self.assertFalse((self.addons / "LegacyForever").exists())

    def test_a_smoke_rejects_a_repository_name_that_is_a_path(self):
        with self.assertRaisesRegex(fc.ClientError, "repository name"):
            self.smoke({"repo": "../etc"})

    def test_a_missing_checkout_says_where_it_looked(self):
        with self.assertRaisesRegex(fc.ClientError, "no checkout of other-repo"):
            self.smoke({"repo": "other-repo"})

    def test_an_errors_read_that_prints_no_json_posts_nothing(self):
        with (
            mock.patch.object(fc, "git", return_value="a" * 40),
            mock.patch.object(fc, "foreign_client", return_value=None),
            mock.patch.object(fc, "build_dev", return_value=self.build),
            mock.patch.object(fc, "package_name", return_value="LegacyForever"),
            mock.patch.object(fc, "addon_folders", return_value=[("LegacyForever", self.build)]),
            mock.patch.object(fc, "ensure_session", side_effect=self.start_session),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "reload"),
            mock.patch.object(fc, "slash"),
            mock.patch.object(fc, "errors", return_value=mock.Mock(returncode=0, stdout="oops", stderr="")),
            mock.patch.object(fc, "post_status") as posted,
            mock.patch.object(fc, "stop_handlers", return_value={}),
            mock.patch.object(fc, "restore_handlers"),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            code = self.smoke()
        # An unreadable error log says nothing about the commit, so nothing is posted and it is smoked again (#727).
        self.assertEqual(code, 2)
        posted.assert_not_called()
        self.assertIn("printed no JSON", out.getvalue())

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
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.enterContext(mock.patch.object(fc, "require_safe"))
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

    def test_parse_flow_clicks_takes_a_named_point_in_screenshot_coordinates(self):
        flows = [("update notice", "/lf"), ("professions", "/sf")]
        self.assertEqual(fc.parse_flow_clicks([], flows), {})
        self.assertEqual(
            fc.parse_flow_clicks(["professions=400, 300", "update notice = 12,34"], flows),
            {"professions": (400, 300), "update notice": (12, 34)},
        )

    def test_parse_flow_clicks_refuses_a_name_no_flow_has(self):
        flows = [("update notice", "/lf")]
        with self.assertRaisesRegex(fc.ClientError, r"no --flow of that name \(update notice\)"):
            fc.parse_flow_clicks(["profession=400,300"], flows)

    def test_parse_flow_clicks_refuses_a_point_that_is_not_two_integers(self):
        flows = [("professions", "/sf"), ("update notice", "/lf")]
        for bad in ("professions", "professions=", "=1,2", "professions=1", "professions=1,2,3", "professions=a,b"):
            with self.subTest(bad=bad), self.assertRaises(fc.ClientError):
                fc.parse_flow_clicks([bad], flows)
        with self.assertRaisesRegex(fc.ClientError, "outside the"):
            fc.parse_flow_clicks([f"professions={fc.WIDTH},10"], flows)

    def test_flow_slug_is_a_file_name(self):
        self.assertEqual(fc.flow_slug("Update notice!"), "update-notice")
        self.assertEqual(fc.flow_slug("***"), "flow")

    def test_flow_step_names_a_lua_snippet_by_file_name_and_digest(self):
        lua = self.state / "westfall-map.lua"
        lua.write_text("print('map')\n")
        digest = fc.hashlib.sha256(lua.read_bytes()).hexdigest()
        self.assertEqual(fc.flow_step(str(lua)), f"sha256:{digest} westfall-map.lua")
        self.assertEqual(fc.flow_step("/wait 25"), "/wait 25")

    def test_clear_eval_inbox_asks_the_writer_for_the_client_addons(self):
        client = self.state / "client"
        tool = mock.Mock()
        with (
            mock.patch.object(fc, "CLIENT", client),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
        ):
            fc.clear_eval_inbox()
        tool.clear_inbox.assert_called_once_with(addons=client / "Interface/AddOns")

    def test_a_flow_clicks_after_the_world_screenshot_and_before_its_ready_one(self):
        client = self.state / "client"
        shots = client / "Screenshots"
        shots.mkdir(parents=True)
        state_dir = self.state / "state"
        state_dir.mkdir()
        events = []

        def fake_reload(_state):
            events.append("reload")
            return self.state / "reloaded.png"

        def fake_sleep(_seconds):
            # The reload's world screenshot lands while the flow waits for the frame its click aims at.
            if not (shots / "1-world.png").exists():
                (shots / "1-world.png").write_bytes(b"world")

        def fake_x(_state, *args):
            present = sorted(path.name for path in shots.glob("*"))
            self.assertEqual(present, ["1-world.png"], "the click follows the world screenshot")
            self.assertEqual(args, ("mousemove", "400", "300", "click", "1"))
            events.append("click")
            (shots / "2-flow.png").write_bytes(b"flow")

        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_slash.return_value = {
            "chunk": Path("/x/Eval.lua"),
            "snippet": Path("/sf"),
            "lines": 5,
            "token": "run-1",
        }
        with (
            mock.patch.object(fc, "CLIENT", client),
            mock.patch.object(fc, "STATE_DIR", state_dir),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "allowed_command"),
            mock.patch.object(fc, "reload", side_effect=fake_reload),
            mock.patch.object(fc, "clear_eval_inbox"),
            mock.patch.object(fc, "client_ui", return_value={"world": True, "menu": False}),
            mock.patch.object(fc, "x", side_effect=fake_x),
            mock.patch.object(fc.time, "sleep", side_effect=fake_sleep),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(fc.run_flow({"ready": True}, "/sf", (400, 300)), "run-1")
        self.assertEqual(events, ["reload", "click"])
        self.assertIn("clicked 400,300 after 1-world.png", out.getvalue())

    def test_a_flow_without_a_click_never_clicks_nor_waits_for_the_world_frame(self):
        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_slash.return_value = {
            "chunk": Path("/x/Eval.lua"),
            "snippet": Path("/sf"),
            "lines": 5,
            "token": "run-1",
        }
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "allowed_command"),
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "reload"),
            mock.patch.object(fc, "clear_eval_inbox"),
            mock.patch.object(fc, "click") as clicked,
            mock.patch.object(fc, "wait_for_flow_world") as world,
            mock.patch.object(fc, "wait_for_flow_ready") as ready,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.run_flow("state", "/sf"), "run-1")
        clicked.assert_not_called()
        world.assert_not_called()
        ready.assert_called_once_with(set(), "/sf", "run-1", state="state")

    def test_run_flow_runs_a_slash_command_through_devsmoke(self):
        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_slash.return_value = {
            "chunk": Path("/x/!!DevSmokeInbox/Eval.lua"),
            "snippet": Path("/lf"),
            "lines": 5,
            "token": "run-slash",
        }
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "allowed_command") as allowed,
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "reload") as reload,
            mock.patch.object(fc, "clear_eval_inbox") as clear,
            mock.patch.object(fc, "wait_for_flow_ready") as ready,
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(fc.run_flow("state", "/lf"), "run-slash")
        allowed.assert_called_once_with("/lf")
        tool.write_slash.assert_called_once_with("/lf", addons=self.state / "client/Interface/AddOns", capture=True)
        reload.assert_called_once_with("state")
        clear.assert_called_once_with()
        ready.assert_called_once_with(set(), "/lf", "run-slash", state="state")
        self.assertIn("wrote /x/!!DevSmokeInbox/Eval.lua from /lf (5 lines)", out.getvalue())

    def test_run_flow_reports_a_ready_failure_with_the_flows_own_token(self):
        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_slash.return_value = {
            "chunk": Path("/x/Eval.lua"),
            "snippet": Path("/lf"),
            "lines": 5,
            "token": "run-slash",
        }
        timeout = fc.ClientError("the flow did not say it was ready")
        precise = fc.ClientError("the flow /lf could not be captured: the flow's ready check failed: boom")
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "allowed_command"),
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "reload"),
            mock.patch.object(fc, "clear_eval_inbox"),
            mock.patch.object(fc, "wait_for_flow_ready", side_effect=timeout),
            mock.patch.object(fc, "flow_capture_failure", return_value=precise) as failure,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(fc.ClientError, "ready check failed: boom"),
        ):
            fc.run_flow("state", "/lf")
        failure.assert_called_once_with("state", "/lf", "run-slash", timeout)

    def test_run_flow_writes_reloads_and_answers_the_run_token(self):
        tool = mock.Mock()
        tool.write_snippet.return_value = {
            "chunk": Path("/x/!!DevSmokeInbox/Eval.lua"),
            "snippet": Path("notice.lua"),
            "lines": 3,
            "token": "run-1",
        }
        tool.EvalError = Exception
        earlier = {self.state / "earlier.jpg"}
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "screenshots", return_value=earlier),
            mock.patch.object(fc, "reload") as reload,
            mock.patch.object(fc, "clear_eval_inbox") as clear,
            mock.patch.object(fc, "wait_for_flow_ready") as ready,
            mock.patch.object(fc, "saved_eval") as saved,
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(fc.run_flow("state", "notice.lua"), "run-1")
        reload.assert_called_once_with("state")
        clear.assert_called_once_with()
        ready.assert_called_once_with(earlier, "notice.lua", "run-1", state="state")
        saved.assert_not_called()  # the result is read after the flow's screenshot
        tool.write_snippet.assert_called_once_with(
            Path("notice.lua"), addons=self.state / "client/Interface/AddOns", capture=True
        )
        self.assertIn("wrote /x/!!DevSmokeInbox/Eval.lua from notice.lua (3 lines)", out.getvalue())

    def test_a_lua_flow_waits_for_the_world_and_its_own_screenshot(self):
        earlier = self.state / "0-earlier.jpg"
        world = self.state / "1-world.jpg"
        flow = self.state / "2-flow.jpg"
        for index, path in enumerate((earlier, world, flow)):
            path.write_bytes(b"image")
            os.utime(path, (100 + index, 100 + index))
        clock = FakeClock()
        with (
            mock.patch.object(fc, "screenshots", return_value={earlier, world, flow}),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
        ):
            self.assertEqual(fc.wait_for_flow_ready({earlier}, "notice.lua"), flow)

    def test_a_lua_flow_that_never_signals_fails_on_the_timeout(self):
        world = self.state / "1-world.jpg"
        world.write_bytes(b"world")
        os.utime(world, (100, 100))
        clock = FakeClock()
        with (
            mock.patch.object(fc, "screenshots", return_value={world}),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            self.assertRaisesRegex(fc.ClientError, r"notice\.lua did not say it was ready to capture"),
        ):
            fc.wait_for_flow_ready(set(), "notice.lua", timeout=5)
        self.assertEqual(clock.now, 5)

    def test_wait_for_flow_ready_reports_the_recorded_failure_before_its_timeout(self):
        world = self.state / "1-world.jpg"
        world.write_bytes(b"world")
        os.utime(world, (100, 100))
        clock = FakeClock()
        failed = {"run": "run-1", "ready": "failed", "readyErr": "the flow's ready check failed: boom"}
        with (
            mock.patch.object(fc, "screenshots", return_value={world}),
            mock.patch.object(fc, "saved_eval", side_effect=[fc.ClientError("earlier run"), failed]),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            self.assertRaisesRegex(fc.ClientError, "ready check failed: boom"),
        ):
            fc.wait_for_flow_ready(set(), "notice.lua", token="run-1", timeout=30)
        self.assertEqual(clock.now, 1, "the recorded reason ends the wait at once")

    def test_a_ready_failure_falls_back_to_a_saving_reload_only_when_unrecorded(self):
        timeout = fc.ClientError("the flow did not say it was ready")
        with (
            mock.patch.object(fc, "flow_ready_failure", side_effect=[None, "the flow was not ready: boom"]),
            mock.patch.object(fc, "reload") as reload,
        ):
            failure = fc.flow_capture_failure({}, "notice.lua", "run-1", timeout)
        reload.assert_called_once_with({})
        self.assertIn("the flow was not ready: boom", str(failure))

    def test_check_flow_eval_fails_on_the_error_its_own_snippet_raised(self):
        saved = {"run": "run-1", "ran": 7, "ok": False, "out": {1: "before"}, "err": "boom\nstack"}
        with (
            mock.patch.object(fc, "reload") as reload,
            mock.patch.object(fc, "saved_eval", return_value=saved) as read,
            contextlib.redirect_stdout(io.StringIO()) as out,
            self.assertRaises(fc.ClientError) as failure,
        ):
            fc.check_flow_eval("state", "notice.lua", "run-1")
        reload.assert_called_once_with("state")
        read.assert_called_once_with("run-1")
        self.assertIn("DevSmokeDB.eval: failed, ran 7\nbefore\nerror:\nboom\nstack", out.getvalue())
        message = str(failure.exception)
        self.assertIn("flow snippet notice.lua failed", message)
        self.assertIn("error:\nboom\nstack", message, "the snippet's own error is quoted")

    def test_run_flow_runs_a_lua_file_given_by_its_absolute_path(self):
        with (
            mock.patch.object(fc, "slash") as slash,
            mock.patch.object(fc, "devsmoke_eval", side_effect=RuntimeError("evaluated")),
            self.assertRaisesRegex(RuntimeError, "evaluated"),
        ):
            fc.run_flow({}, "/home/me/notice.lua")
        slash.assert_not_called()

    def test_run_flow_reports_a_snippet_the_compiler_refused(self):
        class Refused(Exception):
            pass

        tool = mock.Mock()
        tool.write_snippet.side_effect = Refused("notice.lua:2: 'end' expected")
        tool.EvalError = Refused
        with (
            mock.patch.object(fc, "CLIENT", self.state / "client"),
            mock.patch.object(fc, "devsmoke_eval", return_value=tool),
            mock.patch.object(fc, "reload") as reload,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(fc.ClientError, "notice.lua:2: 'end' expected"),
        ):
            fc.run_flow("state", "notice.lua")
        reload.assert_not_called()

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

    def test_proof_refuses_live_unsafe_state_before_build_or_input(self):
        with (
            mock.patch.object(fc, "require_safe", REAL_REQUIRE_SAFE),
            mock.patch.object(fc, "client_ui", return_value={"safety": True, "dead": False, "combat": True}),
            mock.patch.object(fc, "x") as inputs,
            self.assertRaisesRegex(fc.SafetyRefusal, "player is in combat"),
        ):
            self.run_proof()
        inputs.assert_not_called()
        self.reload.assert_not_called()
        self.released.assert_called_once()

    def setUp(self):
        self.enterContext(mock.patch.object(fc, "client_ui", return_value={"world": True, "menu": False}))
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.enterContext(mock.patch.object(fc, "require_safe"))
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state / "state"))
        self.enterContext(mock.patch.object(fc, "PROOF_SCRATCH", self.state / "scratch"))
        self.enterContext(mock.patch.object(fc, "BUILD_ROOT", self.state / "builds"))
        self.client = self.state / "client"
        self.addons = self.client / "Interface/AddOns"
        self.addons.mkdir(parents=True)
        self.enterContext(mock.patch.object(fc, "CLIENT", self.client))
        self.enterContext(mock.patch.object(fc, "allowed_command"))
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
        self.click = mock.Mock()
        self.proof_digests = mock.Mock(return_value={"input_digest": "digest", "candidate": "candidate"})
        self.create_gist = mock.Mock(return_value="abc123")
        self.upload = mock.Mock(
            return_value=[{"url": "https://gist.example/raw/" + "f" * 40 + "/1-update-notice.png", "sha256": "0" * 64}]
        )
        self.client_build = mock.Mock(return_value="1.60.1.70938 (Interface 16001)")
        self.compare = mock.Mock(return_value={"equivalent": True})
        self.build_dev = mock.Mock(return_value=self.build)
        self.ensure = mock.Mock(side_effect=self.start_session)
        self.released = mock.Mock()
        self.eval_tool = mock.Mock()
        self.eval_tool.EvalError = Exception
        self.eval_tool.write_slash.return_value = {
            "chunk": Path("/x/Eval.lua"),
            "snippet": Path("/lf"),
            "lines": 5,
            "token": "run-1",
        }
        self.saved_eval({"run": "run-1", "ran": 7, "ok": True, "out": {1: "shown"}})

    def start_session(self, _timeout, _manual_launcher=False):
        return {"started": 1.0, "ready": 2.0, "display": ":1", "runtime_dir": "/run/user/1"}

    def options(self, **overrides):
        values = {
            "repo": "legacy-forever",
            "ref": "main",
            "checkout": self.checkout,
            "flow": ["update notice=/lf"],
            "flow_click": [],
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

    def saved_eval(self, record: dict) -> Path:
        """The SavedVariables file the session before this one left behind, holding one DevSmokeDB.eval record."""

        def lua_value(value):
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, int):
                return str(value)
            if isinstance(value, dict):
                return "{ " + ", ".join(lua_value(item) for item in value.values()) + " }"
            text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{text}"'

        saved = self.client / "WTF/Account/1/SavedVariables"
        saved.mkdir(parents=True, exist_ok=True)
        path = saved / "!!DevSmoke.lua"
        fields = ",\n".join(f'\t\t["{key}"] = {lua_value(value)}' for key, value in record.items())
        path.write_text(f'DevSmokeDB = {{\n\t["eval"] = {{\n{fields},\n\t}},\n}}\n')
        return path

    def run_proof(self, **overrides):
        ensure = overrides.pop("ensure", None)
        overrides.pop("up", None)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(fc, "git", side_effect=self.fake_git))
            stack.enter_context(mock.patch.object(fc, "foreign_client", side_effect=self.busy))
            stack.enter_context(mock.patch.object(fc, "recover_links"))
            stack.enter_context(mock.patch.object(fc, "build_dev", self.build_dev))
            stack.enter_context(mock.patch.object(fc, "package_name", return_value="LegacyForever"))
            stack.enter_context(mock.patch.object(fc, "addon_folders", return_value=[("LegacyForever", self.build)]))
            stack.enter_context(mock.patch.object(fc, "ensure_session", ensure or self.ensure))
            stack.enter_context(mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")))
            stack.enter_context(mock.patch.object(fc, "release_job", self.released))
            stack.enter_context(mock.patch.object(fc, "reload", self.reload))
            stack.enter_context(mock.patch.object(fc, "job_started", return_value=3.0))
            stack.enter_context(mock.patch.object(fc, "slash", side_effect=self.fake_slash))
            stack.enter_context(mock.patch.object(fc, "wait_for_flow_ready", return_value=self.state / "flow.jpg"))
            stack.enter_context(mock.patch.object(fc, "wait_for_flow_world", return_value=self.state / "world.jpg"))
            stack.enter_context(mock.patch.object(fc, "click", self.click))
            stack.enter_context(mock.patch.object(fc, "devsmoke_eval", return_value=self.eval_tool))
            stack.enter_context(mock.patch.object(fc, "shot", side_effect=self.fake_shot))
            stack.enter_context(mock.patch.object(fc, "proof_digests", self.proof_digests))
            stack.enter_context(mock.patch.object(fc, "create_gist", self.create_gist))
            stack.enter_context(mock.patch.object(fc, "upload_screenshots", self.upload))
            stack.enter_context(mock.patch.object(fc, "client_build", self.client_build))
            stack.enter_context(mock.patch.object(fc, "proof_compare", self.compare))
            stack.enter_context(mock.patch.object(fc, "stop_handlers", return_value={}))
            stack.enter_context(mock.patch.object(fc, "restore_handlers"))
            stack.enter_context(mock.patch.object(fc.time, "sleep"))
            out = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            err = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            code = fc.proof(self.options(**overrides))
        return code, out.getvalue(), err.getvalue()

    def test_a_proof_refuses_a_slot_changed_before_capture_or_teardown(self):
        for phase in ("before capture", "teardown"):
            with self.subTest(phase=phase):
                slot = self.addons / "LegacyForever"

                def replace_slot(*_args, slot=slot):
                    slot.unlink()
                    slot.mkdir()

                if phase == "before capture":
                    self.reload.side_effect = replace_slot
                else:
                    self.compare.reset_mock()
                    # run_flow's eval check happens after the screenshot, before teardown.
                patch = (
                    mock.patch.object(fc, "check_flow_eval", side_effect=replace_slot)
                    if phase == "teardown"
                    else contextlib.nullcontext()
                )
                with patch, self.assertRaisesRegex(fc.ClientError, "no longer points at the candidate"):
                    self.run_proof()
                self.assertFalse((self.checkout / fc.PROOF_FILE).exists())
                self.create_gist.assert_not_called()
                slot.rmdir()
                fc.link_record_path().unlink(missing_ok=True)
                self.reload.side_effect = None

    def test_the_manual_launcher_flag_reaches_the_session(self):
        code, _printed, _err = self.run_proof(manual_launcher=True)
        self.assertEqual(code, 0)
        self.assertTrue(self.ensure.call_args.args[1])

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
        self.eval_tool.write_slash.assert_called_once_with("/lf", addons=self.addons, capture=True)
        self.assertEqual([path.name for path in self.shot_paths], ["1-update-notice.png"])
        self.assertEqual(
            self.reload.call_count, 3, "the proof's own, the slash flow's, and the one that saves the eval to disk"
        )
        self.client_build.assert_called_once_with(self.build)
        self.compare.assert_called_once_with(self.checkout, self.build)
        self.assertIn("wrote", printed)
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.released.assert_called_once()

    def test_shared_build_reads_finish_before_the_job_lock_is_released(self):
        def read_while_locked(*_args):
            self.released.assert_not_called()
            return mock.DEFAULT

        def upload_after_release(*_args):
            self.released.assert_called_once()
            return mock.DEFAULT

        self.client_build.side_effect = read_while_locked
        self.compare.side_effect = read_while_locked
        self.create_gist.side_effect = upload_after_release
        self.upload.side_effect = upload_after_release
        code, _printed, _err = self.run_proof()
        self.assertEqual(code, 0)
        self.client_build.assert_called_once_with(self.build)
        self.compare.assert_called_once_with(self.checkout, self.build)
        self.released.assert_called_once()

    def test_a_proof_clicks_the_point_its_flow_names_and_records_it(self):
        code, printed, _err = self.run_proof(flow_click=["update notice=400, 300"])
        self.assertEqual(code, 0)
        self.click.assert_called_once_with(mock.ANY, 400, 300, "1")
        self.assertIn("clicked 400,300", printed)
        proof = json.loads((self.checkout / ".visual-proof.json").read_text())
        self.assertEqual(
            proof["flows"],
            [{"name": "update notice", "steps": ["/lf"], "click": [400, 300], "result": "pass"}],
        )

    def test_a_proof_without_a_flow_click_clicks_nothing(self):
        code, _printed, _err = self.run_proof()
        self.assertEqual(code, 0)
        self.click.assert_not_called()
        proof = json.loads((self.checkout / ".visual-proof.json").read_text())
        self.assertNotIn("click", proof["flows"][0])

    def test_a_flow_click_that_names_no_flow_is_refused_before_the_build(self):
        with self.assertRaisesRegex(fc.ClientError, "no --flow of that name"):
            self.run_proof(flow_click=["profession=400,300"])
        self.build_dev.assert_not_called()

    def test_a_proof_compare_that_fails_removes_a_stale_proof(self):
        (self.checkout / ".visual-proof.json").write_text("stale proof")
        self.compare.side_effect = fc.ClientError("installed build differs")
        with self.assertRaisesRegex(fc.ClientError, "installed build differs"):
            self.run_proof()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.released.assert_called_once()
        self.create_gist.assert_not_called()
        self.upload.assert_not_called()

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

    def test_a_job_that_stops_before_the_flows_records_nothing(self):
        self.reload.side_effect = KeyboardInterrupt
        code, _printed, err = self.run_proof()
        self.assertEqual(code, 1)
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())
        self.assertIn("stopped before it finished", err)
        self.released.assert_called_once()

    def test_a_client_that_fills_while_the_build_links_stops_at_once(self):
        def start(_timeout, _manual_launcher=False):
            raise fc.ClientError("the Wine prefix is in use")

        self.busy = [None, "the player's client is running (Wow.exe, pid 43)"]
        code, printed, _err = self.run_proof(ensure=start)
        self.assertEqual(code, 3)
        self.create_gist.assert_not_called()
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.assertIn("client in use", printed)

    def test_a_failed_flow_puts_the_links_back_and_records_nothing(self):
        self.slash_error = "refused /lf"
        self.eval_tool.EvalError = fc.ClientError
        self.eval_tool.write_slash.side_effect = fc.ClientError("refused /lf")
        with self.assertRaisesRegex(fc.ClientError, "refused /lf"):
            self.run_proof()
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())
        self.released.assert_called_once()

    def test_a_flow_that_fails_in_the_world_reports_its_own_error_not_a_busy_client(self):
        # In the world the job holds the client, so the busy check must not name our own session as another's.
        self.busy = [None, "another session holds the client", "another session holds the client"]
        self.eval_tool.EvalError = fc.ClientError
        self.eval_tool.write_slash.side_effect = fc.ClientError("refused /lf")
        with self.assertRaisesRegex(fc.ClientError, "refused /lf"):
            self.run_proof()
        self.assertFalse((self.addons / "LegacyForever").exists())
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())
        self.released.assert_called_once()

    def test_a_lua_flow_takes_a_shot_after_the_snippet_ran(self):
        lua = self.state / "notice.lua"
        lua.write_text("print('shown')\n")
        self.saved_eval({"run": "run-1", "ran": 7, "ok": True, "out": {1: "shown"}})
        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_snippet.return_value = {"chunk": Path("/x/Eval.lua"), "snippet": lua, "lines": 1, "token": "run-1"}
        self.eval_tool = tool
        code, printed, _err = self.run_proof(flow=[f"update notice={lua}"])
        self.assertEqual(code, 0)
        self.assertEqual([path.name for path in self.shot_paths], ["1-update-notice.png"])
        self.assertIn("DevSmokeDB.eval: ok, ran 7\nshown", printed)
        self.assertEqual(
            self.reload.call_count, 3, "the proof's own, the flow's, and the one that saves the eval to disk"
        )

    def test_a_lua_flow_step_is_its_file_name_and_digest_not_the_callers_path(self):
        lua = self.state / "flows/westfall-map.lua"
        lua.parent.mkdir(parents=True)
        lua.write_text("print('map')\n")
        self.saved_eval({"run": "run-1", "ran": 7, "ok": True, "out": {1: "map"}})
        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_snippet.return_value = {"chunk": Path("/x/Eval.lua"), "snippet": lua, "lines": 1, "token": "run-1"}
        self.eval_tool = tool
        code, _printed, _err = self.run_proof(flow=[f"map={lua}"])
        self.assertEqual(code, 0)
        digest = fc.hashlib.sha256(lua.read_bytes()).hexdigest()
        target = self.checkout / ".visual-proof.json"
        proof = json.loads(target.read_text())
        self.assertEqual(
            proof["flows"],
            [{"name": "map", "steps": [f"sha256:{digest} westfall-map.lua"], "result": "pass"}],
        )
        self.assertNotIn(str(lua), target.read_text(), "the caller's scratch path is not in the public proof")

    def test_a_proof_clears_the_eval_inbox_when_it_starts_and_ends(self):
        with mock.patch.object(fc, "clear_eval_inbox") as clear:
            code, _printed, _err = self.run_proof()
        self.assertEqual(code, 0)
        self.assertEqual(clear.call_args_list[0], mock.call(), "the proof starts from an empty inbox")
        self.assertEqual(clear.call_args_list[-1], mock.call(quiet=True), "and clears it again when it ends")
        self.assertEqual(clear.call_args_list.count(mock.call()), 2, "the flow's own reload also clears its inbox")

    def test_a_lua_flow_that_raised_fails_the_proof_instead_of_passing_on_an_earlier_eval(self):
        # The reader used to answer with whatever eval the SavedVariables file held, which is the session before this
        # one: a snippet that raised passed on an earlier run's success, and the gist went out with it (#580).
        lua = self.state / "hover.lua"
        lua.write_text("error('boom')\n")
        self.saved_eval({"run": "earlier", "ran": 1, "ok": True, "out": {1: "an earlier run's output"}})
        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_snippet.return_value = {"chunk": Path("/x/Eval.lua"), "snippet": lua, "lines": 1, "token": "run-1"}
        self.eval_tool = tool
        with self.assertRaisesRegex(fc.ClientError, "holds the run 'earlier', not this snippet's 'run-1'"):
            self.run_proof(flow=[f"hover a quest stop={lua}"])
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())

    def test_a_lua_flow_failed_by_its_own_error_fails_the_proof(self):
        lua = self.state / "hover.lua"
        lua.write_text("error('boom')\n")
        self.saved_eval({"run": "run-1", "ran": 9, "ok": False, "err": "Eval.lua:2: boom\nstack", "out": {1: "before"}})
        tool = mock.Mock()
        tool.EvalError = Exception
        tool.write_snippet.return_value = {"chunk": Path("/x/Eval.lua"), "snippet": lua, "lines": 1, "token": "run-1"}
        self.eval_tool = tool
        with self.assertRaises(fc.ClientError) as failure:
            self.run_proof(flow=[f"hover a quest stop={lua}"])
        self.assertIn(f"flow snippet {lua} failed", str(failure.exception))
        self.assertIn("Eval.lua:2: boom", str(failure.exception), "the proof fails on the snippet's own error")
        self.create_gist.assert_not_called()
        self.assertFalse((self.checkout / ".visual-proof.json").exists())

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
                    "--flow-click",
                    "update notice=400,300",
                    "--manual-launcher",
                ]
            )
        self.assertEqual(code, 3)
        options = proof.call_args.args[0]
        self.assertEqual(options.repo, "legacy-forever")
        self.assertEqual(options.checkout, self.checkout)
        self.assertEqual(options.flow, ["update notice=/lf"])
        self.assertEqual(options.flow_click, ["update notice=400,300"])
        self.assertTrue(options.manual_launcher)


class BrokerTest(unittest.TestCase):
    """The resident session and the short job lock: one client, several agents, no login per test."""

    def setUp(self):
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.enterContext(mock.patch.object(fc, "require_safe"))
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))

    def holder(self, token="held", label="smoke legacy-forever", pid=None, start_ticks=None):
        """A job.json naming a live holder, as a job or a lease writes it."""
        fc.write_job_record(
            {
                "pid": pid if pid is not None else os.getpid(),
                "start_ticks": start_ticks if start_ticks is not None else fc.process_start(os.getpid()),
                "token": token,
                "label": label,
                "started": time.time(),
            }
        )

    def test_queued_job_yields_to_pending_reload(self):
        state = live_state(ready=1, reloading=True)
        fc.state_file().write_text(json.dumps(state))
        observed = []

        def finish_reload(_seconds):
            # A waiter must release the flock before sleeping, so serve can take it for teardown.
            with open(fc.job_lock_path(), "a+") as other:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            observed.append("reload")
            fc.state_file().unlink()

        with mock.patch.object(fc.time, "sleep", side_effect=finish_reload):
            handle, token = fc.acquire_job(5, "queued")
        try:
            self.assertEqual(observed, ["reload"])
        finally:
            fc.release_job(handle, token)

    def test_launcher_sources_detects_content_changes_and_removed_imports(self):
        dependency = self.state / "helper.py"
        unrelated = self.state / "unloaded.py"
        dependency.write_text("before")
        unrelated.write_text("unloaded")
        # __file__ determines the repository root, two parents above the launcher.
        launcher = self.state / "tools/headless/launcher.py"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("launcher")
        module = mock.Mock(__file__=str(dependency))
        with mock.patch.object(fc, "__file__", str(launcher)), mock.patch.dict(sys.modules, helper=module):
            baseline = fc.launcher_sources()
            self.assertIn(dependency, baseline)
            with mock.patch.dict(sys.modules, later=mock.Mock(__file__=str(unrelated))):
                self.assertEqual(fc.launcher_sources(baseline), baseline)
            unrelated.write_text("changed")
            os.utime(dependency, (1, 1))
            self.assertEqual(fc.launcher_sources(), baseline)
            dependency.write_text("after!")
            os.utime(dependency, (1, 1))
            self.assertNotEqual(fc.launcher_sources(), baseline)
            dependency.write_text("before")
            self.assertEqual(fc.launcher_sources(), baseline)
            launcher.write_text("new launcher")
            self.assertNotEqual(fc.launcher_sources(), baseline)
            launcher.write_text("launcher")
            dependency.unlink()
            self.assertIsNone(fc.launcher_sources()[dependency])
            self.assertNotEqual(fc.launcher_sources(), baseline)

    def test_the_session_ends_after_the_idle_limit_or_at_the_lifetime_cap(self):
        self.assertIsNone(fc.session_end_reason(100, 0, 50, 95))
        self.assertIn(f"{fc.IDLE_LIMIT // 60} min", fc.session_end_reason(fc.IDLE_LIMIT + 50, 0, 50, 50))
        self.assertIn("lifetime cap", fc.session_end_reason(fc.MAX_SESSION, 0, 0, fc.MAX_SESSION - 1))
        # The lifetime cap wins when both limits are due, so the session never outlives it.
        self.assertIn("lifetime cap", fc.session_end_reason(fc.MAX_SESSION, 0, 0, 0))

    def test_a_mark_from_an_earlier_session_starts_the_idle_limit_at_ready(self):
        stale = self.state / "last-job"
        stale.touch()
        os.utime(stale, (0, 0))
        clock = FakeClock()
        clock.now = 1000.0
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "time", return_value=10_000.0),
        ):
            self.assertEqual(fc.last_job_mark(ready=900.0), 900.0)

    def test_the_lifetime_cap_waits_for_a_running_job_before_teardown(self):
        self.check_session_end_waits_for_job(stale=False)

    def test_stale_source_waits_for_a_running_job_before_teardown(self):
        self.check_session_end_waits_for_job(stale=True)

    def check_session_end_waits_for_job(self, *, stale):
        self.enterContext(mock.patch.object(fc, "LAUNCHER_SOURCES", {}))
        config = self.state / "env.json"
        config.write_text(
            '{"umu_run":"/faugus/umu-run",'
            '"env":{"PROTONPATH":"/runner"},'
            '"character":{"name":"Parked","guid":"1","require_resting":true}}'
        )
        client = self.state / "client"
        (client / "Interface/AddOns").mkdir(parents=True)
        clock = FakeClock()
        order = []

        def acquire(timeout, _label, *, session_end=False):
            self.assertIsNone(timeout, "the end waits for the job in flight, never on a timeout")
            clock.sleep(5)  # the job in flight runs on for five seconds
            self.assertTrue(session_end)
            self.assertEqual(fc.load_state().get("reloading", False), stale)
            order.append("job-finished")
            return mock.Mock(), "session-end"

        def teardown(*_args):
            order.append("teardown")

        self.enterContext(mock.patch.object(fc, "client_ui", return_value={"world": True, "safety": True}))
        gamescope = mock.Mock(pid=123)
        gamescope.poll.return_value = None
        with (
            mock.patch.object(fc, "CONFIG", config),
            mock.patch.object(fc, "CLIENT", client),
            mock.patch.object(fc, "nvidia_mismatch", return_value=None),
            mock.patch.object(fc, "prefix_users", return_value=[]),
            mock.patch.object(fc.socket, "create_connection"),
            mock.patch.object(fc.signal, "signal"),
            mock.patch.object(fc, "runtime_dir", return_value=self.state / "runtime"),
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "child_env", return_value={"DISPLAY": ":3", "GAMESCOPE_WAYLAND_DISPLAY": "private"}),
            mock.patch.object(fc, "wait_for_world", return_value=Path("ready.png")),
            mock.patch.object(fc, "teardown", side_effect=teardown),
            mock.patch.object(fc, "acquire_job", side_effect=acquire),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "MAX_SESSION", 10**9 if stale else 10),
            mock.patch.object(
                fc, "launcher_sources", side_effect=lambda _paths: {"changed": "digest"} if stale and clock.now else {}
            ),
            mock.patch.object(fc, "IDLE_LIMIT", 10**9),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            mock.patch.object(fc.time, "time", return_value=1000.0),
            mock.patch.object(fc.subprocess, "Popen", return_value=gamescope),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.up(args()), 0)
        self.assertEqual(order, ["job-finished", "teardown"])

    def test_a_job_starts_a_session_when_none_runs_and_reuses_a_ready_one(self):
        clock = FakeClock()
        child = mock.Mock(pid=999)
        child.poll.return_value = None
        ready = live_state(ready=1.0, display=":3", runtime_dir="/run/user/1")
        with (
            mock.patch.object(fc, "session_lock_held", return_value=False),
            mock.patch.object(fc, "start_serve", return_value=child) as start,
            mock.patch.object(fc, "current_session", side_effect=[None, None, ready]),
            mock.patch.object(fc, "client_ui", return_value={"world": True, "safety": True}),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(fc.ensure_session(60), ready)
        start.assert_called_once_with(False)
        self.assertGreater(clock.now, 0)

        with (
            mock.patch.object(fc, "start_serve") as start,
            mock.patch.object(fc, "current_session", return_value=ready),
            mock.patch.object(fc, "client_ui", return_value={"world": True, "safety": True}),
        ):
            self.assertEqual(fc.ensure_session(60), ready)
        start.assert_not_called()

    def test_a_completed_reload_restores_ready_before_reuse(self):
        state = live_state(world_lost=True)
        with (
            mock.patch.object(fc, "current_session", return_value=state),
            mock.patch.object(fc, "client_ui", return_value={"world": True, "safety": True}),
            mock.patch.object(fc, "write_state") as write,
        ):
            self.assertTrue(fc.ensure_session(60)["ready"])
        self.assertNotIn("world_lost", write.call_args.args[0])

    def test_an_empty_job_record_does_not_block_a_job(self):
        fc.job_record_path().write_text("")
        handle, token = fc.acquire_job(0, "after reboot")
        try:
            self.assertEqual(fc.job_holder()["token"], token)
        finally:
            fc.release_job(handle, token)

    def test_ready_session_outside_world_is_stopped_and_replaced(self):
        stale = live_state(ready=1.0)
        fresh = live_state(ready=2.0)
        with (
            mock.patch.object(fc, "current_session", side_effect=[stale, None, fresh]),
            mock.patch.object(fc, "client_ui", side_effect=[{"world": False}, {"world": True, "safety": True}]),
            mock.patch.object(fc, "job_holder", return_value={"pid": os.getpid()}),
            mock.patch.object(fc, "write_state") as write,
            mock.patch.object(fc, "down") as down,
            mock.patch.object(fc, "session_lock_held", return_value=False),
            mock.patch.object(fc, "start_serve", return_value=mock.Mock(poll=lambda: None)) as start,
            mock.patch.object(fc.time, "sleep"),
        ):
            self.assertEqual(fc.ensure_session(60), fresh)
        down.assert_called_once()
        start.assert_called_once()
        self.assertNotIn("ready", write.call_args.args[0])

    def test_out_of_world_session_cannot_stop_another_jobs_client(self):
        with (
            mock.patch.object(fc, "current_session", return_value=live_state(ready=1.0)),
            mock.patch.object(fc, "client_ui", return_value={"world": False}),
            mock.patch.object(fc, "job_holder", return_value={"pid": -1, "token": "foreign"}),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(fc, "down") as down,
        ):
            with self.assertRaisesRegex(fc.ClientError, "another job"):
                fc.ensure_session(60)
        down.assert_not_called()

    def test_a_job_runs_its_command_with_the_token_and_releases_the_lock(self):
        state = live_state(ready=1.0, display=":3", runtime_dir="/run/user/1")
        with (
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "ensure_session", return_value=state),
            mock.patch.object(fc, "recover_links"),
            mock.patch.object(fc, "release_job") as released,
            mock.patch.object(
                fc.subprocess, "Popen", return_value=mock.Mock(pid=123, wait=mock.Mock(return_value=7))
            ) as run,
            mock.patch.object(fc.os, "killpg"),
        ):
            code = fc.job(argparse.Namespace(command=["--", "probe.sh"], label=None, timeout=5, manual_launcher=False))
        self.assertEqual(code, 7)
        self.assertEqual(run.call_args.args[0], ["probe.sh"])
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["FOREVER_CLIENT_CALLER"], "in-game")
        self.assertEqual(env["FOREVER_CLIENT_JOB"], "job-token")
        self.assertEqual(env["FOREVER_CLIENT_DISPLAY"], ":3")
        released.assert_called_once_with(mock.ANY, "job-token")

    def test_a_job_waits_for_the_lock_and_names_the_holder_once(self):
        self.holder(label="smoke legacy-forever")
        clock = FakeClock()
        out = io.StringIO()
        calls = {"count": 0}

        def flock(_handle, _operation):
            if Path(_handle.name).name != "job.lock":
                if _operation == fcntl.LOCK_SH | fcntl.LOCK_NB:
                    raise BlockingIOError
                return
            calls["count"] += 1
            if calls["count"] == 1:
                raise BlockingIOError

        with (
            mock.patch.object(fc.fcntl, "flock", side_effect=flock),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            contextlib.redirect_stderr(out),
        ):
            handle, token = fc.acquire_job(60, "shot")
            try:
                self.assertEqual(out.getvalue().count("waiting for"), 1)
                self.assertIn("smoke legacy-forever", out.getvalue())
                record = json.loads(fc.job_record_path().read_text())
                self.assertEqual((record["token"], record["label"]), (token, "shot"))
            finally:
                fc.release_job(handle, token)
        self.assertFalse(fc.job_record_path().exists())
        self.assertTrue((self.state / "last-job").exists())

    def test_a_job_that_waits_out_its_timeout_names_the_holder(self):
        holder = open(self.state / "job.lock", "w")
        self.addCleanup(holder.close)
        fcntl.flock(holder, fcntl.LOCK_EX)
        self.holder()
        clock = FakeClock()
        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaisesRegex(fc.ClientError, "after waiting 5 s.*smoke legacy-forever"),
        ):
            fc.acquire_job(5, "shot")

    def test_a_dead_job_json_owner_is_treated_as_free(self):
        fc.write_job_record({"pid": dead_pid(), "start_ticks": 1, "token": "old", "label": "a dead job", "started": 0})
        self.assertIsNone(fc.job_holder())
        self.assertEqual(fc.describe_job(), "another job")
        with (
            mock.patch.dict(os.environ, {"FOREVER_CLIENT_JOB": "old"}),
            self.assertRaisesRegex(fc.ClientError, "lease ended: unknown token"),
        ):
            fc.with_job("shot", 5, mock.Mock())

    def test_a_job_token_proceeds_without_taking_the_lock(self):
        self.holder(token="job-token")
        with (
            mock.patch.dict(os.environ, {"FOREVER_CLIENT_JOB": "job-token"}),
            mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
            mock.patch.object(fc, "acquire_job") as acquire,
        ):
            self.assertEqual(fc.with_job("shot", 0, lambda _state: 0), 0)
        acquire.assert_not_called()

    def test_a_scroll_without_a_token_takes_the_job_lock(self):
        """A wheel verb run on its own is a job: job.lock is held, and job.json names it, for that invocation."""
        state = live_state(ready=1.0)
        seen = {}

        def scroll(_state, _x, _y, ticks):
            handle = open(fc.job_lock_path(), "w")
            try:
                with self.assertRaises(
                    BlockingIOError, msg="the scroll holds the job lock while it touches the client"
                ):
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                handle.close()
            seen.update(json.loads(fc.job_record_path().read_text()))
            seen["ticks"] = ticks

        with (
            mock.patch.dict(os.environ, {"FOREVER_CLIENT_JOB": ""}),
            mock.patch.object(fc, "load_state", return_value=state),
            mock.patch.object(fc, "scroll", side_effect=scroll) as scroll_verb,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.main(["scroll", "960", "540", "-4"]), 0)
        scroll_verb.assert_called_once_with(state, 960, 540, -4)
        self.assertEqual((seen["pid"], seen["label"]), (os.getpid(), "scroll"))
        self.assertEqual(seen["ticks"], -4)
        self.assertFalse(fc.job_record_path().exists(), "the lock is the invocation's, not the session's")
        self.assertTrue((self.state / "last-job").exists(), "the job's end is recorded for the idle limit")

    def make_lease(self, ttl=600):
        out = io.StringIO()
        fc.write_state(live_state(ready=1.0))
        with (
            mock.patch.object(fc, "ensure_session", return_value=live_state(ready=1.0)),
            contextlib.redirect_stdout(out),
        ):
            fc.lease(argparse.Namespace(ttl=ttl, timeout=0, manual_launcher=False, label="interactive"))
        return out.getvalue().strip()

    def test_a_lease_leaves_the_job_lock_free(self):
        token = self.make_lease()
        record = json.loads((self.state / "leases" / f"{token}.json").read_text())
        self.assertEqual(record["label"], "interactive")
        handle, own = fc.acquire_job(0, "another agent")
        fc.release_job(handle, own)

    def test_a_lease_verb_holds_and_releases_its_own_lock(self):
        token = self.make_lease()

        def action(_state):
            self.assertEqual(fc.job_holder()["label"], "interactive: shot")
            with self.assertRaises(fc.ClientError):
                fc.acquire_job(0, "another agent")
            return 7

        with (
            mock.patch.dict(os.environ, {"FOREVER_CLIENT_JOB": token}),
            mock.patch.object(fc, "load_state", return_value=live_state(ready=1.0)),
        ):
            self.assertEqual(fc.with_job("shot", 0, action), 7)
        handle, own = fc.acquire_job(0, "another agent")
        fc.release_job(handle, own)

    def test_an_expired_lease_errors(self):
        token = self.make_lease()
        with (
            mock.patch.dict(os.environ, {"FOREVER_CLIENT_JOB": token}),
            mock.patch.object(fc.time, "time", return_value=time.time() + 601),
            self.assertRaisesRegex(fc.ClientError, "lease expired: run lease again"),
        ):
            fc.with_job("shot", 0, mock.Mock())

    def test_a_job_limit_kills_the_command_and_frees_the_lock(self):
        with (
            mock.patch.object(fc, "ensure_session", return_value=live_state(display=":3", runtime_dir="/run/user/1")),
            mock.patch.object(fc, "recover_links"),
            self.assertRaisesRegex(fc.ClientError, "0.1 s"),
        ):
            fc.job(
                argparse.Namespace(
                    command=[sys.executable, "-c", "import time; time.sleep(30)"],
                    label=None,
                    timeout=0,
                    manual_launcher=False,
                    max=0.1,
                )
            )
        handle, own = fc.acquire_job(0, "another agent")
        fc.release_job(handle, own)

    def test_down_inside_a_job_requests_stop_without_waiting(self):
        self.holder(token="own")
        with (
            mock.patch.dict(os.environ, {"FOREVER_CLIENT_JOB": "own"}),
            mock.patch.object(fc, "load_state", side_effect=AssertionError("must not wait")),
        ):
            self.assertEqual(fc.down(), 0)
        self.assertTrue((self.state / fc.STOP).exists())

    def test_release_leaves_a_reason_for_the_lease_holder(self):
        token = self.make_lease()
        self.assertEqual(fc.release(token), 0)
        with self.assertRaisesRegex(fc.ClientError, "released by caller"):
            fc.live_lease(token)

    def test_a_job_timeout_escalates_to_kill(self):
        clock = FakeClock()
        process = mock.Mock(pid=123)
        process.wait.side_effect = [
            subprocess.TimeoutExpired("probe", 1),
            -signal.SIGKILL,
        ]
        with (
            mock.patch.object(fc, "ensure_session", return_value=live_state(display=":3", runtime_dir="/run/user/1")),
            mock.patch.object(fc, "recover_links"),
            mock.patch.object(fc.subprocess, "Popen", return_value=process) as spawn,
            mock.patch.object(fc.os, "killpg") as kill,
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
            self.assertRaisesRegex(fc.ClientError, "1 s limit"),
        ):
            fc.job(argparse.Namespace(command=["probe"], label=None, timeout=0, manual_launcher=False, max=1))
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        self.assertEqual(
            [call for call in kill.call_args_list if call.args[1] != 0],
            [
                mock.call(123, signal.SIGTERM),
                mock.call(123, signal.SIGKILL),
            ],
        )
        handle, own = fc.acquire_job(0, "another agent")
        fc.release_job(handle, own)

    def test_waiting_for_a_session_reports_its_deadlines_and_reuse(self):
        for holder, expected in (
            (None, "session pid 42"),
            ({"pid": 73, "label": "smoke legacy-forever", "token": "abc"}, "smoke legacy-forever (pid 73"),
        ):
            with (
                self.subTest(holder=holder),
                mock.patch.object(fc, "recover_links"),
                mock.patch.object(fc, "current_session", return_value={"pid": 42, "started": 100, "ready": 200}),
                mock.patch.object(fc, "job_holder", return_value=holder),
                mock.patch.object(fc.time, "time", return_value=300),
                mock.patch.object(fc, "wait_for_session", side_effect=fc.ClientError("stop test")),
                contextlib.redirect_stderr(io.StringIO()) as out,
                self.assertRaisesRegex(fc.ClientError, "stop test"),
            ):
                fc.serve(argparse.Namespace(wait=True, timeout=0))
            self.assertIn(expected, out.getvalue())
            self.assertIn("latest end 1970-01-01T03:01:40Z (177 min remaining)", out.getvalue())
            self.assertIn("idle end 1970-01-01T00:13:20Z (8 min remaining)", out.getvalue())
            self.assertIn("job/lease run inside the resident session now without --wait", out.getvalue())

    def test_exited_job_leader_gives_its_child_time_to_handle_term(self):
        completed = self.state / "child-finished"
        ready = self.state / "child-ready"
        child_code = (
            "import signal, time; from pathlib import Path; "
            f"signal.signal(signal.SIGTERM, lambda *_: (time.sleep(0.2), Path({str(completed)!r}).touch(), exit(0))); "
            f"Path({str(ready)!r}).touch(); time.sleep(30)"
        )
        leader_code = (
            "import subprocess, sys, time; from pathlib import Path; "
            f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
            f"ready = Path({str(ready)!r}); "
            "exec('while not ready.exists(): time.sleep(0.01)')"
        )
        with (
            mock.patch.object(fc, "ensure_session", return_value=live_state(display=":3", runtime_dir="/run/user/1")),
            mock.patch.object(fc, "recover_links"),
        ):
            result = fc.job(
                argparse.Namespace(
                    command=[sys.executable, "-c", leader_code],
                    label=None,
                    timeout=0,
                    manual_launcher=False,
                    max=5,
                )
            )
        self.assertEqual(result, 0)
        self.assertTrue(completed.exists(), "the child must finish its TERM handler before SIGKILL")

    def test_teardown_clears_lease_records(self):
        token = self.make_lease()
        clock = FakeClock()
        with (
            mock.patch.object(fc, "require_owned_prefix"),
            mock.patch.object(fc, "stop_gamescope"),
            mock.patch.object(fc, "prefix_snapshot", return_value={}),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", clock.sleep),
        ):
            fc.teardown(None, {}, None, {})
        with self.assertRaisesRegex(fc.ClientError, "session ended because"):
            fc.live_lease(token)

    def test_a_lease_ttl_is_capped(self):
        options = argparse.Namespace(ttl=fc.LEASE_MAX + 1, timeout=5, manual_launcher=False, label=None)
        with self.assertRaisesRegex(fc.ClientError, f"1 to {fc.LEASE_MAX}"):
            fc.lease(options)

    def test_release_ends_only_the_lease_that_owns_the_token(self):
        self.holder(token="lease-token", label="a lease")
        with self.assertRaisesRegex(fc.ClientError, "unknown lease"):
            fc.release("another-token")

    def test_release_refuses_a_job_that_is_not_a_lease(self):
        self.holder(token="job-token", label="smoke legacy-forever")
        with self.assertRaisesRegex(fc.ClientError, "unknown lease"):
            fc.release("job-token")

    def test_a_resident_sessions_processes_are_not_a_busy_client(self):
        state = live_state(token="session-token")
        processes = {42: {"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": "session-token"}}
        with (
            mock.patch.object(fc, "prefix_snapshot", return_value=processes),
            mock.patch.object(fc, "current_session", return_value=state),
            mock.patch.object(fc, "client_pid", return_value=42),
        ):
            self.assertIsNone(fc.foreign_client())

    def test_the_players_client_is_the_only_busy_reason(self):
        processes = {42: {"WINEPREFIX": str(fc.PREFIX)}}
        with (
            mock.patch.object(fc, "prefix_snapshot", return_value=processes),
            mock.patch.object(fc, "current_session", return_value=None),
            mock.patch.object(fc, "client_pid", return_value=42),
            mock.patch.object(fc, "read_environ", return_value={"WINEPREFIX": str(fc.PREFIX)}),
        ):
            self.assertIn("player's client is running", fc.foreign_client())

    def test_a_headless_clients_wow_exe_beside_a_dead_sessions_leftovers_is_not_the_players(self):
        # #652: the other session's Wow.exe carried its token, the leftovers did not, and the proof blamed the player.
        processes = {
            42: {"WINEPREFIX": str(fc.PREFIX), "FOREVER_CLIENT_SESSION": "session-token"},
            43: {"WINEPREFIX": str(fc.PREFIX)},
        }
        with (
            mock.patch.object(fc, "prefix_snapshot", return_value=processes),
            mock.patch.object(fc, "current_session", return_value=live_state(token="session-token")),
            mock.patch.object(fc, "client_pid", return_value=42),
            mock.patch.object(fc, "read_environ", side_effect=lambda pid: processes[pid]),
        ):
            self.assertEqual(fc.foreign_client(), "a headless session holds the client (Wow.exe, pid 42)")

    def test_down_asks_the_session_to_stop_after_the_job_in_flight(self):
        fc.state_file().write_text(json.dumps(live_state(ready=1.0)))
        clock = FakeClock()
        seen = {}

        def tick(seconds):
            clock.sleep(seconds)
            seen["stop"] = (self.state / "stop").exists()
            fc.state_file().unlink(missing_ok=True)

        with (
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", side_effect=tick),
        ):
            self.assertEqual(fc.down(), 0)
        self.assertTrue(seen["stop"])
        self.assertFalse((self.state / "stop").exists())

    def test_down_stops_a_session_that_is_still_starting(self):
        state = live_state()
        fc.state_file().write_text(json.dumps(state))
        clock = FakeClock()

        def tick(seconds):
            clock.sleep(seconds)
            fc.state_file().unlink(missing_ok=True)

        with (
            # The signal goes through the pidfd binding down uses, so a pid another process now owns is never hit.
            mock.patch.object(fc, "signal_pid", return_value=True) as stop,
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", side_effect=tick),
        ):
            self.assertEqual(fc.down(), 0)
        stop.assert_called_once_with(state["pid"], state["start_ticks"], signal.SIGTERM)
        self.assertFalse((self.state / "stop").exists(), "a starting session has no resident loop to read the marker")


class HyprlandJobTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.state))
        # These cover the queue and the return; LiveSafetyTest covers the Hyprland job's refusal.
        self.enterContext(mock.patch.object(fc, "require_safe"))

    def request(self, **extra) -> dict:
        return {
            "token": "job-token",
            "pid": os.getpid(),
            "start_ticks": fc.process_start(os.getpid()),
            "maximum": 2,
            "command": ["probe"],
            "environ": {},
            "label": "deskpilot#95",
            "parent": "parent-signature",
            **extra,
        }

    def test_an_absolute_point_gets_the_xwayland_offset_of_the_nested_output(self):
        with mock.patch.object(fc.subprocess, "run") as run:
            fc.x({"display": ":3", "origin": [1280, 0]}, "mousemove", "10", "20", "click", "1")
            fc.x({"display": ":2"}, "mousemove", "10", "20")
        self.assertEqual(run.call_args_list[0].args[0], ["xdotool", "mousemove", "1290", "20", "click", "1"])
        self.assertEqual(run.call_args_list[1].args[0], ["xdotool", "mousemove", "10", "20"])

    def nested(self, *, start_error=None):
        module = mock.Mock()
        module.NestedError = type("NestedError", (Exception,), {})
        record = {
            "signature": "nested-sig",
            "wayland": "wayland-9",
            "display": ":7",
            "origin": [1280, 0],
            "output": "FOREVER",
            "pid": 1,
            "birth": "1",
            "run": "/nowhere",
        }
        if start_error:
            module.start.side_effect = module.NestedError(start_error)
        else:
            module.start.return_value = record
        module.running.return_value = True
        module.window.return_value = {"address": "0xabc", "title": fc.GAME_WINDOW}
        return module

    def serve_with(self, hyprland_job):
        """Run serve with one Hyprland request waiting; returns the order of lock and job steps."""
        config = self.state / "env.json"
        config.write_text(
            '{"umu_run":"/faugus/umu-run","env":{"PROTONPATH":"/runner"},'
            '"character":{"name":"Parked","guid":"1","require_resting":true}}'
        )
        client = self.state / "client"
        (client / "Interface/AddOns").mkdir(parents=True)
        fc.atomic_write(self.state / fc.HYPRLAND_REQUEST, json.dumps(self.request()))
        clock = FakeClock()
        order = []

        def acquire(timeout, label, **_kwargs):
            self.assertIsNone(timeout)
            order.append(("acquire", label))
            return mock.Mock(), "own-token"

        def release(_handle, token, ended=True):
            order.append(("release", token, fc.read_job_record()))

        def lease(*args):
            order.append(("job", fc.read_job_record()["token"], True))
            (self.state / fc.HYPRLAND_REQUEST).unlink()
            return hyprland_job(*args)

        gamescope = mock.Mock(pid=123)
        gamescope.poll.return_value = None
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(fc, "CONFIG", config))
            stack.enter_context(mock.patch.object(fc, "CLIENT", client))
            stack.enter_context(mock.patch.object(fc, "nvidia_mismatch", return_value=None))
            stack.enter_context(mock.patch.object(fc, "prefix_users", return_value=[]))
            stack.enter_context(mock.patch.object(fc.socket, "create_connection"))
            stack.enter_context(mock.patch.object(fc.signal, "signal"))
            stack.enter_context(mock.patch.object(fc, "runtime_dir", return_value=self.state / "runtime"))
            stack.enter_context(mock.patch.object(fc, "screenshots", return_value=set()))
            stack.enter_context(
                mock.patch.object(
                    fc, "child_env", return_value={"DISPLAY": ":3", "GAMESCOPE_WAYLAND_DISPLAY": "private"}
                )
            )
            stack.enter_context(mock.patch.object(fc, "wait_for_world", return_value=Path("ready.png")))
            stack.enter_context(mock.patch.object(fc, "teardown", side_effect=lambda *a: order.append("teardown")))
            stack.enter_context(mock.patch.object(fc, "acquire_job", side_effect=acquire))
            stack.enter_context(mock.patch.object(fc, "release_job", side_effect=release))
            stack.enter_context(mock.patch.object(fc, "hyprland_job", side_effect=lease))
            stack.enter_context(mock.patch.object(fc, "client_ui", return_value={"world": True}))
            stack.enter_context(mock.patch.object(fc, "MAX_SESSION", 10))
            stack.enter_context(mock.patch.object(fc, "IDLE_LIMIT", 10**9))
            stack.enter_context(mock.patch.object(fc.time, "monotonic", clock.monotonic))
            stack.enter_context(mock.patch.object(fc.time, "sleep", clock.sleep))
            stack.enter_context(mock.patch.object(fc.time, "time", return_value=1000.0))
            stack.enter_context(mock.patch.object(fc.subprocess, "Popen", return_value=gamescope))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            try:
                result = fc.up(args())
            except fc.ClientError as error:
                result = error
        return result, order

    def test_a_failed_return_ends_the_session_so_the_next_job_starts_fresh(self):
        def failed(*_args):
            raise fc.ClientError("the world did not load within 600 s")

        result, order = self.serve_with(failed)
        self.assertIsInstance(result, fc.ClientError)
        self.assertEqual(order[-2:], ["teardown", ("release", "job-token", order[-1][2])])
        self.assertFalse(fc.session_lock_held(), "serve released the session lock, so a job can start a new one")

    def run_hyprland(self, failure=None, return_failure=False, cancelled=False, crashed=False, start_error=None):
        module = self.nested(start_error=start_error)
        state = live_state(mode="gamescope", display=":2", ready=1, token="session", runtime_dir="/run/user/1")
        order = []
        client = mock.Mock(pid=555, poll=mock.Mock(return_value=None))
        returned = mock.Mock(pid=777)

        def end(_display, _wine, state):
            order.append(("end", state["mode"]))
            fc.stop_nested(state)

        def launch(*_args):
            order.append("gamescope")
            if return_failure:
                raise fc.ClientError("return failed")
            state.update(mode="gamescope", display=":2")
            return returned

        def run(command, env, maximum, check):
            order.append("command")
            self.assertEqual(command, ["probe"])
            self.assertEqual(maximum, 2)
            self.assertEqual(env["FOREVER_CLIENT_JOB"], "job-token")
            self.assertEqual(env["HYPRLAND_INSTANCE_SIGNATURE"], "nested-sig")
            self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-9")
            self.assertEqual(env["DISPLAY"], ":7")
            self.assertEqual(env["FOREVER_CLIENT_WINDOW"], "0xabc")
            if cancelled:
                (self.state / fc.HYPRLAND_END).write_text("job-token")
            if crashed:
                module.running.return_value = False
            check()
            if failure:
                raise failure
            return 7

        with (
            mock.patch.object(fc, "nested_hyprland", return_value=module),
            mock.patch.object(fc, "end_client", side_effect=end),
            mock.patch.object(fc, "launch_gamescope", side_effect=launch),
            mock.patch.object(fc, "reach_world", side_effect=lambda *a, **kw: order.append(("world", a[0]["mode"]))),
            mock.patch.object(fc, "screenshots", return_value=set()),
            mock.patch.object(fc, "recover_links"),
            mock.patch.object(fc, "run_job_command", side_effect=run),
            mock.patch.object(fc.subprocess, "Popen", return_value=client),
        ):
            try:
                result = fc.hyprland_job(self.request(), mock.Mock(), {}, {}, {"umu_run": "umu"}, None, state)
            except KeyboardInterrupt:
                self.assertNotIn("gamescope", order)
                self.assertEqual(order.count(("world", "hyprland")), 1)
                raise
        self.assertIs(result, returned)
        self.assertEqual(
            order,
            [
                ("end", "gamescope"),
                *([] if start_error else [("world", "hyprland"), "command"]),
                ("end", "hyprland"),
                "gamescope",
                ("world", "gamescope"),
            ],
        )
        if start_error:
            module.stop.assert_not_called()
        else:
            module.stop.assert_called_once()
        self.assertNotIn("origin", state)
        return fc.read_hyprland_json(f"{fc.HYPRLAND_RESULT}-job-token.json")

    def test_command_runs_with_nested_environment_and_returns_before_result(self):
        self.assertEqual(self.run_hyprland()["code"], 7)

    def test_timeout_cancel_and_nested_crash_all_return(self):
        for options, message in [
            ({"failure": fc.ClientError("job exceeded its 2 s limit")}, "exceeded"),
            ({"cancelled": True}, "cancelled"),
            ({"crashed": True}, "exited"),
        ]:
            with self.subTest(options=options):
                (self.state / fc.HYPRLAND_END).unlink(missing_ok=True)
                self.assertIn(message, self.run_hyprland(**options)["error"])

    def test_failed_nested_start_returns_and_reports_the_error(self):
        self.assertIn("no XWayland", self.run_hyprland(start_error="no XWayland")["error"])

    def test_failed_return_does_not_publish_completion(self):
        with self.assertRaisesRegex(fc.ClientError, "return failed"):
            self.run_hyprland(return_failure=True)
        self.assertIsNone(fc.read_hyprland_json(f"{fc.HYPRLAND_RESULT}-job-token.json"))

    def test_hyprland_is_a_job_option_and_lease_rejects_it(self):
        with mock.patch.object(fc, "job", return_value=0) as job:
            self.assertEqual(fc.main(["job", "--hyprland", "--max", "20", "--", "probe"]), 0)
        self.assertTrue(job.call_args.args[0].hyprland)
        self.assertEqual(job.call_args.args[0].max, 20)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            fc.main(["lease", "--hyprland"])

    def test_dead_request_is_not_run(self):
        fc.atomic_write(self.state / fc.HYPRLAND_REQUEST, json.dumps(self.request(pid=-1)))
        self.assertIsNone(fc.hyprland_request())

    def test_nested_screenshot_uses_grim_on_its_output(self):
        state = {"mode": "hyprland", "runtime_dir": str(self.state), "nested": self.nested().start.return_value}
        with (
            mock.patch.object(fc.subprocess, "run") as run,
            mock.patch.object(fc, "_complete_png", return_value=True),
            mock.patch.object(fc, "mark"),
        ):
            fc.shot(state, self.state / "frame.png")
        self.assertEqual(run.call_args.args[0][:3], ["grim", "-o", "FOREVER"])
        self.assertEqual(run.call_args.kwargs["env"]["WAYLAND_DISPLAY"], "wayland-9")

    def test_requester_cancellation_waits_until_return_result(self):
        module = self.nested()
        module.user_instance.return_value = "parent-signature"
        clock = FakeClock()
        ticks = []

        def tick(seconds):
            ticks.append(seconds)
            request = fc.hyprland_request()
            if len(ticks) == 1:
                raise KeyboardInterrupt
            self.assertTrue(fc.hyprland_cancelled(request))
            fc.atomic_write(
                self.state / f"{fc.HYPRLAND_RESULT}-{request['token']}.json",
                json.dumps({"token": request["token"], "code": 0}),
            )
            clock.sleep(seconds)

        with (
            mock.patch.object(fc, "nested_hyprland", return_value=module),
            mock.patch.object(fc, "ensure_session"),
            mock.patch.object(fc, "current_session", return_value=live_state()),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", side_effect=tick),
        ):
            code = fc.request_hyprland_job(
                argparse.Namespace(timeout=10, label=None, manual_launcher=False), ["probe"], 2
            )
        self.assertEqual(code, 130)
        self.assertEqual(len(ticks), 2)

    def test_queue_time_does_not_consume_transition_budget_and_result_is_removed(self):
        clock = FakeClock()
        holder = {}
        module = self.nested()
        module.user_instance.return_value = "parent-signature"
        result_path = self.state / f"{fc.HYPRLAND_RESULT}-job-token.json"
        ticks = []

        def tick(seconds):
            ticks.append(seconds)
            if len(ticks) == 1:
                clock.sleep(fc.HYPRLAND_WORLD_WAIT + fc.HYPRLAND_RETURN_WAIT + 100)
            elif len(ticks) == 2:
                holder["token"] = "job-token"
                (self.state / fc.HYPRLAND_REQUEST).unlink()
            else:
                result_path.write_text(json.dumps({"token": "job-token", "code": 7}))

        with (
            mock.patch.object(fc, "nested_hyprland", return_value=module),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "ensure_session"),
            mock.patch.object(fc, "job_holder", side_effect=lambda: holder),
            mock.patch.object(fc, "current_session", return_value=live_state()),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", side_effect=tick),
        ):
            self.assertEqual(
                fc.request_hyprland_job(
                    argparse.Namespace(timeout=5000, label=None, manual_launcher=False), ["probe"], 2
                ),
                7,
            )
        self.assertFalse(result_path.exists())
        self.assertFalse((self.state / fc.HYPRLAND_END).exists())

    def test_pending_request_wait_is_bounded_by_timeout(self):
        clock = FakeClock()
        module = self.nested()
        module.user_instance.return_value = "parent-signature"
        with (
            mock.patch.object(fc, "nested_hyprland", return_value=module),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "ensure_session"),
            mock.patch.object(fc, "job_holder", return_value={"token": "other-job"}),
            mock.patch.object(fc, "current_session", return_value=live_state()),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.time, "sleep", side_effect=clock.sleep),
            self.assertRaisesRegex(fc.ClientError, "within --timeout"),
        ):
            fc.request_hyprland_job(argparse.Namespace(timeout=2, label=None, manual_launcher=False), ["probe"], 2)
        self.assertLess(clock.now, 2 + fc.JOB_POLL + 0.01)

    def test_requester_removes_error_result_without_writing_end_marker(self):
        module = self.nested()
        module.user_instance.return_value = "parent-signature"
        result_path = self.state / f"{fc.HYPRLAND_RESULT}-job-token.json"
        result_path.write_text(json.dumps({"token": "job-token", "code": 1, "error": "job failed"}))
        with (
            mock.patch.object(fc, "nested_hyprland", return_value=module),
            mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "job-token")),
            mock.patch.object(fc, "release_job"),
            mock.patch.object(fc, "ensure_session"),
            self.assertRaisesRegex(fc.ClientError, "job failed"),
        ):
            fc.request_hyprland_job(argparse.Namespace(timeout=2, label=None, manual_launcher=False), ["probe"], 2)
        self.assertFalse(result_path.exists())
        self.assertFalse((self.state / fc.HYPRLAND_END).exists())

    def test_completed_job_removes_its_end_marker(self):
        self.run_hyprland(cancelled=True)
        self.assertFalse((self.state / fc.HYPRLAND_END).exists())

    def test_teardown_clears_hyprland_leftovers(self):
        names = [fc.HYPRLAND_END, fc.HYPRLAND_REQUEST, f"{fc.HYPRLAND_RESULT}-old.json"]
        for name in names:
            (self.state / name).write_text("leftover")
        with mock.patch.object(fc, "end_client"):
            fc.teardown(None, {}, None, {})
        for name in names:
            self.assertFalse((self.state / name).exists())

    def test_serve_interrupt_publishes_error_without_returning_to_gamescope(self):
        result_path = self.state / f"{fc.HYPRLAND_RESULT}-job-token.json"
        with self.assertRaises(KeyboardInterrupt):
            self.run_hyprland(failure=KeyboardInterrupt())
        self.assertIn("interrupted", json.loads(result_path.read_text())["error"])

    def test_serve_releases_only_after_successful_return(self):
        result, order = self.serve_with(lambda *_args: mock.Mock(pid=124, poll=mock.Mock(return_value=None)))
        self.assertEqual(result, 0)
        self.assertEqual(order[0], ("acquire", "deskpilot#95"))
        self.assertEqual(order[1], ("job", "job-token", True))
        self.assertEqual(order[2][:2], ("release", "job-token"))

    def test_monitored_command_limit_uses_the_group_cleanup(self):
        clock = FakeClock()
        process = mock.Mock(pid=4242)

        def wait(timeout=None):
            if timeout is None:
                return 0
            clock.sleep(timeout)
            raise subprocess.TimeoutExpired("probe", timeout)

        process.wait.side_effect = wait
        check = mock.Mock()
        with (
            mock.patch.object(fc.subprocess, "Popen", return_value=process),
            mock.patch.object(fc.time, "monotonic", clock.monotonic),
            mock.patch.object(fc.os, "killpg", side_effect=ProcessLookupError) as kill,
            self.assertRaisesRegex(fc.ClientError, "0.3 s limit"),
        ):
            fc.run_job_command(["probe"], {}, 0.3, check)
        self.assertGreaterEqual(check.call_count, 2)
        self.assertEqual(kill.call_args_list[0].args, (4242, signal.SIGTERM))
        self.assertEqual(kill.call_args_list[-1].args, (4242, signal.SIGKILL))


class NestedHyprlandTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))
        self.module = fc.nested_hyprland()

    def test_config_has_only_the_private_outputs_and_no_autostarts(self):
        config = self.module.config(1920, 1080)
        self.assertIn('output = "FOREVER", mode = "1920x1080", position = "0x0"', config)
        self.assertNotIn("exec", config)
        self.assertNotIn("plugin", config)
        self.assertEqual(self.module.WORKSPACE, "special:forever-client")

    def test_xwayland_origin_comes_from_the_named_output(self):
        with mock.patch.object(
            self.module.subprocess,
            "run",
            return_value=mock.Mock(
                stdout="Monitors: 2\n 0: +OTHER 1280/1x800/1+0+0 OTHER\n 1: +FOREVER 1920/1x1080/1+1280+0 FOREVER\n"
            ),
        ) as run:
            self.assertEqual(self.module.xwayland_origin(":7"), [1280, 0])
        self.assertEqual(run.call_args.kwargs["env"]["DISPLAY"], ":7")

    def test_discovery_matches_the_pid_and_checks_its_hidden_workspace(self):
        run = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (run / "pid").write_text("42")
        runtime = run / "runtime"
        (runtime / "ours").mkdir(parents=True)
        (runtime / "other").mkdir()
        events = mock.Mock()
        events.recv.return_value = b"openwindow>>abc,special:forever-client,aquamarine,Nested\n"
        workspace = {"name": self.module.WORKSPACE}

        def ctl(signature, *args):
            if args == ("-j", "instances"):
                return json.dumps(
                    [{"instance": "other", "pid": 99}, {"instance": "ours", "pid": 42, "wl_socket": "wayland-9"}]
                )
            if args == ("-j", "clients"):
                return json.dumps([{"pid": 42, "workspace": workspace}])
            if args == ("-j", "monitors"):
                return '[{"name": "FOREVER"}]'
            return "ok"

        with (
            mock.patch.object(self.module, "RUNTIME", runtime),
            mock.patch.object(self.module, "alive", return_value=True),
            mock.patch.object(self.module, "hyprctl", side_effect=ctl),
            mock.patch.object(self.module, "process_birth", return_value="birth"),
            mock.patch.object(self.module, "xwayland_display", return_value=":7"),
            mock.patch.object(self.module, "xwayland_origin", return_value=[1280, 0]),
        ):
            record = self.module.started(events, run, set(), 1920, 1080, "parent")
            self.assertEqual(record["signature"], "ours")
            workspace["name"] = "1"
            with self.assertRaisesRegex(self.module.NestedError, "not on special"):
                self.module.started(events, run, set(), 1920, 1080, "parent")

    def test_stop_never_signals_a_reused_pid(self):
        with (
            mock.patch.object(self.module, "alive", return_value=False),
            mock.patch.object(self.module, "process_birth", return_value="new-birth"),
            mock.patch.object(self.module.os, "kill") as kill,
        ):
            self.module.stop({"pid": 42, "birth": "old-birth", "signature": "old", "run": "/nonexistent"})
        kill.assert_not_called()


class HeadlessQueueRegressionTest(unittest.TestCase):
    def setUp(self):
        self.ticket_handles = {}
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(fc, "STATE_DIR", self.root))
        self.enterContext(mock.patch.object(fc, "process_start", return_value=123))
        self.enterContext(mock.patch.object(fc, "boot_id", return_value="boot"))
        self.enterContext(
            mock.patch.object(
                fc,
                "owner_alive",
                side_effect=lambda record: bool(
                    record and record.get("started") == 123 and record.get("boot_id") == "boot"
                ),
            )
        )
        self.session = {"pid": 42, "started": 7, "start_ticks": 123, "boot_id": "boot", "ready": 1}
        self.enterContext(mock.patch.object(fc, "current_session", return_value=self.session))
        self.clock = FakeClock()
        self.enterContext(mock.patch.object(fc.time, "monotonic", self.clock.monotonic))
        self.enterContext(mock.patch.object(fc.time, "sleep", self.clock.sleep))

    def enqueue(self):
        path, handle = fc.enqueue_job()
        self.addCleanup(handle.close)
        self.ticket_handles[path] = handle
        return path

    def test_waiter_a_arrives_before_b_and_acquires_first(self):
        first = self.enqueue()
        order = []

        def let_a_run(seconds):
            self.clock.sleep(seconds)
            with mock.patch.object(fc, "enqueue_job", return_value=(first, self.ticket_handles[first])):
                handle, token = fc.acquire_job(0, "A")
            order.append("A")
            fc.release_job(handle, token)

        with mock.patch.object(fc.time, "sleep", side_effect=let_a_run):
            handle, token = fc.acquire_job(5, "B")
        order.append("B")
        fc.release_job(handle, token)
        self.assertEqual(order, ["A", "B"])
        self.assertEqual(fc.job_queue(), [])

    def test_abandoned_ticket_is_removed(self):
        ticket = self.enqueue()
        self.ticket_handles[ticket].close()
        handle, token = fc.acquire_job(0, "next")
        fc.release_job(handle, token)
        self.assertFalse(ticket.exists())

    def test_teardown_overtakes_tickets_without_removing_them(self):
        first = self.enqueue()
        handle, token = fc.acquire_job(0, "serve end", session_end=True)
        self.assertTrue(first.exists())
        fc.release_job(handle, token)
        self.assertEqual(fc.job_queue(), [first])

    def test_ticket_publication_exception_cleans_up_and_keeps_counter_monotonic(self):
        write = fc.atomic_write

        def fail_after_publish(path, contents):
            write(path, contents)
            if path.suffix == ".json":
                raise OSError("interrupted directory sync")

        with mock.patch.object(fc, "atomic_write", side_effect=fail_after_publish), self.assertRaises(OSError):
            self.enqueue()
        self.assertEqual(fc.job_queue(), [])
        ticket = self.enqueue()
        self.assertEqual(int(ticket.stem), 2)

    def test_timeout_and_exception_remove_the_waiters_ticket(self):
        first = self.enqueue()
        with self.assertRaisesRegex(fc.ClientError, "queue position 2"):
            fc.acquire_job(0, "timeout")
        self.assertEqual(fc.job_queue(), [first])
        with mock.patch.object(fc.time, "sleep", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            fc.acquire_job(5, "interrupted")
        self.assertEqual(fc.job_queue(), [first])

    def test_waiting_line_changes_with_holder_and_reports_position(self):
        first = self.enqueue()

        def tick(seconds):
            self.clock.sleep(seconds)

        with (
            mock.patch.object(fc, "describe_job", side_effect=["holder A", "holder B", "holder B"]),
            contextlib.redirect_stderr(io.StringIO()) as err,
            mock.patch.object(fc.time, "sleep", side_effect=tick),
            self.assertRaises(fc.ClientError),
        ):
            fc.acquire_job(fc.JOB_POLL * 2, "queued")
        self.assertEqual(err.getvalue().count("waiting for"), 2)
        self.assertIn("holder B; queue position 2", err.getvalue())
        self.assertEqual(fc.job_queue(), [first])

    def make_lease(self):
        token = "lease-token"
        path = fc.lease_path(token)
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "token": token,
                    "label": "test",
                    "expires": time.time() + 100,
                    "session": fc.session_identity(self.session),
                }
            )
        )
        return token

    def test_session_end_replaced_expired_and_released_leases_never_queue(self):
        for reason in ("session ended because world lost", "replaced", "expired", "released"):
            with self.subTest(reason=reason):
                token = self.make_lease()
                if reason == "replaced":
                    self.session["started"] += 1
                elif reason == "expired":
                    record = json.loads(fc.lease_path(token).read_text())
                    record["expires"] = 0
                    fc.lease_path(token).write_text(json.dumps(record))
                elif reason == "released":
                    fc.release(token)
                else:
                    fc.clear_leases(reason)
                with (
                    mock.patch.dict(os.environ, FOREVER_CLIENT_JOB=token),
                    mock.patch.object(fc, "acquire_job") as acquire,
                    self.assertRaisesRegex(fc.ClientError, "lease (ended|expired)"),
                ):
                    fc.with_job("shot", 5, mock.Mock())
                acquire.assert_not_called()

    def test_lease_is_rechecked_after_waiting_for_the_lock(self):
        token = self.make_lease()

        def acquire(*_args):
            fc.clear_leases("session ended because source changed")
            return mock.Mock(), "job"

        with (
            mock.patch.dict(os.environ, FOREVER_CLIENT_JOB=token),
            mock.patch.object(fc, "acquire_job", side_effect=acquire),
            mock.patch.object(fc, "release_job") as release,
            self.assertRaisesRegex(fc.ClientError, "source changed"),
        ):
            fc.with_job("shot", 5, mock.Mock())
        release.assert_called_once()

    def test_headless_addon_files_are_launcher_sources_and_change_digest(self):
        addon = self.root / "addon"
        addon.mkdir()
        lua = addon / "ForeverHeadless.lua"
        lua.write_text("old protocol")
        with mock.patch.object(fc, "ADDON", addon):
            baseline = fc.launcher_sources()
            digest = fc.headless_addon_digest()
            self.assertIn(lua, baseline)
            lua.write_text("new protocol")
            self.assertNotEqual(fc.launcher_sources(baseline), baseline)
            self.assertNotEqual(fc.headless_addon_digest(), digest)

    def test_resident_source_check_detects_added_headless_addon_files(self):
        addon = self.root / "addon"
        addon.mkdir()
        (addon / "ForeverHeadless.lua").write_text("protocol")
        with mock.patch.object(fc, "ADDON", addon):
            baseline = fc.launcher_sources()
            (addon / "NewProtocol.lua").write_text("new protocol")
            self.assertNotEqual(fc.launcher_sources(baseline), baseline)

    def test_changed_addon_at_same_protocol_is_torn_down_under_the_job_lock(self):
        old = {**self.session, "headless_addon_digest": "old"}
        fresh = {**self.session, "headless_addon_digest": fc.headless_addon_digest()}
        handle, token = fc.acquire_job(0, "new caller")

        def stop():
            self.assertEqual(fc.job_holder()["token"], token)
            self.assertNotIn("ready", old)
            self.assertIn("headless addon source changed", old["end_reason"])

        try:
            with (
                mock.patch.object(fc, "current_session", side_effect=[old, fresh]),
                mock.patch.object(fc, "client_ui", return_value={"world": True, "safety": True}) as ui,
                mock.patch.object(fc, "write_state"),
                mock.patch.object(fc, "down", side_effect=stop) as down,
            ):
                self.assertEqual(fc.ensure_session(5), fresh)
            down.assert_called_once()
            ui.assert_called_once_with(fresh)
        finally:
            fc.release_job(handle, token)

    def test_newer_verb_requests_locked_restart_for_old_protocol(self):
        state = {**self.session, "headless_addon_digest": "old"}
        with (
            mock.patch.dict(os.environ, FOREVER_CLIENT_JOB=""),
            mock.patch.object(fc, "load_state", return_value=state),
            mock.patch.object(fc, "ensure_session", return_value=self.session) as ensure,
            mock.patch.object(fc, "session_alive", return_value=True),
        ):
            self.assertEqual(fc.with_job("shot", 5, lambda state: state["pid"]), 42)
        ensure.assert_called_once_with(5)

    def test_token_inside_job_does_not_restart_session(self):
        action = mock.Mock(return_value=0)
        with (
            mock.patch.dict(os.environ, FOREVER_CLIENT_JOB="held"),
            mock.patch.object(fc, "job_holder", return_value={"token": "held"}),
            mock.patch.object(fc, "load_state", return_value=self.session),
            mock.patch.object(fc, "compatible_session", side_effect=AssertionError("restart inside job")),
        ):
            self.assertEqual(fc.with_job("shot", 5, action), 0)
        action.assert_called_once_with(self.session)

    def test_missing_own_ticket_fails_clearly(self):
        with mock.patch.object(fc, "job_queue", return_value=[]):
            with self.assertRaisesRegex(fc.ClientError, "ticket.*disappeared"):
                fc.acquire_job(0, "lost")

    def test_locked_ticket_survives_invisible_owner(self):
        ticket = self.enqueue()
        with mock.patch.object(fc, "owner_alive", return_value=False):
            self.assertEqual(fc.job_queue(), [ticket])
        self.ticket_handles[ticket].close()
        self.assertEqual(fc.job_queue(), [])

    def test_issuing_lease_prunes_expired_records(self):
        token = self.make_lease()
        path = fc.lease_path(token)
        record = json.loads(path.read_text())
        record["expires"] = 0
        record["ended"] = "released"
        path.write_text(json.dumps(record))
        with (
            mock.patch.object(fc, "ensure_session", return_value=self.session),
            mock.patch.object(fc, "require_safe") as safety,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            fc.lease(argparse.Namespace(ttl=100, label="new", timeout=0, manual_launcher=False))
        safety.assert_called_once_with(self.session)
        self.assertFalse(path.exists())

    def test_recover_links_leaves_another_live_owners_record_untouched(self):
        addons = self.root / "AddOns"
        addons.mkdir()
        target = self.root / "build"
        target.mkdir()
        with (
            mock.patch.object(fc, "addons_dir", return_value=addons),
            mock.patch.object(fc, "client_in_use", return_value=None),
        ):
            records = fc.link_build([("Addon", target)], addons)
            record = json.loads(fc.link_record_path().read_text())
            record["owner"]["pid"] = 42
            fc.link_record_path().write_text(json.dumps(record))
            with (
                open(fc.job_lock_path(), "a+") as holder,
                mock.patch.object(fc, "owner_alive", return_value=False),
                mock.patch.object(fc, "restore_links") as restore,
            ):
                fc.fcntl.flock(holder, fc.fcntl.LOCK_EX | fc.fcntl.LOCK_NB)
                self.assertEqual(fc.recover_links(), 0)
            restore.assert_not_called()
            fc.verify_links(records)


class FetchCommitRegressionTest(unittest.TestCase):
    def test_a_missing_full_sha_fetches_origin_once_and_retries(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        origin, writer, reader = (root / name for name in ("origin", "writer", "reader"))

        def git(*args):
            return subprocess.check_output(["git", *map(str, args)], stderr=subprocess.PIPE, text=True).strip()

        git("init", "--bare", origin)
        git("clone", origin, writer)
        git(
            "-C",
            writer,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            "first",
        )
        git("-C", writer, "push", "origin", "HEAD")
        git("clone", origin, reader)
        git(
            "-C",
            writer,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            "second",
        )
        sha = git("-C", writer, "rev-parse", "HEAD")
        git("-C", writer, "push", "origin", "HEAD")
        with mock.patch.object(fc, "git", wraps=fc.git) as calls:
            self.assertEqual(fc.resolve_commit(reader, sha), sha)
            self.assertEqual(sum(call.args[1:] == ("fetch", "origin") for call in calls.call_args_list), 1)
            calls.reset_mock()
            self.assertEqual(fc.resolve_commit(reader, sha), sha)
            self.assertFalse(any(call.args[1] == "fetch" for call in calls.call_args_list))
            with self.assertRaisesRegex(fc.ClientError, "commit .* is not on origin"):
                fc.resolve_commit(reader, "f" * 40)
            self.assertEqual(sum(call.args[1:] == ("fetch", "origin") for call in calls.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()


class LiveSafetyTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.dict(os.environ, {"FOREVER_CLIENT_CALLER": "in-game"}))

    def test_decode_version_old_header_and_unsafe_bits(self):
        for header, dead, combat in [
            ("01110010", False, False),
            ("01110010", True, False),
            ("01110010", False, True),
            ("10110010", False, False),
        ]:
            with self.subTest(header=header, dead=dead, combat=combat):
                row = b"".join(
                    bytes([128 if bit else 127]) * 12
                    for bit in [*(c == "1" for c in header), True, False, False, dead, combat]
                )
                with (
                    mock.patch.object(fc, "shot"),
                    mock.patch.object(fc, "png_pixels", return_value=(52, 4, 3, [row] * 4)),
                ):
                    ui = fc.client_ui({})
                self.assertEqual(ui["safety"], header == "01110010")
                self.assertEqual(ui["dead"], dead if ui["safety"] else True)
                self.assertEqual(ui["combat"], combat if ui["safety"] else True)

    def test_every_input_verb_refuses_before_any_action(self):
        for verb in ("slash", "click", "scroll", "key", "reload", "eval", "errors"):
            for dead, combat, reason in [
                (True, False, "player is dead or a ghost"),
                (False, True, "player is in combat"),
            ]:
                with self.subTest(verb=verb, reason=reason), contextlib.ExitStack() as stack:
                    stack.enter_context(
                        mock.patch.object(
                            fc, "client_ui", return_value={"safety": True, "dead": dead, "combat": combat}
                        )
                    )
                    actions = [
                        stack.enter_context(mock.patch.object(fc, name))
                        for name in ("x", "slash", "click", "scroll", "press", "reload", "devsmoke_eval")
                    ]
                    with self.assertRaisesRegex(fc.SafetyRefusal, reason):
                        fc.input_verb({"ready": True}, argparse.Namespace(verb=verb))
                    for action in actions:
                        action.assert_not_called()

    def test_each_low_level_send_rechecks_safety_including_typed_input(self):
        with (
            mock.patch.object(fc, "client_ui", return_value={"safety": True, "dead": True, "combat": False}),
            mock.patch.object(fc, "mark", return_value=0),
            mock.patch.object(fc.subprocess, "run") as inputs,
            self.assertRaisesRegex(fc.SafetyRefusal, "player is dead or a ghost"),
        ):
            fc.send({"ready": True}, "type", "/forever")
        inputs.assert_not_called()

    def test_jobs_and_lease_refuse_before_starting_children_and_release_lock(self):
        argvs = {
            "job": ["job", "--", "true"],
            "hyprland": ["job", "--hyprland", "--", "true"],
            "lease": ["lease"],
        }
        for verb, argv in argvs.items():
            state = Path(self.enterContext(tempfile.TemporaryDirectory()))
            with (
                self.subTest(verb=verb),
                mock.patch.object(fc, "STATE_DIR", state),
                mock.patch.object(fc, "nested_hyprland"),
                mock.patch.object(fc, "acquire_job", return_value=(mock.Mock(), "token")),
                mock.patch.object(fc, "ensure_session", return_value={"ready": True}),
                mock.patch.object(fc, "release_job") as released,
                mock.patch.object(fc, "client_ui", return_value={"safety": True, "dead": True, "combat": False}),
                mock.patch.object(fc.subprocess, "run") as inputs,
                mock.patch.object(fc.subprocess, "Popen") as children,
                contextlib.redirect_stderr(io.StringIO()) as error,
            ):
                self.assertEqual(fc.main(argv), 4)
                self.assertIn("player is dead or a ghost", error.getvalue())
                inputs.assert_not_called()
                children.assert_not_called()
                released.assert_called_once()
                # Neither a lease record nor a Hyprland request is left for serve or a verb to act on.
                self.assertEqual(list(state.rglob("*.json")), [])

    def test_unusable_resident_is_replaced_without_safety_refusal(self):
        for stale, header in [
            ({"ready": True}, "10110010"),
            ({"world_lost": True}, "00000000"),
            ({"ready": True}, "00000000"),
        ]:
            with self.subTest(stale=stale, header=header):
                stale = live_state(**stale)
                fresh = live_state(ready=True)
                # A v1 capture is only 44 pixels wide, with no safety cells.
                row = b"".join(bytes([255 if bit == "1" else 0]) * 12 for bit in header + "100")
                with (
                    mock.patch.object(fc, "current_session", side_effect=[stale, None, fresh]),
                    mock.patch.object(fc, "shot"),
                    mock.patch.object(fc, "png_pixels", return_value=(44, 4, 3, [row] * 4)),
                ):
                    old_ui = fc.client_ui(stale)
                    self.assertEqual(old_ui.get("outdated", False), header == "10110010")
                    with (
                        mock.patch.object(fc, "client_ui", side_effect=[old_ui, {"world": True, "safety": True}]) as ui,
                        mock.patch.object(fc, "require_safe") as safety,
                        mock.patch.object(fc, "job_holder", return_value={"pid": os.getpid()}),
                        mock.patch.object(fc, "write_state"),
                        mock.patch.object(fc, "down") as stop,
                        mock.patch.object(fc, "session_lock_held", return_value=False),
                        mock.patch.object(fc, "start_serve", return_value=mock.Mock(poll=lambda: None)) as start,
                        mock.patch.object(fc.time, "sleep"),
                    ):
                        self.assertIs(fc.ensure_session(1), fresh)
                    stop.assert_called_once()
                    start.assert_called_once()
                    self.assertEqual(ui.call_count, 2)
                    safety.assert_not_called()

    def test_reload_and_flow_waits_report_live_refusal_without_sleeping(self):
        with (
            mock.patch.object(fc, "client_ui", return_value={"safety": True, "dead": False, "combat": True}),
            mock.patch.object(fc.time, "sleep") as sleep,
        ):
            for wait in (
                lambda: fc.wait_for_world(set(), 10, safety_state={}),
                lambda: fc.wait_for_flow_world(set(), "/lf", state={}),
                lambda: fc.wait_for_flow_ready(set(), "/lf", state={}),
            ):
                with self.assertRaisesRegex(fc.SafetyRefusal, "player is in combat"):
                    wait()
            sleep.assert_not_called()

    def test_verbs_inside_an_existing_job_still_refuse_input(self):
        for verb in (["slash", "/forever"], ["key", "Escape"], ["click", "2", "2"]):
            with (
                self.subTest(verb=verb),
                mock.patch.dict(os.environ, {"FOREVER_CLIENT_JOB": "token"}),
                mock.patch.object(fc, "job_holder", return_value={"token": "token"}),
                mock.patch.object(fc, "load_state", return_value={"ready": True}),
                mock.patch.object(fc, "session_alive", return_value=True),
                mock.patch.object(fc, "client_ui", return_value={"safety": True, "dead": False, "combat": True}),
                mock.patch.object(fc, "x") as inputs,
                mock.patch.object(fc, "acquire_job") as lock,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(fc.main(verb), 4)
                inputs.assert_not_called()
                lock.assert_not_called()

    def test_read_only_verbs_remain_available_without_input_or_reload(self):
        with (
            mock.patch.object(fc, "client_ui", return_value={"safety": True, "dead": True, "combat": True}),
            mock.patch.object(fc, "shot") as shot,
            mock.patch.object(fc, "reload") as reload,
            mock.patch.object(fc, "job_started", return_value=0),
            mock.patch.object(fc.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(fc.input_verb({"ready": True}, argparse.Namespace(verb="shot", path=None)), 0)
            shot.assert_called_once()
            reload.assert_not_called()
