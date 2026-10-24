"""Semantic change reports for generated Lua data: what a regeneration added, removed or changed, by key.

A byte diff of a generated file says lines moved. This reads both versions as tables and reports only what the
data itself establishes: keyed records added, removed or changed (with the changed fields), sources and builds
named in the header, header counts the generator wrote, and key references that no longer resolve. Positional
lists have no identity, so they are reported as whole entries present on one side only, never as line counts.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .luadata import IDENTIFIER, LuaDataError, Table, parse_tables

EXAMPLES = 8
CHANGES_PER_RECORD = 4
BUILD = re.compile(r"\b\d+\.\d+\.\d+\.\d+\b")
REVISION = re.compile(r"\b[0-9a-f]{40}\b")


@dataclass(frozen=True)
class Hint:
    """How to read one table: `fields` names the positions of each record's values, and `key` is the position that
    identifies a record when the table is an array of records."""

    fields: tuple[str, ...] = ()
    key: int | None = None


@dataclass(frozen=True)
class Subset:
    """Every key of table `source` must be a key of table `target`; `meaning` states why the dataset requires it."""

    source: str
    target: str
    meaning: str


def brief(value: object, limit: int = 60) -> str:
    def render(item: object) -> str:
        if isinstance(item, Table):
            parts = [render(v) for v in item.array] + [f"{k}={render(v)}" for k, v in item.keyed.items()]
            return "{" + ", ".join(parts) + "}"
        return repr(item) if isinstance(item, str) else str(item).lower() if isinstance(item, bool) else str(item)

    text = render(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def kind(table: Table) -> str:
    if not table.keyed:
        return "list"
    if all(isinstance(key, str) and IDENTIFIER.fullmatch(key) for key in table.keyed):
        return "sections"
    return "records"


def sort_key(key: object) -> tuple[int, str]:
    return (0, f"{key:020}") if isinstance(key, int) and key >= 0 else (1, repr(key))


def changes(old: object, new: object, fields: tuple[str, ...] = (), prefix: str = "", depth: int = 0) -> list[str]:
    """The differing leaves of two values as `path old -> new`."""
    if isinstance(old, Table) and isinstance(new, Table) and depth < 4:
        out: list[str] = []
        for index in range(max(len(old.array), len(new.array))):
            label = fields[index] if depth == 0 and index < len(fields) else f"[{index + 1}]"
            path = f"{prefix}.{label}" if prefix and not label.startswith("[") else f"{prefix}{label}"
            if index >= len(old.array) or index >= len(new.array):
                side = "added" if index >= len(old.array) else "removed"
                out.append(f"{path} {side} {brief(new.array[index] if side == 'added' else old.array[index], 30)}")
            else:
                out += changes(old.array[index], new.array[index], fields, path, depth + 1)
        for key in sorted(old.keyed.keys() | new.keyed.keys(), key=sort_key):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in old.keyed:
                out.append(f"{path} added {brief(new.keyed[key], 30)}")
            elif key not in new.keyed:
                out.append(f"{path} removed")
            else:
                out += changes(old.keyed[key], new.keyed[key], fields, path, depth + 1)
        return out
    return [] if old == new else [f"{prefix or 'value'} {brief(old, 30)} -> {brief(new, 30)}"]


def fields_of(table: Table) -> tuple[str, ...] | int | None:
    """The record shape of a keyed table: the field names every record shares, an arity for uniform positional
    records, or None when the records vary (so no schema claim is made)."""
    shapes = set()
    for value in table.keyed.values():
        if not isinstance(value, Table):
            return None
        shapes.add(tuple(sorted(map(str, value.keyed))) if value.keyed else len(value.array))
    return next(iter(shapes)) if len(shapes) == 1 else None


def record_lines(path: str, old: Table, new: Table, fields: tuple[str, ...]) -> list[str]:
    added = sorted(new.keyed.keys() - old.keyed.keys(), key=sort_key)
    removed = sorted(old.keyed.keys() - new.keyed.keys(), key=sort_key)
    changed = sorted((k for k in old.keyed.keys() & new.keyed.keys() if old.keyed[k] != new.keyed[k]), key=sort_key)
    if not (added or removed or changed or old.array != new.array):
        return []
    lines = [
        f"- `{path}`: {len(old.keyed)} -> {len(new.keyed)} keyed records "
        f"(+{len(added)} added, -{len(removed)} removed, {len(changed)} changed)"
    ]
    for sign, keys, source in (("+", added, new), ("-", removed, old)):
        lines += [f"  {sign} {key}: {brief(source.keyed[key])}" for key in keys[:EXAMPLES]]
        if len(keys) > EXAMPLES:
            lines.append(f"  {sign} ... {len(keys) - EXAMPLES} more")
    for key in changed[:EXAMPLES]:
        found = changes(old.keyed[key], new.keyed[key], fields)
        shown = "; ".join(found[:CHANGES_PER_RECORD]) + (
            f"; ... {len(found) - CHANGES_PER_RECORD} more" if len(found) > CHANGES_PER_RECORD else ""
        )
        lines.append(f"  ~ {key}: {shown}")
    if len(changed) > EXAMPLES:
        lines.append(f"  ~ ... {len(changed) - EXAMPLES} more changed")
    before_shape, after_shape = fields_of(old), fields_of(new)
    if before_shape is not None and after_shape is not None and before_shape != after_shape:
        lines.append(f"  record fields changed: {before_shape} -> {after_shape}")
    if old.array != new.array:
        lines.append("  positional entries beside the keys also differ")
    return lines


def keyed_array(table: Table, key: int) -> Table | None:
    """An array of records as a keyed table by each record's `key` position, or None if the key is not unique."""
    keyed: dict = {}
    for item in table.array:
        if not isinstance(item, Table) or key >= len(item.array) or item.array[key] in keyed:
            return None
        keyed[item.array[key]] = item
    return Table(keyed=keyed)


def list_lines(path: str, old: Table, new: Table) -> list[str]:
    if old.array == new.array:
        return []
    before, after = Counter(map(brief_full, old.array)), Counter(map(brief_full, new.array))
    gone, came = before - after, after - before
    lines = [
        f"- `{path}`: {len(old.array)} -> {len(new.array)} positional entries "
        f"({sum(came.values())} only in the new data, {sum(gone.values())} only in the old)"
    ]
    for sign, extra in (("+", came), ("-", gone)):
        lines += [f"  {sign} {text}" for text in list(extra)[:EXAMPLES]]
        if len(extra) > EXAMPLES:
            lines.append(f"  {sign} ... {len(extra) - EXAMPLES} more")
    return lines


def brief_full(value: object) -> str:
    return brief(value, 10_000)


def table_lines(path: str, old: Table, new: Table, hints: Mapping[str, Hint]) -> list[str]:
    hint = hints.get(path, Hint())
    if kind(old) == kind(new) == "sections":
        lines: list[str] = []
        for key in sorted(old.keyed.keys() | new.keyed.keys(), key=sort_key):
            child = f"{path}.{key}"
            before, after = old.keyed.get(key), new.keyed.get(key)
            if isinstance(before, Table) and isinstance(after, Table):
                lines += table_lines(child, before, after, hints)
            elif before != after:
                lines.append(f"- `{child}`: {brief(before, 40)} -> {brief(after, 40)}")
        return lines
    if kind(old) == kind(new) == "list" and hint.key is not None:
        keyed_old, keyed_new = keyed_array(old, hint.key), keyed_array(new, hint.key)
        if keyed_old is not None and keyed_new is not None:
            return record_lines(path, keyed_old, keyed_new, hint.fields)
    if kind(old) == "list" == kind(new):
        return list_lines(path, old, new)
    if "records" in {kind(old), kind(new)} or (old.keyed or new.keyed):
        return record_lines(path, old, new, hint.fields)
    return list_lines(path, old, new)


def provenance(before: list[str], after: list[str]) -> list[str]:
    lines = []
    for label, pattern in (("builds", BUILD), ("pinned revisions", REVISION)):
        old = sorted(set(pattern.findall("\n".join(before))))
        new = sorted(set(pattern.findall("\n".join(after))))
        if old != new:
            lines.append(f"- {label}: {', '.join(old) or 'none'} -> {', '.join(new) or 'none'}")
    old_facts, new_facts = (
        Counter(h for h in before if re.search(r"\d", h)),
        Counter(h for h in after if re.search(r"\d", h)),
    )
    for sign, extra in (("-", old_facts - new_facts), ("+", new_facts - old_facts)):
        lines += [f"- header {sign} {text}" for text in extra]
    return lines


def parse(text: str | None, name: str) -> tuple[dict[str, Table], list[str]] | str:
    """The file's tables and header, or a sentence saying why it was not read."""
    if text is None:
        return {}, []
    try:
        return parse_tables(text)
    except LuaDataError as error:
        return f"{name} was not read as Lua data ({error})"


def file_section(name: str, before: str | None, after: str | None, hints: Mapping[str, Hint]) -> list[str]:
    old, new = parse(before, name), parse(after, name)
    lines: list[str] = []
    if before is None:
        lines.append("- new file")
    elif after is None:
        lines.append("- file removed")
    if isinstance(old, str) or isinstance(new, str):
        sizes = f"{len((before or '').encode())} -> {len((after or '').encode())} bytes"
        return [*lines, f"- {old if isinstance(old, str) else new}; {sizes}"]
    (old_tables, old_header), (new_tables, new_header) = old, new
    lines += provenance(old_header, new_header)
    for path in sorted(old_tables.keys() | new_tables.keys()):
        before_table, after_table = old_tables.get(path), new_tables.get(path)
        if before_table is None or after_table is None:
            lines.append(f"- `{path}`: {'added' if after_table else 'removed'}")
        else:
            lines += table_lines(path, before_table, after_table, hints)
    return lines


def mixed_builds(contents: Mapping[str, str | None]) -> list[str]:
    """Builds of one client line (1.60, 1.15) named by different files of the same regeneration."""
    named: dict[str, dict[str, set[str]]] = {}
    for name, text in contents.items():
        for build in set(
            BUILD.findall("\n".join(parse_tables(text)[1]) if text and not isinstance(parse(text, name), str) else "")
        ):
            line = ".".join(build.split(".")[:2])
            named.setdefault(line, {}).setdefault(build, set()).add(name)
    return [
        f"- mixed builds of the {line} line: "
        + "; ".join(f"{build} in {', '.join(sorted(files))}" for build, files in sorted(builds.items()))
        for line, builds in sorted(named.items())
        if len(builds) > 1
    ]


def unresolved(contents: Mapping[str, str | None], subsets: Iterable[Subset]) -> dict[Subset, list[object]]:
    tables: dict[str, Table] = {}
    for name, text in contents.items():
        parsed = parse(text, name)
        if not isinstance(parsed, str):
            tables.update(parsed[0])
    result = {}
    for subset in subsets:
        source, target = tables.get(subset.source), tables.get(subset.target)
        if source is None or target is None:
            continue
        result[subset] = sorted(source.keyed.keys() - target.keyed.keys(), key=sort_key)
    return result


def reference_lines(files: Mapping[str, tuple[str | None, str | None]], subsets: Iterable[Subset]) -> list[str]:
    subsets = tuple(subsets)
    before = unresolved({name: pair[0] for name, pair in files.items()}, subsets)
    after = unresolved({name: pair[1] for name, pair in files.items()}, subsets)
    lines = []
    for subset, missing in after.items():
        if missing or before.get(subset):
            shown = ", ".join(map(str, missing[:EXAMPLES])) + (
                f", ... {len(missing) - EXAMPLES} more" if len(missing) > EXAMPLES else ""
            )
            lines.append(
                f"- {subset.source} keys missing from {subset.target} ({subset.meaning}): "
                f"{len(before.get(subset, []))} -> {len(missing)}" + (f": {shown}" if missing else "")
            )
    return lines


def build_report(
    files: Mapping[str, tuple[str | None, str | None]],
    hints: Mapping[str, Hint] | None = None,
    subsets: Iterable[Subset] = (),
) -> str:
    """Markdown for `{path: (old text, new text)}`; None marks a file absent on that side."""
    hints = hints or {}
    sections = []
    for name in sorted(files):
        before, after = files[name]
        if before != after:
            body = file_section(name, before, after, hints) or ["- text changed, but no table or header content did"]
            sections.append(f"### {name}\n" + "\n".join(body))
    checks = mixed_builds({name: pair[1] for name, pair in files.items()}) + reference_lines(files, subsets)
    if not sections and not checks:
        return "## Generated data changes\n\nNo generated Lua data changed."
    out = ["## Generated data changes", *sections]
    if checks:
        out.append("### Checks across the regenerated data\n" + "\n".join(checks))
    return "\n\n".join(out)
