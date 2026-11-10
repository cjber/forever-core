"""The suite's asset blacklist, independent of aspect-ratio helpers and waivers.

Runtime Lua/XML and Python renderers use the Forever atlas set. Loose legacy frame chrome
and templates which select it are forbidden, even inside an Art helper.
"""

import argparse
import ast
import html
import re
from pathlib import Path

from . import legacy_chrome
from .lua import LONG_OPEN, tokenize
from .toc import runtime_files

APPROVED_BUTTON_TEMPLATES = frozenset(
    {"SharedButtonTemplate", "SharedButtonSmallTemplate", "SharedButtonLargeTemplate", "SharedButtonExtraSmallTemplate"}
)
LEGACY_BUTTON_TEMPLATES = frozenset(
    {
        # Virtual descendants from the pinned Forever FrameXML, including texture templates.
        "AuctionHouseDialogButtonTemplate",
        "AuctionHouseSearchButtonTemplate",
        "BankFramePurchaseButton",
        "BankPanelMoneyFrameButtonTemplate",
        "CalendarEventButtonTemplate",
        "CalendarMassInviteArenaButtonTemplate",
        "CalendarViewEventRSVPButtonTemplate",
        "ClassTalentLoadoutDialogButtonTemplate",
        "CommunitiesInviteButtonTemplate",
        "CommunitiesSettingsButtonTemplate",
        "CreateChannelPopupButtonTemplate",
        "CurrencyTransferCancelButtonTemplate",
        "CurrencyTransferConfirmButtonTemplate",
        "CurrencyTransferToggleButtonTemplate",
        "EditModeDialogButton",
        "EditModeManagerFrameButtonTemplate",
        "EditModeSystemSettingsDialogButtonTemplate",
        "EditModeSystemSettingsDialogExtraButtonTemplate",
        "FriendsFrameButtonTemplate",
        "FriendsFrameButtonTemplate_BottomLeft",
        "FriendsFrameButtonTemplate_BottomRight",
        "GameMenuButtonTemplate",
        "HousingDashboard_HouseFinderButtonTemplate",
        "LFGListMagicButtonTemplate",
        "LFGStartGroupButtonTemplate",
        "MagicButtonTemplate",
        "PlayerChoiceBaseOptionButtonTemplate",
        "PlayerChoiceBaseSmallerOptionButtonTemplate",
        "StartMissionButtonTemplate",
        "UIPanelBorderedButtonTemplate",
        "UIPanelButtonDisabledTexture",
        "UIPanelButtonDownTexture",
        "UIPanelButtonHighlightTexture",
        "UIPanelButtonUpTexture",
        "UIPanelLargeSilverButton",
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
# Named indirections verified in the pinned Forever FrameXML, including virtual descendants.
LEGACY_CHROME_TEMPLATES = frozenset(
    {
        "AddFriendButtonTemplate",
        "AdventuresRewardsScreenTemplate",
        "AuthChallengeButtonTemplate",
        "CRFManagerFilterButtonTemplate",
        "DialogBorderDarkTemplate",
        "DialogBorderTemplate",
        "DialogBoxFrame",
        "DialogButtonDisabledTexture",
        "DialogButtonHighlightTexture",
        "DialogButtonNormalTexture",
        "DialogButtonPushedTexture",
        "IslandsQueueScreenDifficultySelector",
        "QuestSessionDialogButtonTemplate",
        "SecureDialogBorderDarkTemplate",
        "SecureDialogBorderTemplate",
        "SecureTransferButtonTemplate",
        "StaticPopupButtonTemplate",
        "StoreButtonSmallTemplate",
        "TableAttributeDisplayTemplate",
        "UIPanelButtonDisabledDownTexture",
        "WowTokenButtonTemplate",
    }
)
# These are loose pre-atlas chrome families, not content icons in Interface/Icons.
LEGACY_LOOSE = re.compile(
    r"^interface/(?:buttons/ui-(?:panel-button|silverbuttonlg|dialogbox-(?:button|goldbutton))"
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
# A client texture path: `Interface\...` or `interface/...`, either slash, any case. The optional
# `|T` prefix is inline texture markup; `:16|t` and punctuation after the path are left out.
CLIENT_PATH = re.compile(r"(?i)(?<![a-z0-9_/])(?:\|T)?interface[\\/]+[^\s\"'|:,;()<>\[\]{}`]+")
# An addon's own `Interface\AddOns\<addon>\media\...` path is not a client file; the package check
# owns it. Only the client's own art lives under the rest of `interface/`.
ADDONS_PREFIX = "interface/addons/"
# The profession crafting bar reads as the crafting cast bar wherever it is reused as a generic progress bar.
CRAFTING_PROGRESS_BAR = re.compile(r"^profession-progressbar-(?:bg|frame)$", re.IGNORECASE)


def _old_problem(value: str) -> str | None:
    """The named-family rules that predate the FileDataID age rule."""
    normal = re.sub(r"/+", "/", value.replace("\\", "/"))
    for template in normal.split(","):
        if template.strip() in LEGACY_BUTTON_TEMPLATES:
            return "legacy button template; use SharedButtonSmallTemplate (Forever atlas set 1)"
        if template.strip() in LEGACY_CHROME_TEMPLATES:
            return "legacy chrome template; use the approved Forever atlas/template family"
    if re.match(r"^_?128-GoldRedButton|^(?:SharedGoldRed|BigGoldRedThreeSlice)", normal, re.I):
        return "shop button family; use SharedButtonSmallTemplate and the set-1 128-RedButton atlas"
    if LEGACY_LOOSE.match(normal) or re.match(
        r"^ui-(?:panel-button|silverbuttonlg|dialogbox-(?:button|goldbutton))", normal, re.I
    ):
        return "legacy loose chrome; use the approved Forever atlas/template family"
    if EXPANSION_CHROME.match(normal):
        return "expansion chrome is outside the approved Forever asset set"
    if CRAFTING_PROGRESS_BAR.match(normal):
        return (
            "profession crafting bar art reads as a casting bar; use the approved native progress bar instead "
            "(a StatusBar filled with common-stat-bar-white over common-stat-bar-BG)"
        )
    for markup in re.finditer(r"\|(?:T|A:)([^:|]+)", value):
        if reason := _old_problem(markup[1]):
            return reason
    return None


def _client_findings(value: str) -> list[tuple[str, str]]:
    """The age rule and its unverifiable-path fallback, one finding per client path in `value`."""
    findings = []
    for match in CLIENT_PATH.finditer(value):
        candidate = match.group(0)
        if candidate[:2].upper() == "|T":
            candidate = candidate[2:]
        candidate = candidate.rstrip(".")
        path = legacy_chrome.normalise(candidate)
        if path == "interface/addons" or path.startswith(ADDONS_PREFIX):
            continue
        if path.endswith("/") or not path.rsplit("/", 1)[-1]:
            continue
        # A constant prefix being built into a path (`UI-BonusObjectiveBlob-`) is not a path yet.
        if path.endswith(("-", "_")) and not legacy_chrome.is_legacy(path):
            continue
        if not legacy_chrome.is_known(path) and not legacy_chrome.is_legacy(path):
            if legacy_chrome.is_path_prefix(path):
                continue
        if reason := legacy_chrome.reason(path):
            findings.append((path, reason))
    return findings


def findings(value: str) -> list[tuple[str, str]]:
    """(subject, reason) for every forbidden thing in one literal. A client path gets the age rule's
    answer first, even when a named family would also match; the age rule names the path so an inline
    `|T...|t` reports the path, not the whole markup. A backdrop global is the client files it names,
    so each of those gets the same age rule."""
    backdrop = legacy_chrome.backdrop_paths(value)
    if backdrop:
        return [(path, reason) for path in backdrop if (reason := legacy_chrome.reason(path))]
    found = _client_findings(value)
    if found:
        return found
    if reason := _old_problem(value):
        return [(value, reason)]
    return []


def problem(value: str) -> str | None:
    """Explain why one literal asset reference is forbidden."""
    found = findings(value)
    return found[0][1] if found else None


def references(source: str, suffix: str) -> list[tuple[int, str]]:
    """Read literals and known backdrop identifiers, excluding comments; retain f-string fragments."""
    if suffix == ".py":
        tree = ast.parse(source)
        values = [
            (node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]

        values.extend(
            (node.lineno, node.id)
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id in legacy_chrome.backdrops()
        )

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
        source = re.sub(
            r"(<!\[CDATA\[[\s\S]*?\]\]>|<!--[\s\S]*?-->)",
            lambda match: match[1] if match[1].startswith("<![CDATA[") else "\n" * match[0].count("\n"),
            source,
        )
        attribute_source = re.sub(r"<!\[CDATA\[[\s\S]*?\]\]>", lambda match: "\n" * match[0].count("\n"), source)
        attribute_source = re.sub(
            r"(<On[A-Za-z0-9_]+\b[^>]*>)([\s\S]*?)(</On[A-Za-z0-9_]+\s*>)",
            lambda match: match[1] + "\n" * match[2].count("\n") + match[3],
            attribute_source,
        )
        values = [
            (attribute_source.count("\n", 0, match.start()) + 1, html.unescape(match[2]))
            for match in re.finditer(
                r"\b(?:atlas|file|bgFile|edgeFile|inherits|text|value)\s*=\s*([\"'])([\s\S]*?)\1",
                attribute_source,
            )
        ]
        for match in re.finditer(r"<On[A-Za-z0-9_]+\b[^>]*>([\s\S]*?)</On[A-Za-z0-9_]+\s*>", source):
            offset = source.count("\n", 0, match.start(1))
            parts = re.split(r"(<!\[CDATA\[[\s\S]*?\]\]>)", match[1])
            body = "".join(part[9:-3] if part.startswith("<![CDATA[") else html.unescape(part) for part in parts)
            values.extend((line + offset, value) for line, value in references(body, ".lua"))
        return values
    values = []
    tokens = tokenize(source)[0]
    for index, token in enumerate(tokens):
        if token.kind == "name" and token.text in legacy_chrome.backdrops():
            values.append((token.line, token.text))
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
            (line, f"asset-blacklist: {subject}: {reason}")
            for line, value in references(source, suffix)
            for subject, reason in findings(value)
        }
    )


def renderer_files(root: Path) -> list[Path]:
    """Renderer entry points, including the shared renderer's own implementation."""
    tools = root / "tools"
    active = [path for path in (tools / "micro_menu_render.py", tools / "rarity.py") if path.is_file()]
    return sorted(
        {
            *tools.glob("*screenshots*.py"),
            *tools.glob("*mockups*.py"),
            *active,
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
