"""The suite's asset blacklist, independent of aspect-ratio helpers and waivers.

Runtime Lua/XML and Python renderers use the Forever atlas set. Loose legacy frame chrome
and templates which select it are forbidden, even inside an Art helper.
"""

import argparse
import ast
import re
from pathlib import Path

from .lua import LONG_OPEN, tokenize
from .toc import runtime_files

APPROVED_BUTTON_TEMPLATES = frozenset(
    {"SharedButtonTemplate", "SharedButtonSmallTemplate", "SharedButtonLargeTemplate", "SharedButtonExtraSmallTemplate"}
)
LEGACY_BUTTON_TEMPLATES = frozenset(
    {
        "UIPanelButtonTemplate",
        "UIPanelButtonNoTooltipTemplate",
        "UIPanelButtonGrayTemplate",
        "UIPanelGoldButtonTemplate",
        "UIPanelDynamicResizeButtonTemplate",
        "UIPanelButtonHeightScaledTemplate",
        "UIPanelButtonUserScaledTemplate",
        "UIPanelButtonNoTooltipResizeToFitTemplate",
    }
)
# These are loose pre-atlas chrome families, not content icons in Interface/Icons.
LEGACY_LOOSE = re.compile(
    r"^interface/(?:buttons/ui-(?:panel-button|dialogbox-(?:button|goldbutton))"
    r"|dialogframe/ui-dialogbox|tooltips/ui-tooltip-(?:border|background)"
    r"|framegeneral/ui-border|characterframe/ui-character-border)",
    re.IGNORECASE,
)
EXPANSION_CHROME = re.compile(
    r"^_?(?:garr(?:mission|building|follower|ability)|classhall[_-]|orderhall[_-]"
    r"|covenant[_-]|covenantsanctum|soulbinds?[_-]|warfront[_-]|housing[_-]"
    r"|shop-|pvpqueue|pvptalents|dragonriding|plunderstorm|eyeofthejailer)",
    re.IGNORECASE,
)


def problem(value: str) -> str | None:
    """Explain why one literal asset reference is forbidden."""
    normal = re.sub(r"/+", "/", value.replace("\\", "/"))
    for template in normal.split(","):
        if template.strip() in LEGACY_BUTTON_TEMPLATES:
            return "legacy button template; use SharedButtonSmallTemplate (Forever atlas set 1)"
    if re.match(r"^_?128-GoldRedButton|^(?:SharedGoldRed|BigGoldRedThreeSlice)", normal, re.I):
        return "shop button family; use SharedButtonSmallTemplate and the set-1 128-RedButton atlas"
    if LEGACY_LOOSE.match(normal) or re.match(r"^ui-(?:panel-button|dialogbox-(?:button|goldbutton))", normal, re.I):
        return "legacy loose chrome; use the approved Forever atlas/template family"
    if EXPANSION_CHROME.match(normal):
        return "expansion chrome is outside the approved Forever asset set"
    for markup in re.finditer(r"\|[TA]([^:|]+)", value):
        if reason := problem(markup[1]):
            return reason
    return None


def literals(source: str, suffix: str) -> list[tuple[int, str]]:
    """Read literals without treating comments as references; retain f-string fragments."""
    if suffix == ".py":
        tree = ast.parse(source)
        values = [
            (node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]

        def constant(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                left, right = constant(node.left), constant(node.right)
                if left is not None and right is not None:
                    return left + right
            return None

        values.extend(
            (node.lineno, value)
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp) and (value := constant(node)) is not None
        )
        return values
    if suffix == ".xml":
        source = re.sub(r"<!--.*?-->", lambda match: "\n" * match[0].count("\n"), source, flags=re.DOTALL)
        return [
            (source.count("\n", 0, match.start()) + 1, match[2])
            for match in re.finditer(r"\b(?:atlas|file|inherits|value)\s*=\s*([\"'])(.*?)\1", source)
        ]
    values = []
    tokens = tokenize(source)[0]
    for index, token in enumerate(tokens):
        if token.kind != "string":
            continue
        opening = LONG_OPEN.match(token.text)
        value = token.text[opening.end() : -len(opening[0])] if opening else token.text[1:-1]
        values.append((token.line, value))
        # Constant concatenation must not hide a forbidden path or template name.
        cursor = index + 1
        while cursor + 1 < len(tokens) and tokens[cursor].text == ".." and tokens[cursor + 1].kind == "string":
            following = tokens[cursor + 1].text
            opening = LONG_OPEN.match(following)
            value += following[opening.end() : -len(opening[0])] if opening else following[1:-1]
            values.append((token.line, value))
            cursor += 2
    return values


def check(source: str, suffix: str = ".lua") -> list[tuple[int, str]]:
    return sorted(
        {
            (line, f"asset-blacklist: {value}: {reason}")
            for line, value in literals(source, suffix)
            if (reason := problem(value))
        }
    )


def renderer_files(root: Path) -> list[Path]:
    """Renderer entry points, including the shared renderer's own implementation."""
    tools = root / "tools"
    return sorted(
        {
            *tools.glob("*screenshots*.py"),
            *tools.glob("*mockups*.py"),
            *tools.glob("wowmock/wowmock.py"),
        }
    )


def run(files: list[Path]) -> int:
    failed = False
    for path in sorted(set(files)):
        for line, message in check(path.read_text(encoding="utf-8"), path.suffix):
            print(f"{path}:{line}: {message}")
            failed = True
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = parser.parse_args().root.resolve()
    xml = [
        path
        for path in root.rglob("*.xml")
        if not any(
            part.startswith(".") or part in {"tools", "tests", "node_modules"} for part in path.relative_to(root).parts
        )
    ]
    return run([*runtime_files(root), *xml, *renderer_files(root)])


if __name__ == "__main__":
    raise SystemExit(main())
