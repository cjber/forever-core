"""Read the !!DevPerf profiler and !!DevSmoke timing runs from the client's SavedVariables.

The private dev addon `!!DevPerf` writes `DevPerfDB` into the account's SavedVariables. Each session holds the load
timeline, the marks taken with `/forever perf <label>`, the hover scenarios, the combat summary and, when the heap
watch was on, the heap range. `!!DevSmoke` writes `DevSmokeDB` beside it, with the slowest and cold time of every
`/forever selftest` surface.

    python3 tools/forever_perf.py
    python3 tools/forever_perf.py --session 2
    python3 tools/forever_perf.py --compare 2
    python3 tools/forever_perf.py --json

The report is read only: WFA-13 findings are printed but never fail the exit status.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from forever_errors import DEFAULT_WTF, FOLDERS, LuaSyntaxError, load_lua, table_values

BUDGET_MS = 3.0
OVER_METRICS = (
    "CountTimeOver1Ms",
    "CountTimeOver5Ms",
    "CountTimeOver10Ms",
    "CountTimeOver50Ms",
    "CountTimeOver100Ms",
)


# --------------------------------------------------------------------------------------------------
# SavedVariables shapes


@dataclass(frozen=True)
class Addon:
    name: str
    version: str
    ours: bool


@dataclass(frozen=True)
class LoadedAddon:
    name: str
    ms: float


@dataclass(frozen=True)
class Load:
    file_ms: float | None
    entering_world_ms: float | None
    loading_ms: float | None
    reload: bool
    addons: tuple[LoadedAddon, ...]


@dataclass(frozen=True)
class Context:
    quest_log_entries: int | None
    map_id: int | None
    free_bag_slots: int | None


@dataclass(frozen=True)
class Stats:
    metrics: dict[str, float]
    memory_kb: float | None


@dataclass(frozen=True)
class Mark:
    label: str
    at: float | None
    clock: float | None
    ms: float | None
    overall: dict[str, float]
    application: dict[str, float]
    addons: dict[str, Stats]


@dataclass(frozen=True)
class KindCost:
    count: int | None
    total_ms: float | None
    max_ms: float | None


@dataclass(frozen=True)
class ScenarioAddon:
    metrics: dict[str, float]
    peak_raised: bool
    over: dict[str, float]
    memory_delta_kb: float | None


@dataclass(frozen=True)
class Scenario:
    name: str
    at: float | None
    frames: int | None
    wall_ms: float | None
    skipped: str | None
    kinds: dict[str, KindCost]
    addons: dict[str, ScenarioAddon]


@dataclass(frozen=True)
class Combat:
    fights: int
    seconds: float
    peak_raised: dict[str, float]
    over: dict[str, dict[str, float]]


@dataclass(frozen=True)
class Heap:
    samples: int
    min_kb: float
    max_kb: float
    collected_kb: float


@dataclass(frozen=True)
class Session:
    started: float | None
    build: str
    build_number: int | None
    interface: int | None
    character: str
    level: int | None
    profiler: bool
    addons: tuple[Addon, ...]
    load: Load
    context: Context
    marks: tuple[Mark, ...]
    scenarios: tuple[Scenario, ...]
    combat: Combat
    heap: Heap | None


@dataclass(frozen=True)
class SmokeSurface:
    surface: str
    ms: float | None
    first_ms: float | None
    ok: bool | None


@dataclass(frozen=True)
class SmokeRun:
    started: float | None
    build: str
    results: tuple[SmokeSurface, ...]


@dataclass(frozen=True)
class Sources:
    sessions: tuple[Session, ...]
    smoke: SmokeRun | None
    warnings: tuple[str, ...]
    found_perf: bool


@dataclass(frozen=True)
class SavedVariable:
    name: str
    kb: float
    paths: tuple[Path, ...]
    ours: bool


@dataclass(frozen=True)
class MarkRow:
    name: str
    ours: bool
    avg_ms: float | None
    recent_ms: float | None
    peak_ms: float | None
    over5_ms: float | None
    over10_ms: float | None
    over50_ms: float | None
    memory_mb: float | None


@dataclass(frozen=True)
class ScenarioRow:
    name: str
    ours: bool
    recent_ms: float | None
    peak_ms: float | None
    peak_raised: bool
    over1_ms: float | None
    over5_ms: float | None
    over10_ms: float | None
    memory_mb: float | None


@dataclass(frozen=True)
class IntervalRow:
    name: str
    ours: bool
    over1_ms: float | None
    over5_ms: float | None
    over10_ms: float | None
    over50_ms: float | None
    over100_ms: float | None
    memory_mb: float | None


@dataclass(frozen=True)
class Interval:
    before: str
    after: str
    rows: tuple[IntervalRow, ...]


@dataclass(frozen=True)
class CompareRow:
    name: str
    ours: bool
    avg_ms: float | None
    peak_ms: float | None
    over5_ms: float | None
    over10_ms: float | None
    over50_ms: float | None
    memory_mb: float | None


@dataclass(frozen=True)
class Compare:
    session_index: int
    mark: str | None
    rows: tuple[CompareRow, ...]


@dataclass(frozen=True)
class Report:
    session: Session
    session_index: int
    session_count: int
    saved_variables: tuple[SavedVariable, ...]
    intervals: tuple[Interval, ...]
    smoke: SmokeRun | None
    findings: tuple[str, ...]
    compare: Compare | None


# --------------------------------------------------------------------------------------------------
# Reading the client's files


def _table(value: object) -> dict[object, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _integer(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (dict, list, tuple)):
        return ""
    return str(value)


def _flag(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _metrics(value: object) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, item in _table(value).items():
        number = _number(item)
        if isinstance(key, str) and number is not None:
            metrics[key] = number
    return metrics


def parse_stats(value: object) -> Stats:
    table = _table(value)
    return Stats(metrics=_metrics(table), memory_kb=_number(table.get("memoryKB")))


def parse_mark(value: object) -> Mark:
    table = _table(value)
    addons: dict[str, Stats] = {}
    for name, stats in _table(table.get("addons")).items():
        if isinstance(name, str):
            addons[name] = parse_stats(stats)
    return Mark(
        label=_text(table.get("label")),
        at=_number(table.get("at")),
        clock=_number(table.get("clock")),
        ms=_number(table.get("ms")),
        overall=_metrics(table.get("overall")),
        application=_metrics(table.get("application")),
        addons=addons,
    )


def parse_load(value: object) -> Load:
    table = _table(value)
    addons: list[LoadedAddon] = []
    for entry in table_values(table.get("addonLoaded")):
        if not isinstance(entry, dict):
            continue
        name = _text(entry.get("name"))
        ms = _number(entry.get("ms"))
        if name and ms is not None:
            addons.append(LoadedAddon(name, ms))
    return Load(
        file_ms=_number(table.get("fileMs")),
        entering_world_ms=_number(table.get("enteringWorldMs")),
        loading_ms=_number(table.get("loadingMs")),
        reload=_flag(table.get("reload")),
        addons=tuple(addons),
    )


def parse_context(value: object) -> Context:
    table = _table(value)
    return Context(
        quest_log_entries=_integer(table.get("questLogEntries")),
        map_id=_integer(table.get("mapID")),
        free_bag_slots=_integer(table.get("freeBagSlots")),
    )


def parse_combat(value: object) -> Combat:
    table = _table(value)
    peak_raised: dict[str, float] = {}
    for name, ms in _table(table.get("peakRaised")).items():
        number = _number(ms)
        if isinstance(name, str) and number is not None:
            peak_raised[name] = number
    over: dict[str, dict[str, float]] = {}
    for name, metrics in _table(table.get("over")).items():
        if isinstance(name, str):
            over[name] = _metrics(metrics)
    return Combat(
        fights=_integer(table.get("fights")) or 0,
        seconds=_number(table.get("seconds")) or 0.0,
        peak_raised=peak_raised,
        over=over,
    )


def parse_heap(value: object) -> Heap | None:
    table = _table(value)
    if not table:
        return None
    return Heap(
        samples=_integer(table.get("samples")) or 0,
        min_kb=_number(table.get("minKB")) or 0.0,
        max_kb=_number(table.get("maxKB")) or 0.0,
        collected_kb=_number(table.get("collectedKB")) or 0.0,
    )


def parse_kind_cost(value: object) -> KindCost:
    table = _table(value)
    return KindCost(
        count=_integer(table.get("count")),
        total_ms=_number(table.get("totalMs")),
        max_ms=_number(table.get("maxMs")),
    )


def parse_scenario_addon(value: object) -> ScenarioAddon:
    table = _table(value)
    return ScenarioAddon(
        metrics=_metrics(table),
        peak_raised=_flag(table.get("peakRaised")),
        over=_metrics(table.get("over")),
        memory_delta_kb=_number(table.get("memoryDeltaKB")),
    )


def parse_scenario(value: object) -> Scenario:
    table = _table(value)
    kinds: dict[str, KindCost] = {}
    for name, cost in _table(table.get("kinds")).items():
        if isinstance(name, str):
            kinds[name] = parse_kind_cost(cost)
    addons: dict[str, ScenarioAddon] = {}
    for name, stats in _table(table.get("addons")).items():
        if isinstance(name, str):
            addons[name] = parse_scenario_addon(stats)
    return Scenario(
        name=_text(table.get("name")),
        at=_number(table.get("at")),
        frames=_integer(table.get("frames")),
        wall_ms=_number(table.get("wallMs")),
        skipped=_text(table.get("skipped")) or None,
        kinds=kinds,
        addons=addons,
    )


def parse_session(value: object) -> Session:
    table = _table(value)
    addons: list[Addon] = []
    for entry in table_values(table.get("addons")):
        if not isinstance(entry, dict):
            continue
        name = _text(entry.get("name"))
        if name:
            addons.append(Addon(name=name, version=_text(entry.get("version")), ours=_flag(entry.get("ours"))))
    marks = [parse_mark(mark) for mark in table_values(table.get("marks")) if isinstance(mark, dict)]
    scenarios = [
        parse_scenario(scenario) for scenario in table_values(table.get("scenarios")) if isinstance(scenario, dict)
    ]
    return Session(
        started=_number(table.get("started")),
        build=_text(table.get("build")),
        build_number=_integer(table.get("buildNumber")),
        interface=_integer(table.get("interface")),
        character=_text(table.get("character")),
        level=_integer(table.get("level")),
        profiler=_flag(table.get("profiler"), True),
        addons=tuple(addons),
        load=parse_load(table.get("load")),
        context=parse_context(table.get("context")),
        marks=tuple(marks),
        scenarios=tuple(scenarios),
        combat=parse_combat(table.get("combat")),
        heap=parse_heap(table.get("heap")),
    )


def parse_smoke_run(value: object) -> SmokeRun:
    table = _table(value)
    results: list[SmokeSurface] = []
    for entry in table_values(table.get("results")):
        if not isinstance(entry, dict):
            continue
        surface = _text(entry.get("surface"))
        if not surface:
            continue
        ok = entry.get("ok")
        results.append(
            SmokeSurface(
                surface=surface,
                ms=_number(entry.get("ms")),
                first_ms=_number(entry.get("firstMs")),
                ok=ok if isinstance(ok, bool) else None,
            )
        )
    return SmokeRun(started=_number(table.get("started")), build=_text(table.get("build")), results=tuple(results))


def newest_smoke(runs: Sequence[SmokeRun]) -> SmokeRun | None:
    if not runs:
        return None
    return max(
        enumerate(runs),
        key=lambda pair: (pair[1].started is not None, pair[1].started or 0.0, pair[0]),
    )[1]


def load_sources(wtf: Path) -> Sources:
    """Every DevPerfDB session and DevSmokeDB run under the client's WTF folder."""
    sessions: list[Session] = []
    runs: list[SmokeRun] = []
    warnings: list[str] = []
    found_perf = False
    for path in sorted(wtf.rglob("SavedVariables/*.lua")):
        try:
            variables = load_lua(path)
        except (OSError, LuaSyntaxError) as error:
            warnings.append(f"{path}: {error}")
            continue
        perf = variables.get("DevPerfDB")
        if isinstance(perf, dict):
            found_perf = True
            sessions.extend(
                parse_session(item) for item in table_values(perf.get("sessions")) if isinstance(item, dict)
            )
        smoke = variables.get("DevSmokeDB")
        if isinstance(smoke, dict):
            runs.extend(parse_smoke_run(item) for item in table_values(smoke.get("runs")) if isinstance(item, dict))
    sessions.sort(key=lambda session: (session.started is None, session.started or 0.0))
    return Sources(
        sessions=tuple(sessions),
        smoke=newest_smoke(runs),
        warnings=tuple(warnings),
        found_perf=found_perf,
    )


def saved_variable_sizes(wtf: Path) -> tuple[SavedVariable, ...]:
    """Every SavedVariables Lua file, summed per addon file name and largest first."""
    grouped: dict[str, list[Path]] = {}
    for path in sorted(wtf.rglob("SavedVariables/*.lua")):
        try:
            path.stat()
        except OSError:
            continue
        grouped.setdefault(path.name, []).append(path)
    rows: list[SavedVariable] = []
    for name, paths in grouped.items():
        try:
            size = sum(path.stat().st_size for path in paths)
        except OSError:
            continue
        rows.append(
            SavedVariable(
                name=name,
                kb=size / 1024,
                paths=tuple(paths),
                ours=name.removesuffix(".lua") in FOLDERS,
            )
        )
    rows.sort(key=lambda row: (-row.kb, row.name.lower()))
    return tuple(rows)


# --------------------------------------------------------------------------------------------------
# Derived views


def is_ours(session: Session, name: str) -> bool:
    for addon in session.addons:
        if addon.name == name:
            return addon.ours
    return name in FOLDERS


def session_gaps(session: Session) -> list[tuple[str, float]]:
    """Each ADDON_LOADED gap from the previous one, so a row is that file's run and SavedVariables parse."""
    gaps: list[tuple[str, float]] = []
    previous = session.load.file_ms or 0.0
    for addon in session.load.addons:
        gaps.append((addon.name, addon.ms - previous))
        previous = addon.ms
    return gaps


def mark_rows(mark: Mark, session: Session) -> list[MarkRow]:
    rows = [
        MarkRow(
            name=name,
            ours=is_ours(session, name),
            avg_ms=stats.metrics.get("SessionAverageTime"),
            recent_ms=stats.metrics.get("RecentAverageTime"),
            peak_ms=stats.metrics.get("PeakTime"),
            over5_ms=stats.metrics.get("CountTimeOver5Ms"),
            over10_ms=stats.metrics.get("CountTimeOver10Ms"),
            over50_ms=stats.metrics.get("CountTimeOver50Ms"),
            memory_mb=None if stats.memory_kb is None else stats.memory_kb / 1024,
        )
        for name, stats in mark.addons.items()
    ]
    rows.sort(key=lambda row: (not row.ours, -(row.avg_ms or 0.0), row.name.lower()))
    return rows


def scenario_rows(scenario: Scenario, session: Session) -> list[ScenarioRow]:
    rows = [
        ScenarioRow(
            name=name,
            ours=is_ours(session, name),
            recent_ms=stats.metrics.get("RecentAverageTime"),
            peak_ms=stats.metrics.get("PeakTime"),
            peak_raised=stats.peak_raised,
            over1_ms=stats.over.get("CountTimeOver1Ms"),
            over5_ms=stats.over.get("CountTimeOver5Ms"),
            over10_ms=stats.over.get("CountTimeOver10Ms"),
            memory_mb=None if stats.memory_delta_kb is None else stats.memory_delta_kb / 1024,
        )
        for name, stats in scenario.addons.items()
    ]
    rows.sort(key=lambda row: (not row.ours, -(row.recent_ms or 0.0), row.name.lower()))
    return rows


def _metric_delta(before: Stats | None, after: Stats | None, metric: str) -> float | None:
    old = before.metrics.get(metric) if before is not None else None
    new = after.metrics.get(metric) if after is not None else None
    if old is None or new is None:
        return None
    return new - old


def _memory_delta(before: Stats | None, after: Stats | None) -> float | None:
    if before is None or after is None or before.memory_kb is None or after.memory_kb is None:
        return None
    return (after.memory_kb - before.memory_kb) / 1024


def interval_rows(before: Mark, after: Mark, session: Session) -> list[IntervalRow]:
    rows: list[IntervalRow] = []
    for name in set(before.addons) | set(after.addons):
        old = before.addons.get(name)
        new = after.addons.get(name)
        rows.append(
            IntervalRow(
                name=name,
                ours=is_ours(session, name),
                over1_ms=_metric_delta(old, new, "CountTimeOver1Ms"),
                over5_ms=_metric_delta(old, new, "CountTimeOver5Ms"),
                over10_ms=_metric_delta(old, new, "CountTimeOver10Ms"),
                over50_ms=_metric_delta(old, new, "CountTimeOver50Ms"),
                over100_ms=_metric_delta(old, new, "CountTimeOver100Ms"),
                memory_mb=_memory_delta(old, new),
            )
        )
    rows.sort(key=lambda row: (not row.ours, -(row.over5_ms or 0.0), row.name.lower()))
    return rows


def last_common_marks(session: Session, other: Session) -> tuple[Mark, Mark] | None:
    """The last mark label both sessions share, paired as (session, other)."""
    other_by_label = {mark.label: mark for mark in other.marks}
    for mark in reversed(session.marks):
        if mark.label in other_by_label:
            return mark, other_by_label[mark.label]
    return None


def compare_rows(session: Session, mark: Mark, other_mark: Mark) -> list[CompareRow]:
    rows: list[CompareRow] = []
    for name in set(mark.addons) | set(other_mark.addons):
        new = mark.addons.get(name)
        old = other_mark.addons.get(name)
        rows.append(
            CompareRow(
                name=name,
                ours=is_ours(session, name),
                avg_ms=_metric_delta(old, new, "SessionAverageTime"),
                peak_ms=_metric_delta(old, new, "PeakTime"),
                over5_ms=_metric_delta(old, new, "CountTimeOver5Ms"),
                over10_ms=_metric_delta(old, new, "CountTimeOver10Ms"),
                over50_ms=_metric_delta(old, new, "CountTimeOver50Ms"),
                memory_mb=_memory_delta(old, new),
            )
        )
    rows.sort(key=lambda row: (not row.ours, -(abs(row.avg_ms or 0.0)), row.name.lower()))
    return rows


def _scenario_findings(session: Session) -> list[str]:
    """Our addons over the recent or peak budget in a scenario, and every kind whose worst call was over it."""
    findings: list[str] = []
    for scenario in session.scenarios:
        if scenario.skipped:
            continue
        for name, stats in sorted(scenario.addons.items()):
            if not is_ours(session, name):
                continue
            recent = stats.metrics.get("RecentAverageTime")
            peak = stats.metrics.get("PeakTime")
            reasons: list[str] = []
            if recent is not None and recent > 1.0:
                reasons.append(f"recent {recent:.1f} ms")
            if stats.peak_raised and peak is not None and peak > BUDGET_MS:
                reasons.append(f"peak {peak:.1f} ms raised")
            if reasons:
                findings.append(f"scenario {scenario.name!r}: {name} {', '.join(reasons)}")
        for kind, cost in sorted(scenario.kinds.items()):
            if cost.max_ms is not None and cost.max_ms > BUDGET_MS:
                findings.append(f"scenario {scenario.name!r}: kind {kind!r} max {cost.max_ms:.1f} ms")
    return findings


def wfa13_findings(session: Session, smoke: SmokeRun | None) -> list[str]:
    """Ours over the per-frame budget at a mark, in a scenario or at a kind, and every smoke surface over it.

    PeakTime and the over-budget counts are cumulative for the client session, so an addon repeats the same peak
    at every later mark. Report each of ours once, from the newest mark that has it.
    """
    findings: list[str] = []
    seen: set[str] = set()
    for mark in reversed(session.marks):
        for name, stats in mark.addons.items():
            if name in seen:
                continue
            seen.add(name)
            peak = stats.metrics.get("PeakTime")
            if is_ours(session, name) and peak is not None and peak > BUDGET_MS:
                findings.append(f"mark {mark.label!r}: {name} peak {peak:.1f} ms")
    if smoke is not None:
        for result in smoke.results:
            slow = [
                f"{label} {value:.1f} ms"
                for label, value in (("ms", result.ms), ("firstMs", result.first_ms))
                if value is not None and value > BUDGET_MS
            ]
            if slow:
                findings.append(f"smoke {result.surface!r}: {', '.join(slow)}")
    findings.extend(_scenario_findings(session))
    return findings


def build_report(
    session: Session,
    session_index: int,
    session_count: int,
    saved_variables: Sequence[SavedVariable],
    smoke: SmokeRun | None,
    compare_session: Session | None = None,
    compare_index: int | None = None,
) -> Report:
    intervals = tuple(
        Interval(before.label, after.label, tuple(interval_rows(before, after, session)))
        for before, after in zip(session.marks[:-1], session.marks[1:], strict=True)
    )
    comparison: Compare | None = None
    if compare_session is not None and compare_index is not None:
        common = last_common_marks(session, compare_session)
        if common is None:
            comparison = Compare(session_index=compare_index, mark=None, rows=())
        else:
            mark, other_mark = common
            comparison = Compare(
                session_index=compare_index,
                mark=mark.label,
                rows=tuple(compare_rows(session, mark, other_mark)),
            )
    return Report(
        session=session,
        session_index=session_index,
        session_count=session_count,
        saved_variables=tuple(saved_variables),
        intervals=intervals,
        smoke=smoke,
        findings=tuple(wfa13_findings(session, smoke)),
        compare=comparison,
    )


# --------------------------------------------------------------------------------------------------
# Text


def _time_text(value: float | None) -> str:
    return "-" if value is None else datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _count(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _signed(value: float | None) -> str:
    return "-" if value is None else f"{value:+.1f}"


def _mb(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _table_text(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    material = [tuple(row) for row in rows]
    if not material:
        return ["  (none)"]
    widths = [max(len(row[index]) for row in (tuple(header), *material)) for index in range(len(header))]
    lines = []
    for row in (tuple(header), *material):
        lines.append("  ".join(cell[:width].ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip())
    return lines


def _header_text(session: Session) -> list[str]:
    build = session.build or "-"
    level = "-" if session.level is None else str(session.level)
    loaded = len(session.load.addons) or len(session.addons)
    context_parts: list[str] = []
    if session.context.quest_log_entries is not None:
        context_parts.append(f"{session.context.quest_log_entries} quest log entries")
    if session.context.map_id is not None:
        context_parts.append(f"map {session.context.map_id}")
    if session.context.free_bag_slots is not None:
        context_parts.append(f"{session.context.free_bag_slots} free bag slots")
    kind = "reload" if session.load.reload else "cold login"
    lines = [
        f"{session.character or 'unknown character'} level {level}, build {build}",
        f"Started {_time_text(session.started)} ({kind})",
        f"Loaded addons: {loaded}",
        f"Context: {', '.join(context_parts) or '-'}",
    ]
    if not session.profiler:
        lines.append("Profiler: unavailable")
    return lines


def _load_text(report: Report) -> list[str]:
    load = report.session.load
    gaps = session_gaps(report.session)
    gaps.sort(key=lambda item: (-item[1], item[0].lower()))
    rows = [(name, _ms(gap), "yes" if is_ours(report.session, name) else "-") for name, gap in gaps[:10]]
    lines = [
        "",
        "Load",
        f"  loading {_ms(load.loading_ms)} ms, file {_ms(load.file_ms)} ms, "
        f"entering world {_ms(load.entering_world_ms)} ms",
    ]
    lines.extend(_table_text(("ADDON", "GAP MS", "OURS"), rows))
    return lines


def _saved_variables_text(report: Report) -> list[str]:
    total = sum(row.kb for row in report.saved_variables)
    rows = [(row.name, f"{row.kb:.1f}", "yes" if row.ours else "-") for row in report.saved_variables[:10]]
    lines = ["", "SavedVariables size", f"  {len(report.saved_variables)} file(s), {total:.1f} KB"]
    lines.extend(_table_text(("FILE", "KB", "OURS"), rows))
    return lines


def _mark_text(report: Report) -> list[str]:
    lines: list[str] = []
    for mark in report.session.marks:
        lines.extend(
            [
                "",
                f"Mark {mark.label!r} at {_time_text(mark.at)} clock {_ms(mark.clock)} ms",
            ]
        )
        rows = [
            (
                row.name,
                _ms(row.avg_ms),
                _ms(row.recent_ms),
                _ms(row.peak_ms),
                _count(row.over5_ms),
                _count(row.over10_ms),
                _count(row.over50_ms),
                _mb(row.memory_mb),
                "yes" if row.ours else "-",
            )
            for row in mark_rows(mark, report.session)
        ]
        lines.extend(
            _table_text(
                ("ADDON", "AVG MS", "RECENT MS", "PEAK MS", "OVER 5", "OVER 10", "OVER 50", "MEM MB", "OURS"),
                rows,
            )
        )
    for interval in report.intervals:
        lines.extend(["", f"Interval {interval.before!r} -> {interval.after!r}"])
        rows = [
            (
                row.name,
                _signed(row.over1_ms),
                _signed(row.over5_ms),
                _signed(row.over10_ms),
                _signed(row.over50_ms),
                _signed(row.over100_ms),
                _signed(row.memory_mb),
                "yes" if row.ours else "-",
            )
            for row in interval.rows
        ]
        lines.extend(
            _table_text(("ADDON", "OVER 1", "OVER 5", "OVER 10", "OVER 50", "OVER 100", "MEM MB", "OURS"), rows)
        )
    return lines


def _scenario_text(report: Report) -> list[str]:
    lines = ["", "Scenarios"]
    if not report.session.scenarios:
        lines.append("  (none)")
        return lines
    for scenario in report.session.scenarios:
        detail = f"  Scenario {scenario.name!r} at {_time_text(scenario.at)}"
        if scenario.frames is not None:
            detail += f", {scenario.frames} frame(s)"
        if scenario.wall_ms is not None:
            detail += f", {_ms(scenario.wall_ms)} ms"
        lines.append(detail)
        if scenario.skipped:
            lines.append(f"    skipped: {scenario.skipped}")
            continue
        kind_rows = []
        for kind, cost in sorted(scenario.kinds.items(), key=lambda item: (-(item[1].max_ms or 0.0), item[0].lower())):
            mean = None if cost.total_ms is None or not cost.count else cost.total_ms / cost.count
            over = cost.max_ms is not None and cost.max_ms > BUDGET_MS
            kind_rows.append((kind, _count(cost.count), _ms(mean), _ms(cost.max_ms), "yes" if over else "-"))
        lines.extend(_table_text(("KIND", "COUNT", "MEAN MS", "MAX MS", "OVER 3MS"), kind_rows))
        rows = [
            (
                row.name,
                _ms(row.recent_ms),
                _ms(row.peak_ms),
                "yes" if row.peak_raised else "-",
                _count(row.over1_ms),
                _count(row.over5_ms),
                _count(row.over10_ms),
                _mb(row.memory_mb),
                "yes" if row.ours else "-",
            )
            for row in scenario_rows(scenario, report.session)
        ]
        lines.extend(
            _table_text(
                ("ADDON", "RECENT MS", "PEAK MS", "PEAK RAISED", "OVER 1", "OVER 5", "OVER 10", "MEM MB", "OURS"),
                rows,
            )
        )
    return lines


def _combat_rows(session: Session) -> list[tuple[str, str, str, str, str, str, str, str]]:
    names = set(session.combat.over) | set(session.combat.peak_raised)
    rows = []
    for name in names:
        metrics = session.combat.over.get(name, {})
        rows.append(
            (
                name,
                _count(metrics.get("CountTimeOver1Ms")),
                _count(metrics.get("CountTimeOver5Ms")),
                _count(metrics.get("CountTimeOver10Ms")),
                _count(metrics.get("CountTimeOver50Ms")),
                _count(metrics.get("CountTimeOver100Ms")),
                _ms(session.combat.peak_raised.get(name)),
                "yes" if is_ours(session, name) else "-",
            )
        )
    rows.sort(key=lambda row: (row[7] != "yes", row[0].lower()))
    return rows


def _combat_text(report: Report) -> list[str]:
    combat = report.session.combat
    lines = ["", "Combat", f"  {combat.fights} fight(s), {combat.seconds:.1f} s"]
    lines.extend(
        _table_text(
            ("ADDON", "OVER 1", "OVER 5", "OVER 10", "OVER 50", "OVER 100", "PEAK MS", "OURS"),
            _combat_rows(report.session),
        )
    )
    return lines


def _heap_text(report: Report) -> list[str]:
    heap = report.session.heap
    if heap is None:
        return []
    return [
        "",
        "Heap",
        f"  {heap.samples} sample(s), {_ms(heap.min_kb)}-{_ms(heap.max_kb)} KB, collected {_ms(heap.collected_kb)} KB",
    ]


def _smoke_text(report: Report) -> list[str]:
    smoke = report.smoke
    lines = ["", "Smoke"]
    if smoke is None:
        lines.append("  DevSmoke: no runs")
        return lines
    build = f", build {smoke.build}" if smoke.build else ""
    lines.append(f"  DevSmoke run {_time_text(smoke.started)}{build}")
    rows = []
    for result in smoke.results:
        over = any(value is not None and value > BUDGET_MS for value in (result.ms, result.first_ms))
        rows.append((result.surface, _ms(result.ms), _ms(result.first_ms), "yes" if over else "-"))
    lines.extend(_table_text(("SURFACE", "MS", "FIRST MS", "OVER 3MS"), rows))
    return lines


def _findings_text(report: Report) -> list[str]:
    lines = ["", "WFA-13 findings"]
    if not report.findings:
        lines.append("  none")
    else:
        lines.extend(f"  - {finding}" for finding in report.findings)
    return lines


def _compare_text(report: Report) -> list[str]:
    compare = report.compare
    if compare is None:
        return []
    lines = ["", f"Compare session {compare.session_index} (newer minus older)"]
    if compare.mark is None:
        lines.append("  no common mark label")
        return lines
    lines.append(f"  mark {compare.mark!r}")
    rows = [
        (
            row.name,
            _signed(row.avg_ms),
            _signed(row.peak_ms),
            _signed(row.over5_ms),
            _signed(row.over10_ms),
            _signed(row.over50_ms),
            _signed(row.memory_mb),
            "yes" if row.ours else "-",
        )
        for row in compare.rows
    ]
    lines.extend(_table_text(("ADDON", "AVG MS", "PEAK MS", "OVER 5", "OVER 10", "OVER 50", "MEM MB", "OURS"), rows))
    return lines


def render_text(report: Report) -> str:
    lines = [f"Session {report.session_index} of {report.session_count} (1 is newest)"]
    lines.extend(_header_text(report.session))
    lines.extend(_load_text(report))
    lines.extend(_saved_variables_text(report))
    lines.extend(_mark_text(report))
    lines.extend(_scenario_text(report))
    lines.extend(_combat_text(report))
    lines.extend(_heap_text(report))
    lines.extend(_smoke_text(report))
    lines.extend(_findings_text(report))
    lines.extend(_compare_text(report))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------
# JSON


def _json_default(value: object) -> object:
    """asdict leaves a Path in place; json writes tuples as lists itself."""
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def report_json(report: Report, wtf: Path) -> dict[str, object]:
    return {"wtf": str(wtf), **asdict(report)}


# --------------------------------------------------------------------------------------------------
# Command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wtf", type=Path, default=DEFAULT_WTF, help="the client's WTF folder")
    parser.add_argument(
        "--session",
        type=int,
        default=1,
        metavar="N",
        help="session index from newest, 1 = newest (default: 1)",
    )
    parser.add_argument(
        "--compare",
        type=int,
        metavar="N",
        help="diff this session index from newest against the chosen session",
    )
    parser.add_argument("--json", action="store_true", help="print the whole report as one JSON object")
    return parser


def _pick(sessions: Sequence[Session], index: int, label: str) -> Session | None:
    if 1 <= index <= len(sessions):
        return sessions[-index]
    print(f"{label} {index} does not exist: {len(sessions)} session(s) found", file=sys.stderr)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    sources = load_sources(arguments.wtf)
    for warning in sources.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not sources.sessions:
        if sources.found_perf:
            message = f"DevPerfDB has no sessions under {arguments.wtf}"
        else:
            message = f"no DevPerfDB found under {arguments.wtf}: install and enable !!DevPerf, play, then /reload"
        if arguments.json:
            print(json.dumps({"error": message}))
        else:
            print(message, file=sys.stderr)
        return 1
    session = _pick(sources.sessions, arguments.session, "session")
    if session is None:
        return 2
    compare_session = None
    if arguments.compare is not None:
        compare_session = _pick(sources.sessions, arguments.compare, "compare session")
        if compare_session is None:
            return 2
    report = build_report(
        session=session,
        session_index=arguments.session,
        session_count=len(sources.sessions),
        saved_variables=saved_variable_sizes(arguments.wtf),
        smoke=sources.smoke,
        compare_session=compare_session,
        compare_index=arguments.compare,
    )
    if arguments.json:
        print(json.dumps(report_json(report, arguments.wtf), indent=2, default=_json_default))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
