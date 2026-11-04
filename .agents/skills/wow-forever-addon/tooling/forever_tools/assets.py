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
LEGACY_BACKDROPS = frozenset(
    {
        "BACKDROP_CHARACTER_CREATE_TOOLTIP_32_32",
        "BACKDROP_DARK_DIALOG_32_32",
        "BACKDROP_DIALOG_32_32",
        "BACKDROP_DIALOG_EDGE_32",
        "BACKDROP_GOLD_DIALOG_32_32",
        "BACKDROP_MISTS_CHARACTER_CREATE_TOOLTIP_32_32",
        "BACKDROP_TUTORIAL_16_16",
        "BACKDROP_WATERMARK_DIALOG_0_16",
        "BACKDROP_WRATH_CHARACTER_CREATE_TOOLTIP_32_32",
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


def problem(value: str) -> str | None:
    """Explain why one literal asset reference is forbidden."""
    normal = re.sub(r"/+", "/", value.replace("\\", "/"))
    for template in normal.split(","):
        if template.strip() in LEGACY_BUTTON_TEMPLATES:
            return "legacy button template; use SharedButtonSmallTemplate (Forever atlas set 1)"
        if template.strip() in LEGACY_CHROME_TEMPLATES:
            return "legacy chrome template; use the approved Forever atlas/template family"
    if normal in LEGACY_BACKDROPS:
        return "legacy backdrop global; use the approved Forever atlas/template family"
    if re.match(r"^_?128-GoldRedButton|^(?:SharedGoldRed|BigGoldRedThreeSlice)", normal, re.I):
        return "shop button family; use SharedButtonSmallTemplate and the set-1 128-RedButton atlas"
    if LEGACY_LOOSE.match(normal) or re.match(
        r"^ui-(?:panel-button|silverbuttonlg|dialogbox-(?:button|goldbutton))", normal, re.I
    ):
        return "legacy loose chrome; use the approved Forever atlas/template family"
    if EXPANSION_CHROME.match(normal):
        return "expansion chrome is outside the approved Forever asset set"
    for markup in re.finditer(r"\|(?:T|A:)([^:|]+)", value):
        if reason := problem(markup[1]):
            return reason
    return None


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
            if isinstance(node, ast.Name) and node.id in LEGACY_BACKDROPS
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
        source = re.sub(r"<!--.*?-->", lambda match: "\n" * match[0].count("\n"), source, flags=re.DOTALL)
        return [
            (source.count("\n", 0, match.start()) + 1, match[2])
            for match in re.finditer(r"\b(?:atlas|file|bgFile|edgeFile|inherits|value)\s*=\s*([\"'])(.*?)\1", source)
        ]
    values = []
    tokens = tokenize(source)[0]
    for index, token in enumerate(tokens):
        if token.kind == "name" and token.text in LEGACY_BACKDROPS:
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
            (line, f"asset-blacklist: {value}: {reason}")
            for line, value in references(source, suffix)
            if (reason := problem(value))
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
