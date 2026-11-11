"""Tests for tools/forever_perf.py: the DevPerfDB report, the deltas, SavedVariables size and smoke flags."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import forever_perf as perf


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sized(path: Path, statement: str, size: int) -> None:
    """A valid SavedVariables file padded with a comment to exactly size bytes."""
    write(path, statement + "\n-- " + "x" * (size - len(statement) - 5) + "\n")


def old_session() -> str:
    return """
{
["started"] = 400,
["build"] = "1.60.1.70000",
["buildNumber"] = 70000,
["interface"] = 16001,
["character"] = "Oldchar",
["level"] = 79,
["profiler"] = true,
["addons"] = {
{ ["name"] = "AdventureGuideForever", ["version"] = "v1", ["ours"] = true },
{ ["name"] = "TweaksForever", ["version"] = "v2", ["ours"] = true },
{ ["name"] = "Questie", ["version"] = "v3", ["ours"] = false },
},
["load"] = {
["fileMs"] = 40,
["enteringWorldMs"] = 200,
["loadingMs"] = 300,
["reload"] = false,
["addonLoaded"] = {
{ ["name"] = "AdventureGuideForever", ["ms"] = 80 },
{ ["name"] = "TweaksForever", ["ms"] = 180 },
},
},
["context"] = { ["questLogEntries"] = 5, ["mapID"] = 2024, ["freeBagSlots"] = 3 },
["marks"] = {
{
["label"] = "login",
["at"] = 410,
["clock"] = 10,
["ms"] = 1,
["overall"] = { ["SessionAverageTime"] = 0.5 },
["application"] = { ["SessionAverageTime"] = 0.4 },
["addons"] = {
["AdventureGuideForever"] = {
["SessionAverageTime"] = 1.0,
["RecentAverageTime"] = 1.1,
["PeakTime"] = 2.0,
["CountTimeOver5Ms"] = 2,
["CountTimeOver10Ms"] = 1,
["CountTimeOver50Ms"] = 0,
["memoryKB"] = 1024,
},
["TweaksForever"] = {
["SessionAverageTime"] = 0.5,
["RecentAverageTime"] = 0.5,
["PeakTime"] = 1.5,
["CountTimeOver5Ms"] = 1,
["CountTimeOver10Ms"] = 0,
["CountTimeOver50Ms"] = 0,
["memoryKB"] = 512,
},
},
},
{
["label"] = "after-selftest",
["at"] = 420,
["clock"] = 20,
["ms"] = 1,
["overall"] = { ["SessionAverageTime"] = 0.5 },
["application"] = { ["SessionAverageTime"] = 0.4 },
["addons"] = {
["AdventureGuideForever"] = {
["SessionAverageTime"] = 1.0,
["RecentAverageTime"] = 1.2,
["PeakTime"] = 2.0,
["CountTimeOver5Ms"] = 6,
["CountTimeOver10Ms"] = 3,
["CountTimeOver50Ms"] = 1,
["memoryKB"] = 2048,
},
["TweaksForever"] = {
["SessionAverageTime"] = 0.5,
["RecentAverageTime"] = 0.6,
["PeakTime"] = 1.5,
["CountTimeOver5Ms"] = 2,
["CountTimeOver10Ms"] = 0,
["CountTimeOver50Ms"] = 0,
["memoryKB"] = 768,
},
},
},
},
["scenarios"] = {
{
["name"] = "tooltips",
["at"] = 425,
["frames"] = 120,
["wallMs"] = 240,
["kinds"] = {
["tooltip set"] = { ["count"] = 120, ["totalMs"] = 96, ["maxMs"] = 3.6 },
["pin enter"] = { ["count"] = 10, ["totalMs"] = 5, ["maxMs"] = 0.8 },
},
["addons"] = {
["AdventureGuideForever"] = {
["RecentAverageTime"] = 1.4,
["PeakTime"] = 4.2,
["peakRaised"] = true,
["over"] = { ["CountTimeOver1Ms"] = 12, ["CountTimeOver5Ms"] = 1 },
["memoryDeltaKB"] = 2048,
},
["TweaksForever"] = {
["RecentAverageTime"] = 0.4,
["PeakTime"] = 0.9,
["peakRaised"] = false,
["over"] = { ["CountTimeOver1Ms"] = 2 },
["memoryDeltaKB"] = 128,
},
["Questie"] = {
["RecentAverageTime"] = 2.2,
["PeakTime"] = 5.5,
["peakRaised"] = false,
["over"] = { ["CountTimeOver1Ms"] = 20 },
["memoryDeltaKB"] = 512,
},
},
},
{
["name"] = "mappins",
["at"] = 430,
["frames"] = 0,
["wallMs"] = 0,
["skipped"] = "no world map",
},
},
["combat"] = {
["fights"] = 1,
["seconds"] = 30,
["peakRaised"] = { ["AdventureGuideForever"] = 2.5 },
["over"] = { ["AdventureGuideForever"] = { ["CountTimeOver5Ms"] = 3, ["CountTimeOver10Ms"] = 1 } },
},
["heap"] = { ["samples"] = 10, ["minKB"] = 100, ["maxKB"] = 200, ["collectedKB"] = 50 },
}
"""


def new_session() -> str:
    return """
{
["started"] = 500,
["build"] = "1.60.1.70124",
["buildNumber"] = 70124,
["interface"] = 16001,
["character"] = "Newchar",
["level"] = 80,
["profiler"] = true,
["addons"] = {
{ ["name"] = "AdventureGuideForever", ["version"] = "v1", ["ours"] = true },
{ ["name"] = "TweaksForever", ["version"] = "v2", ["ours"] = true },
{ ["name"] = "Questie", ["version"] = "v3", ["ours"] = false },
},
["load"] = {
["fileMs"] = 50,
["enteringWorldMs"] = 250,
["loadingMs"] = 400,
["reload"] = true,
["addonLoaded"] = {
{ ["name"] = "AdventureGuideForever", ["ms"] = 100 },
{ ["name"] = "TweaksForever", ["ms"] = 250 },
{ ["name"] = "Questie", ["ms"] = 450 },
},
},
["context"] = { ["questLogEntries"] = 12, ["mapID"] = 2025, ["freeBagSlots"] = 4 },
["marks"] = {
{
["label"] = "login",
["at"] = 510,
["clock"] = 10,
["ms"] = 1,
["overall"] = { ["SessionAverageTime"] = 0.6 },
["application"] = { ["SessionAverageTime"] = 0.5 },
["addons"] = {
["AdventureGuideForever"] = {
["SessionAverageTime"] = 1.5,
["RecentAverageTime"] = 1.4,
["PeakTime"] = 2.5,
["CountTimeOver1Ms"] = 10,
["CountTimeOver5Ms"] = 2,
["CountTimeOver10Ms"] = 1,
["CountTimeOver50Ms"] = 0,
["CountTimeOver100Ms"] = 0,
["memoryKB"] = 1024,
},
["TweaksForever"] = {
["SessionAverageTime"] = 0.6,
["RecentAverageTime"] = 0.6,
["PeakTime"] = 1.6,
["CountTimeOver1Ms"] = 5,
["CountTimeOver5Ms"] = 1,
["CountTimeOver10Ms"] = 0,
["CountTimeOver50Ms"] = 0,
["CountTimeOver100Ms"] = 0,
["memoryKB"] = 640,
},
["Questie"] = {
["SessionAverageTime"] = 2.0,
["RecentAverageTime"] = 2.1,
["PeakTime"] = 5.0,
["CountTimeOver1Ms"] = 8,
["CountTimeOver5Ms"] = 2,
["CountTimeOver10Ms"] = 1,
["CountTimeOver50Ms"] = 0,
["CountTimeOver100Ms"] = 0,
},
},
},
{
["label"] = "after-selftest",
["at"] = 520,
["clock"] = 20,
["ms"] = 1,
["overall"] = { ["SessionAverageTime"] = 0.7 },
["application"] = { ["SessionAverageTime"] = 0.6 },
["addons"] = {
["AdventureGuideForever"] = {
["SessionAverageTime"] = 2.0,
["RecentAverageTime"] = 1.9,
["PeakTime"] = 4.5,
["CountTimeOver1Ms"] = 20,
["CountTimeOver5Ms"] = 6,
["CountTimeOver10Ms"] = 3,
["CountTimeOver50Ms"] = 1,
["CountTimeOver100Ms"] = 0,
["memoryKB"] = 2048,
},
["TweaksForever"] = {
["SessionAverageTime"] = 0.7,
["RecentAverageTime"] = 0.7,
["PeakTime"] = 2.5,
["CountTimeOver1Ms"] = 8,
["CountTimeOver5Ms"] = 2,
["CountTimeOver10Ms"] = 0,
["CountTimeOver50Ms"] = 0,
["CountTimeOver100Ms"] = 0,
["memoryKB"] = 768,
},
["Questie"] = {
["SessionAverageTime"] = 2.2,
["RecentAverageTime"] = 2.2,
["PeakTime"] = 5.5,
["CountTimeOver1Ms"] = 12,
["CountTimeOver5Ms"] = 3,
["CountTimeOver10Ms"] = 1,
["CountTimeOver50Ms"] = 0,
["CountTimeOver100Ms"] = 0,
},
},
},
{
["label"] = "idle",
["at"] = 600,
["clock"] = 100,
["ms"] = 1,
["overall"] = { ["SessionAverageTime"] = 0.4 },
["application"] = { ["SessionAverageTime"] = 0.3 },
["addons"] = {
["AdventureGuideForever"] = {
["SessionAverageTime"] = 1.2,
["RecentAverageTime"] = 1.0,
["PeakTime"] = 4.5,
["CountTimeOver1Ms"] = 24,
["CountTimeOver5Ms"] = 6,
["CountTimeOver10Ms"] = 3,
["CountTimeOver50Ms"] = 1,
["CountTimeOver100Ms"] = 0,
["memoryKB"] = 2050,
},
["TweaksForever"] = {
["SessionAverageTime"] = 0.4,
["RecentAverageTime"] = 0.4,
["PeakTime"] = 1.2,
["CountTimeOver1Ms"] = 9,
["CountTimeOver5Ms"] = 2,
["CountTimeOver10Ms"] = 0,
["CountTimeOver50Ms"] = 0,
["CountTimeOver100Ms"] = 0,
["memoryKB"] = 770,
},
},
},
},
["combat"] = {
["fights"] = 2,
["seconds"] = 45,
["peakRaised"] = { ["AdventureGuideForever"] = 3.5, ["Questie"] = 4.0 },
["over"] = {
["AdventureGuideForever"] = { ["CountTimeOver5Ms"] = 4, ["CountTimeOver10Ms"] = 2, ["CountTimeOver50Ms"] = 0 },
["Questie"] = { ["CountTimeOver5Ms"] = 5, ["CountTimeOver10Ms"] = 2 },
},
},
}
"""


def build_fixture(root: Path) -> Path:
    wtf = root / "WTF"
    account = wtf / "Account" / "1" / "SavedVariables"
    write(
        account / "!!DevPerf.lua",
        'DevPerfDB = {\n["version"] = 1,\n["sessions"] = {' + old_session() + "," + new_session() + "},\n}\n",
    )
    write(
        account / "!!DevSmoke.lua",
        """
DevSmokeDB = {
["runs"] = {
{
["started"] = 400,
["build"] = "1.60.1.70000",
["results"] = {
{ ["surface"] = "old surface", ["ok"] = true, ["ms"] = 9.0, ["firstMs"] = 9.0, ["errors"] = {} },
},
},
{
["started"] = 500,
["build"] = "1.60.1.70124",
["results"] = {
{ ["surface"] = "AdventureGuideForever /agf", ["ok"] = true, ["ms"] = 1.5, ["firstMs"] = 2.0, ["errors"] = {} },
{ ["surface"] = "LegacyForever /lf", ["ok"] = true, ["ms"] = 5.0, ["firstMs"] = 4.0, ["errors"] = {} },
{ ["surface"] = "world map", ["ok"] = true, ["ms"] = 2.0, ["firstMs"] = 1.0, ["errors"] = {} },
},
},
},
}
""",
    )
    sized(
        account / "AdventureGuideForever.lua",
        'AdventureGuideForeverDB = { ["errors"] = {} }',
        16 * 1024,
    )
    sized(account / "TweaksForever.lua", 'TweaksForeverDB = { ["errors"] = {} }', 2 * 1024)
    sized(wtf / "Account" / "1" / "Newchar" / "SavedVariables" / "SkillUpForever.lua", "SkillUpForeverDB = {}", 1024)
    sized(account / "Questie.lua", "QuestieDB = {}", 4096)
    return wtf


def run_main(*arguments: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = perf.main(list(arguments))
    return status, stdout.getvalue(), stderr.getvalue()


class PerfReportTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.wtf = build_fixture(self.directory)
        self.sources = perf.load_sources(self.wtf)

    def session(self, index: int = 1) -> perf.Session:
        return self.sources.sessions[-index]

    def test_reads_both_sessions_newest_last_and_the_newest_smoke_run(self):
        self.assertEqual([session.character for session in self.sources.sessions], ["Oldchar", "Newchar"])
        self.assertEqual(self.session().build, "1.60.1.70124")
        self.assertEqual(self.session().level, 80)
        self.assertEqual([mark.label for mark in self.session().marks], ["login", "after-selftest", "idle"])
        self.assertIsNotNone(self.sources.smoke)
        assert self.sources.smoke is not None
        self.assertEqual(self.sources.smoke.started, 500.0)
        self.assertEqual([result.surface for result in self.sources.smoke.results][1], "LegacyForever /lf")

    def test_load_gaps_are_the_previous_addons_file_run(self):
        self.assertEqual(
            perf.session_gaps(self.session()),
            [
                ("AdventureGuideForever", 50.0),
                ("TweaksForever", 150.0),
                ("Questie", 200.0),
            ],
        )

    def test_first_load_gap_starts_at_the_devperf_file_time(self):
        session = self.session()
        self.assertEqual(session.load.file_ms, 50.0)
        self.assertEqual(perf.session_gaps(session)[0], ("AdventureGuideForever", 50.0))
        self.assertNotEqual(perf.session_gaps(session)[0][1], session.load.addons[0].ms)

    def test_interval_deltas_follow_the_marks(self):
        login, after = self.session().marks[:2]
        rows = {row.name: row for row in perf.interval_rows(login, after, self.session())}
        guide = rows["AdventureGuideForever"]
        self.assertEqual(guide.over1_ms, 10.0)
        self.assertEqual(guide.over5_ms, 4.0)
        self.assertEqual(guide.over10_ms, 2.0)
        self.assertEqual(guide.over50_ms, 1.0)
        self.assertEqual(guide.over100_ms, 0.0)
        self.assertEqual(guide.memory_mb, 1.0)

    def test_saved_variables_sizes_are_per_file_and_flag_ours(self):
        rows = {row.name: row for row in perf.saved_variable_sizes(self.wtf)}
        guide = rows["AdventureGuideForever.lua"]
        self.assertAlmostEqual(guide.kb, 16.0, places=2)
        self.assertAlmostEqual(guide.account_kb, 16.0, places=2)
        self.assertAlmostEqual(guide.character_kb, 0.0, places=2)
        self.assertEqual(guide.files, 1)
        self.assertAlmostEqual(guide.disk_kb, 16.0, places=2)
        self.assertTrue(guide.ours)
        skillup = rows["SkillUpForever.lua"]
        self.assertAlmostEqual(skillup.kb, 1.0, places=2)
        self.assertAlmostEqual(skillup.account_kb, 0.0, places=2)
        self.assertAlmostEqual(skillup.character_kb, 1.0, places=2)
        self.assertEqual(skillup.files, 1)
        self.assertAlmostEqual(skillup.disk_kb, 1.0, places=2)
        self.assertTrue(skillup.ours)
        questie = rows["Questie.lua"]
        self.assertAlmostEqual(questie.kb, 4.0, places=2)
        self.assertAlmostEqual(questie.account_kb, 4.0, places=2)
        self.assertAlmostEqual(questie.character_kb, 0.0, places=2)
        self.assertEqual(questie.files, 1)
        self.assertFalse(questie.ours)

    def test_saved_variables_do_not_sum_characters_into_the_per_login_size(self):
        with tempfile.TemporaryDirectory() as directory:
            wtf = Path(directory) / "WTF"
            account = wtf / "Account" / "1" / "SavedVariables"
            sized(account / "AcrossForever.lua", "AcrossForeverDB = {}", 8 * 1024)
            sized(
                wtf / "Account" / "1" / "Achar" / "SavedVariables" / "AcrossForever.lua",
                "AcrossForeverDB = {}",
                2 * 1024,
            )
            sized(
                wtf / "Account" / "1" / "Bchar" / "SavedVariables" / "AcrossForever.lua",
                "AcrossForeverDB = {}",
                4 * 1024,
            )
            row = perf.saved_variable_sizes(wtf)[0]
            self.assertAlmostEqual(row.kb, 12.0, places=2)
            self.assertAlmostEqual(row.account_kb, 8.0, places=2)
            self.assertAlmostEqual(row.character_kb, 4.0, places=2)
            self.assertEqual(row.files, 3)
            self.assertAlmostEqual(row.disk_kb, 14.0, places=2)

    def test_saved_variables_text_labels_the_disk_total_as_disk_use(self):
        with tempfile.TemporaryDirectory() as directory:
            wtf = Path(directory) / "WTF"
            account = wtf / "Account" / "1" / "SavedVariables"
            sized(account / "AcrossForever.lua", "AcrossForeverDB = {}", 8 * 1024)
            sized(
                wtf / "Account" / "1" / "Achar" / "SavedVariables" / "AcrossForever.lua",
                "AcrossForeverDB = {}",
                2 * 1024,
            )
            sized(
                wtf / "Account" / "1" / "Bchar" / "SavedVariables" / "AcrossForever.lua",
                "AcrossForeverDB = {}",
                4 * 1024,
            )
            saved = perf.saved_variable_sizes(wtf)
            report = perf.build_report(
                session=self.session(),
                session_index=1,
                session_count=1,
                saved_variables=saved,
                smoke=None,
            )
            text = perf.render_text(report)
            login_total = sum(row.kb for row in saved)
            disk_total = sum(row.disk_kb for row in saved)
            self.assertIn(
                f"1 file name(s) read at login; {login_total:.1f} KB per login, {disk_total:.1f} KB on disk",
                text,
            )
            self.assertNotIn(f"{disk_total:.1f} KB per login", text)
            row = next(line for line in text.splitlines() if line.startswith("AcrossForever.lua"))
            self.assertIn("12.0", row)
            self.assertIn("3", row)
            self.assertIn("FILES", text)

    def test_smoke_flags_and_wfa13_findings(self):
        findings = perf.wfa13_findings(self.session(), self.sources.smoke)
        self.assertIn("mark 'idle': AdventureGuideForever peak 4.5 ms", findings)
        self.assertIn("smoke 'LegacyForever /lf': ms 5.0 ms, firstMs 4.0 ms", findings)
        self.assertFalse(any("world map" in finding for finding in findings))
        self.assertFalse(any("Questie peak" in finding for finding in findings))

    def test_a_cumulative_peak_is_reported_once_from_the_newest_mark(self):
        findings = perf.wfa13_findings(self.session(), None)
        self.assertEqual(findings, ["mark 'idle': AdventureGuideForever peak 4.5 ms"])
        self.assertEqual(sum("AdventureGuideForever" in finding for finding in findings), 1)

    def test_scenarios_parse_with_kinds_and_addon_costs(self):
        scenarios = self.session(2).scenarios
        self.assertEqual([scenario.name for scenario in scenarios], ["tooltips", "mappins"])
        tooltips, mappins = scenarios
        self.assertEqual(tooltips.frames, 120)
        self.assertEqual(tooltips.wall_ms, 240.0)
        self.assertIsNone(tooltips.skipped)
        self.assertEqual(tooltips.kinds["tooltip set"].count, 120)
        self.assertEqual(tooltips.kinds["tooltip set"].total_ms, 96.0)
        self.assertEqual(tooltips.kinds["tooltip set"].max_ms, 3.6)
        self.assertTrue(tooltips.addons["AdventureGuideForever"].peak_raised)
        self.assertEqual(tooltips.addons["AdventureGuideForever"].over["CountTimeOver1Ms"], 12.0)
        self.assertEqual(tooltips.addons["AdventureGuideForever"].memory_delta_kb, 2048.0)
        self.assertEqual(mappins.skipped, "no world map")
        self.assertEqual(mappins.kinds, {})
        rows = perf.scenario_rows(tooltips, self.session(2))
        self.assertEqual([row.name for row in rows], ["AdventureGuideForever", "TweaksForever", "Questie"])
        self.assertTrue(rows[0].ours)
        self.assertFalse(rows[-1].ours)
        self.assertEqual(rows[0].over1_ms, 12.0)
        self.assertEqual(rows[0].memory_mb, 2.0)

    def test_scenario_findings_cover_our_addons_and_kinds(self):
        findings = perf.wfa13_findings(self.session(2), None)
        self.assertIn(
            "scenario 'tooltips': AdventureGuideForever recent 1.4 ms, peak 4.2 ms raised",
            findings,
        )
        self.assertIn("scenario 'tooltips': kind 'tooltip set' max 3.6 ms", findings)
        self.assertFalse(any("TweaksForever" in finding for finding in findings))
        self.assertFalse(any("Questie" in finding for finding in findings))
        self.assertFalse(any("mappins" in finding for finding in findings))

    def test_compare_uses_the_last_common_mark_label(self):
        report = perf.build_report(
            session=self.session(),
            session_index=1,
            session_count=2,
            saved_variables=perf.saved_variable_sizes(self.wtf),
            smoke=self.sources.smoke,
            compare_session=self.session(2),
            compare_index=2,
        )
        assert report.compare is not None
        self.assertEqual(report.compare.mark, "after-selftest")
        rows = {row.name: row for row in report.compare.rows}
        guide = rows["AdventureGuideForever"]
        self.assertEqual(guide.avg_ms, 1.0)
        self.assertEqual(guide.peak_ms, 2.5)
        self.assertEqual(guide.over5_ms, 0.0)
        self.assertEqual(guide.over10_ms, 0.0)
        self.assertEqual(guide.over50_ms, 0.0)
        self.assertEqual(guide.memory_mb, 0.0)

    def test_text_names_the_sections_and_findings(self):
        status, output, error = run_main("--wtf", str(self.wtf), "--compare", "2")
        self.assertEqual(status, 0)
        self.assertEqual(error, "")
        for heading in ("Load", "SavedVariables", "Mark 'after-selftest'", "Interval", "Combat", "WFA-13 findings"):
            self.assertIn(heading, output)
        self.assertIn("LegacyForever /lf", output)
        self.assertIn("Compare session 2", output)
        self.assertIn("AdventureGuideForever", output)

    def test_text_names_scenarios_and_skips_the_one_without_a_map(self):
        status, output, error = run_main("--wtf", str(self.wtf), "--session", "2")
        self.assertEqual(status, 0)
        self.assertEqual(error, "")
        self.assertIn("Scenarios", output)
        self.assertIn("Scenario 'tooltips'", output)
        self.assertIn("Scenario 'mappins'", output)
        self.assertIn("skipped: no world map", output)
        self.assertIn("tooltip set", output)
        self.assertIn("PEAK RAISED", output)
        self.assertIn("OVER 3MS", output)

    def test_json_includes_scenarios(self):
        status, output, error = run_main("--wtf", str(self.wtf), "--session", "2", "--json")
        self.assertEqual(status, 0)
        self.assertEqual(error, "")
        scenarios = json.loads(output)["session"]["scenarios"]
        self.assertEqual([scenario["name"] for scenario in scenarios], ["tooltips", "mappins"])
        self.assertEqual(scenarios[0]["frames"], 120)
        self.assertEqual(scenarios[0]["kinds"]["tooltip set"]["max_ms"], 3.6)
        self.assertTrue(scenarios[0]["addons"]["AdventureGuideForever"]["peak_raised"])
        self.assertEqual(scenarios[0]["addons"]["AdventureGuideForever"]["memory_delta_kb"], 2048.0)
        self.assertEqual(scenarios[1]["skipped"], "no world map")

    def test_json_is_one_object_with_every_section(self):
        status, output, error = run_main("--wtf", str(self.wtf), "--json")
        self.assertEqual(status, 0)
        self.assertEqual(error, "")
        report = json.loads(output)
        self.assertEqual(report["session"]["character"], "Newchar")
        self.assertEqual(report["session_count"], 2)
        self.assertEqual(len(report["session"]["marks"]), 3)
        self.assertEqual(report["session"]["marks"][1]["label"], "after-selftest")
        self.assertEqual(report["intervals"][0]["before"], "login")
        self.assertEqual(report["smoke"]["build"], "1.60.1.70124")
        self.assertTrue(any(row["first_ms"] > perf.BUDGET_MS for row in report["smoke"]["results"]))
        self.assertTrue(any(row["name"] == "AdventureGuideForever.lua" for row in report["saved_variables"]))
        self.assertTrue(all(isinstance(path, str) for row in report["saved_variables"] for path in row["paths"]))
        self.assertTrue(any("peak 4.5 ms" in finding for finding in report["findings"]))

    def test_session_index_counts_from_newest(self):
        status, output, _ = run_main("--wtf", str(self.wtf), "--session", "2", "--json")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["session"]["character"], "Oldchar")
        status, _, error = run_main("--wtf", str(self.wtf), "--session", "3")
        self.assertEqual(status, 2)
        self.assertIn("does not exist", error)


class MissingPerfTest(unittest.TestCase):
    def test_no_devperfdb_names_the_dev_addon(self):
        with tempfile.TemporaryDirectory() as directory:
            wtf = Path(directory) / "WTF"
            write(wtf / "Account" / "1" / "SavedVariables" / "!!DevSmoke.lua", 'DevSmokeDB = { ["runs"] = {} }')
            status, output, error = run_main("--wtf", str(wtf))
            self.assertEqual(status, 1)
            self.assertEqual(output, "")
            self.assertIn("no DevPerfDB found", error)
            self.assertIn("!!DevPerf", error)

    def test_json_missing_devperfdb_is_an_error_object(self):
        with tempfile.TemporaryDirectory() as directory:
            status, output, _ = run_main("--wtf", str(Path(directory) / "WTF"), "--json")
            self.assertEqual(status, 1)
            self.assertIn("no DevPerfDB found", json.loads(output)["error"])


if __name__ == "__main__":
    unittest.main()
