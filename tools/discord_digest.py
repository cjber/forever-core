"""Build and post the Forever addons' Discord release digest.

The payload builders are pure: they take release, changelog and store-link data and return Discord webhook payload
dicts. The fetch and post functions are the only code that touches the network, so a different poster can reuse the
builders.

    python3 tools/discord_digest.py --mode digest --dry-run
    python3 tools/discord_digest.py --mode features --now 2026-11-07T18:00:00Z
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OWNER = "cjber"
USER_AGENT = "forever-core-discord-digest"
WEBHOOK_USERNAME = "Forever Addons"

DIGEST_WINDOW = timedelta(hours=24)
FEATURE_WINDOW = timedelta(hours=1)
MAX_EMBEDS = 10
MAX_DESCRIPTION = 4096
MAX_EMBED_TEXT = 6000
MAX_DIGEST_LINES = 4
HTTP_TIMEOUT = 30


@dataclass(frozen=True)
class Addon:
    repo: str
    name: str
    accent: int


# The table order is the order the digest lists addons in.
ADDONS = (
    Addon("adventure-guide-forever", "Adventure Guide Forever", 0xE8A33A),
    Addon("shortest-path-forever", "Shortest Path Forever", 0x3DA5E8),
    Addon("skillup-forever", "SkillUp Forever", 0xF0743C),
    Addon("tweaks-forever", "Tweaks Forever", 0x46C06A),
    Addon("legacy-forever", "Legacy Forever", 0xA77BE8),
    Addon("field-guide-forever", "Field Guide Forever", 0xD3577F),
)


def emblem_url(addon):
    """The borderless emblem, for the spots Discord crops to a circle."""
    return f"https://raw.githubusercontent.com/{OWNER}/forever-core/main/docs/discord/{addon.repo}.png"


def icon_url(addon):
    """The framed icon, for the feature post's square thumbnail."""
    return f"https://raw.githubusercontent.com/{OWNER}/{addon.repo}/main/media/icon-400.png"


def image_url(addon, path):
    return f"https://raw.githubusercontent.com/{OWNER}/{addon.repo}/main/{path.removeprefix('./').lstrip('/')}"


def notes_url(addon, version):
    return f"https://github.com/{OWNER}/{addon.repo}/releases/tag/v{version}"


@dataclass(frozen=True)
class Release:
    version: str
    published: datetime
    feature: bool = False


@dataclass(frozen=True)
class ChangelogEntry:
    headlines: tuple[str, ...] = ()
    image: str | None = None


@dataclass(frozen=True)
class AddonData:
    addon: Addon
    releases: tuple[Release, ...]
    changelog: Mapping[str, ChangelogEntry]
    store: Mapping[str, str]


@dataclass
class PlannedEmbed:
    """An embed whose description is rendered from bullet lines, so limits can trim lines but never links."""

    color: int
    author_name: str
    author_icon: str
    title: str
    url: str
    lines: tuple[str, ...]
    links: str
    thumbnail: str | None = None
    image: str | None = None
    visible: int | None = None

    def render(self):
        shown = self.lines if self.visible is None else self.lines[: max(self.visible, 0)]
        hidden = len(self.lines) - len(shown)
        parts = list(shown)
        if hidden > 0:
            parts.append(f"+{hidden} more")
        description = "\n".join(parts)
        if self.links:
            description = f"{description}\n\n{self.links}" if description else self.links
        embed = {
            "color": self.color,
            "author": {"name": self.author_name, "icon_url": self.author_icon},
            "title": self.title,
            "url": self.url,
            "description": description,
        }
        if self.thumbnail:
            embed["thumbnail"] = {"url": self.thumbnail}
        if self.image:
            embed["image"] = {"url": self.image}
        return embed


_VERSION = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")
_HEADING = re.compile(r"^##\s+\[([^\]]+)\]")
_IMAGE_COMMENT = re.compile(r"^\s*<!--\s*discord-image:\s*(\S+)\s*-->\s*$")
_PLAYER_BULLET = re.compile(r"^-\s+\*\*(.+?)\*\*")
_CURSE_ID = re.compile(r"^##\s*X-Curse-Project-ID\s*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_WAGO_ID = re.compile(r"^##\s*X-Wago-ID\s*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)


def version_key(version):
    match = _VERSION.match(version.removeprefix("v"))
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def major_minor(version):
    major, minor, _patch = version_key(version)
    return f"{major}.{minor}"


def parse_time(value):
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def floor_hour(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def _release_key(release):
    return (release.published, version_key(release.version))


def classify_releases(releases):
    """Mark each release as a feature release when its major or minor number rises over the one before it.

    The oldest release has no predecessor, so it counts as a feature only when it starts a patch line (patch 0);
    otherwise a fetched list that begins mid-line would announce an ordinary patch as a feature.
    """
    ordered = sorted(releases, key=_release_key)
    classified = []
    previous = None
    for release in ordered:
        key = version_key(release.version)
        if previous is None:
            feature = key[2] == 0
        else:
            feature = key[0] > previous[0] or (key[0] == previous[0] and key[1] > previous[1])
        classified.append(replace(release, feature=feature))
        previous = key
    return classified


def parse_changelog(text):
    entries = {}
    current = None
    headlines = []
    image = None
    collecting = False

    def store():
        if current is not None:
            entries[current] = ChangelogEntry(tuple(headlines), image)

    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            store()
            name = heading.group(1).strip()
            current = None if name.lower() == "unreleased" else name.removeprefix("v")
            headlines = []
            image = None
            collecting = current is not None
            continue
        if current is None:
            continue
        picture = _IMAGE_COMMENT.match(line)
        if picture:
            image = picture.group(1)
            continue
        if line.startswith("### "):
            collecting = False
            continue
        if collecting:
            bullet = _PLAYER_BULLET.match(line)
            if bullet:
                headlines.append(bullet.group(1).strip())
    store()
    return entries


def parse_store_links(text):
    links = {}
    curse = _CURSE_ID.search(text)
    if curse:
        links["curseforge"] = f"https://www.curseforge.com/projects/{curse.group(1)}"
    wago = _WAGO_ID.search(text)
    if wago:
        links["wago"] = f"https://addons.wago.io/addons/{wago.group(1)}"
    return links


def links_line(store, notes):
    parts = []
    if store.get("curseforge"):
        parts.append(f"[CurseForge]({store['curseforge']})")
    if store.get("wago"):
        parts.append(f"[Wago]({store['wago']})")
    parts.append(f"[Full notes]({notes})")
    return " · ".join(parts)


def _shrink(spec):
    current = len(spec.lines) if spec.visible is None else spec.visible
    if current <= 0:
        return False
    spec.visible = current - 1
    return True


def embed_text_length(embed):
    return len(embed["author"]["name"]) + len(embed["title"]) + len(embed["description"])


def fit_embeds(specs):
    for spec in specs:
        while len(spec.render()["description"]) > MAX_DESCRIPTION and _shrink(spec):
            pass
    while sum(embed_text_length(spec.render()) for spec in specs) > MAX_EMBED_TEXT:
        if not any(_shrink(spec) for spec in reversed(specs)):
            break
    return specs


def _date_label(moment):
    return f"{moment:%A} {moment.day} {moment:%B}"


def _count(noun, count):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _window(releases, since, now):
    return [release for release in releases if since <= release.published < now]


def _newest(releases):
    return max(releases, key=_release_key)


def _digest_spec(data, since, now, backfill=False):
    window = _window(data.releases, since, now)
    if not window:
        return None
    newest = _newest(window)
    earlier = [release for release in data.releases if release.published < since]
    previous = _newest(earlier) if earlier else None
    title = f"v{previous.version} → v{newest.version}" if previous else f"v{newest.version}"
    lines = []
    for release in sorted(window, key=_release_key, reverse=True):
        entry = data.changelog.get(release.version)
        headlines = entry.headlines if entry else ()
        if release.feature and not backfill:
            if headlines:
                lines.append(f"• New in {major_minor(release.version)}: see the post above")
        else:
            lines.extend(f"• {headline}" for headline in headlines)
    if not lines:
        return None
    spec = PlannedEmbed(
        color=data.addon.accent,
        author_name=data.addon.name,
        author_icon=emblem_url(data.addon),
        title=title,
        url=notes_url(data.addon, newest.version),
        lines=tuple(lines),
        links=links_line(data.store, notes_url(data.addon, newest.version)),
        visible=min(MAX_DIGEST_LINES, len(lines)),
    )
    return spec, len(window)


def build_digest(datasets, since, now, backfill=False):
    """Return the daily digest payload, or None when no addon has a player line in the window."""
    planned = []
    for data in datasets:
        result = _digest_spec(data, since, now, backfill)
        if result is not None:
            planned.append(result)
    planned = planned[:MAX_EMBEDS]
    if not planned:
        return None
    specs = fit_embeds([spec for spec, _count in planned])
    releases = sum(count for _spec, count in planned)
    addons = len(planned)
    if backfill:
        heading = f"**Updates since {_date_label(since)}**"
    else:
        heading = f"**Today's updates · {_date_label(now)}**"
    content = (
        f"{heading}\n{_count('release', releases)} across {_count('addon', addons)}. "
        "Update in your addon manager, then `/reload`."
    )
    return {"content": content, "embeds": [spec.render() for spec in specs]}


def build_features(datasets, since, now):
    """Return one payload per feature release published in the window, in addon table order."""
    payloads = []
    for data in datasets:
        window = _window(data.releases, since, now)
        for release in sorted(
            (item for item in window if item.feature),
            key=_release_key,
            reverse=True,
        ):
            entry = data.changelog.get(release.version) or ChangelogEntry()
            spec = PlannedEmbed(
                color=data.addon.accent,
                author_name=data.addon.name,
                author_icon=emblem_url(data.addon),
                title=f"v{release.version} · What's new",
                url=notes_url(data.addon, release.version),
                lines=tuple(f"• {headline}" for headline in entry.headlines),
                links=links_line(data.store, notes_url(data.addon, release.version)),
                thumbnail=icon_url(data.addon),
                image=image_url(data.addon, entry.image) if entry.image else None,
            )
            fit_embeds([spec])
            payloads.append(
                {
                    "content": f"**New in {data.addon.name} {major_minor(release.version)}**",
                    "embeds": [spec.render()],
                }
            )
    return payloads


def webhook_payload(payload):
    body = dict(payload)
    body["username"] = WEBHOOK_USERNAME
    body["avatar_url"] = emblem_url(ADDONS[0])
    body["allowed_mentions"] = {"parse": []}
    return body


def _get(url, token=None, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.read().decode("utf-8")


def _get_json(url, token=None):
    value = json.loads(_get(url, token))
    if not isinstance(value, list):
        raise ValueError("expected a JSON list")
    return value


def fetch_releases(addon, token=None):
    url = f"https://api.github.com/repos/{OWNER}/{addon.repo}/releases?per_page=50"
    releases = []
    for item in _get_json(url, token):
        if item.get("draft") or item.get("prerelease"):
            continue
        tag = str(item.get("tag_name") or "").strip()
        if not tag or not item.get("published_at"):
            continue
        releases.append(Release(tag.removeprefix("v"), parse_time(item["published_at"])))
    return releases


def fetch_changelog(addon, token=None):
    url = f"https://raw.githubusercontent.com/{OWNER}/{addon.repo}/main/CHANGELOG.md"
    return parse_changelog(_get(url, token, accept="text/plain"))


def _toc_url(addon, token):
    listing = _get_json(f"https://api.github.com/repos/{OWNER}/{addon.repo}/contents?ref=main", token)
    for item in listing:
        if item.get("type") == "file" and str(item.get("name", "")).endswith(".toc"):
            return item["download_url"]
    raise ValueError("no root .toc file")


def fetch_store_links(addon, token=None):
    return parse_store_links(_get(_toc_url(addon, token), token, accept="text/plain"))


def load_addon(addon, token=None):
    releases = classify_releases(fetch_releases(addon, token))
    return AddonData(addon, tuple(releases), fetch_changelog(addon, token), fetch_store_links(addon, token))


def collect_datasets(token=None):
    datasets = []
    for addon in ADDONS:
        try:
            datasets.append(load_addon(addon, token))
        except Exception as error:  # one repo's network or data failure must not drop the rest
            print(f"discord-digest: skipping {addon.repo}: {error}", file=sys.stderr)
    return datasets


def post(webhook, payload):
    separator = "&" if "?" in webhook else "?"
    request = Request(
        f"{webhook}{separator}wait=true",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            response.read()
    except HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        print(f"discord-digest: post failed with {error.code}: {body}", file=sys.stderr)
        return 1
    except URLError as error:
        print(f"discord-digest: post failed: {error.reason}", file=sys.stderr)
        return 1
    return 0


def _payloads(args, now, token):
    since = parse_time(args.since) if args.since else now - DIGEST_WINDOW
    datasets = collect_datasets(token)
    if args.mode == "digest":
        payload = build_digest(datasets, since, now, backfill=bool(args.since))
        return [payload] if payload else []
    return build_features(datasets, now - FEATURE_WINDOW, now)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Post the Forever addons' release digest to Discord.")
    parser.add_argument("--mode", choices=("digest", "features"), required=True)
    parser.add_argument("--now", help="window end as an ISO time; defaults to the current UTC hour")
    parser.add_argument("--since", help="digest window start as an ISO time")
    parser.add_argument("--dry-run", action="store_true", help="print the payload instead of posting it")
    args = parser.parse_args(argv)

    now = parse_time(args.now) if args.now else floor_hour(datetime.now(timezone.utc))
    token = os.environ.get("GITHUB_TOKEN")
    payloads = _payloads(args, now, token)
    if not payloads:
        return 0

    webhook = os.environ.get("DISCORD_ANNOUNCE_WEBHOOK")
    if args.dry_run or not webhook:
        for payload in payloads:
            print(json.dumps(webhook_payload(payload), ensure_ascii=False))
        return 0
    for payload in payloads:
        status = post(webhook, webhook_payload(payload))
        if status:
            return status
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
