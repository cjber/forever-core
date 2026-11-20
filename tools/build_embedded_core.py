"""Build schema-1 embedded or standalone inputs from ForeverCore's canonical TOC.

This produces one owned addon folder, not a release archive. Standalone mode
preserves ForeverCore metadata and wraps the same runtime with Begin/Seal. Embedded
mode emits no nested TOC or shared top-level addon.
The ready entry is explicitly converted consumer code: it receives addon, namespace,
core, resources as varargs at OnReady, after account SavedVariables load. Resources
provides the selected template name and explicit legacy/elected/standalone mode.
Only API2 with Register and TrackerLine is supported; legacy also requires
TrackerLine.SetInteractive and uses its original global template, which the ready step
names on the legacy facade when that older standalone left it unnamed, so consumer code
reads ForeverCore.TrackerLine.template in every mode. It must initialize directly rather
than wait for its already-finished ADDON_LOADED event.
"""

import argparse
import hashlib
import json
import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

SCHEMA = 1
API = 2
TEMPLATE = "ForeverTrackerInteractiveLineTemplate"


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise ValueError(f"expected an addon folder or Lua identifier, got {value!r}")
    return value


def release_build(version: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("version must be a released major.minor.patch")
    major, minor, patch = map(int, version.split("."))
    if minor >= 1000 or patch >= 1000:
        raise ValueError("schema-1 minor and patch must be below 1000")
    return major * 1000000 + minor * 1000 + patch


def source_file(root: Path, name: str) -> Path:
    relative = PurePosixPath(name.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe load path: {name}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"missing or escaped source: {name}")
    return path


def plan(
    source: Path, folder: str, version: str, saved_variable: str, entry: bytes, *, standalone: bool = False
) -> dict[str, bytes]:
    """Return all output bytes before writing anything. Source checkout stays untouched."""
    identifier(folder)
    identifier(saved_variable)
    if standalone and (folder != "ForeverCore" or saved_variable != "ForeverCoreDB" or entry):
        raise ValueError("standalone requires ForeverCore, ForeverCoreDB and no consumer entry")
    if not standalone and (folder == "ForeverCore" or saved_variable == "ForeverCoreDB"):
        raise ValueError("consumer must own its folder and account SavedVariables")
    build = release_build(version)
    graph = [
        line.strip().replace("\\", "/")
        for line in (source / "ForeverCore.toc").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not graph or graph[0] != "Core/Loader.lua" or graph[-1] != "Expose.lua" or len(set(graph)) != len(graph):
        raise ValueError("unsupported canonical TOC: loader first, expose last, unique entries required")
    inputs = {name: source_file(source, name).read_bytes() for name in graph}
    for directory in ("media",):
        for path in sorted((source / directory).rglob("*")):
            if path.is_file():
                name = path.relative_to(source).as_posix()
                inputs[name] = source_file(source, name).read_bytes()
    for name in ("LICENSE", "THIRD_PARTY.md"):
        inputs[name] = source_file(source, name).read_bytes()
    digest = hashlib.sha256()
    producer_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    digest.update(b"producer\0" + producer_digest.encode() + b"\0")
    # Identical files in a different TOC order can execute differently. Hash the
    # normalized graph, independent of host folder and TOC metadata or spacing.
    digest.update(b"source_order\0" + json.dumps(graph, separators=(",", ":")).encode() + b"\0")
    for name, data in sorted(inputs.items()):
        digest.update(name.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    identity = digest.hexdigest()
    prefix = "" if standalone else "Libs/ForeverCore/"
    output = {prefix + name: data for name, data in inputs.items() if name not in graph}
    template_name = folder + "_ForeverCore_" + TEMPLATE
    templates = {}
    for name in graph:
        data = inputs[name]
        if name == "Core/Loader.lua":
            output[prefix + name] = data
        elif name.endswith(".lua"):
            output[prefix + name] = (
                b"local _, host = ...\nhost.ForeverCoreCopy:Define(function(...)\n" + data + b"\nend)\n"
            )
        elif name == "UI/TrackerSection.xml":
            xml = ET.fromstring(data)
            children = list(xml)
            # Support the canonical declarative template only. Scripts, Includes,
            # real frames and additional templates need an explicit producer change.
            if (
                len(children) != 1
                or children[0].tag != "{http://www.blizzard.com/wow/ui/}Frame"
                or children[0].attrib
                != {
                    "name": TEMPLATE,
                    "inherits": "ObjectiveTrackerLineTemplate",
                    "enableMouse": "true",
                    "virtual": "true",
                }
                or list(children[0])
            ):
                raise ValueError("unsupported tracker XML contract")
            children[0].set("name", template_name)
            ET.register_namespace("", "http://www.blizzard.com/wow/ui/")
            output[prefix + name] = ET.tostring(xml, encoding="utf-8") + b"\n"
            templates[TEMPLATE] = template_name
        else:
            raise ValueError(f"unsupported canonical TOC entry: {name}")
    if TEMPLATE not in templates:
        raise ValueError("canonical tracker template missing")
    # A host first loaded after another copy is running (load on demand) joins that copy: the loader records its own
    # copy as "late", which is not a packaging error, and keeps its store offer (a revision 1 registry refuses
    # that as "late" too). Any other refusal stops the load.
    # Every wrapped Lua file plus End.lua's template definition: Seal refuses a package missing any of them.
    chunks = sum(1 for name in graph if name.endswith(".lua") and name != "Core/Loader.lua") + 1
    output[prefix + "Begin.lua"] = (
        "local addon, host = ...\n"
        f'host.ForeverCoreCopy = ForeverCoreLoader.Begin(addon, {build}, "{identity}", {chunks})\n'
        f'local offered, reason = ForeverCoreLoader.OfferStore(addon, "{saved_variable}")\n'
        'assert(offered or reason == "late", reason)\n'
    ).encode()
    output[prefix + "End.lua"] = (
        "local _, host = ...\nhost.ForeverCoreCopy:Define(function(_, ns)\n"
        f'ns.TrackerLine.template = "{template_name}"\nend)\n'
        "local sealed, reason = host.ForeverCoreCopy:Seal()\n"
        'assert(sealed or reason == "late", reason)\n'
    ).encode()
    output["ForeverCoreReady.lua"] = (
        b"local addon, host = ...\nlocal readyCore, resources, loaded, started\nlocal function initialize(...)\n"
        + entry
        + (
            "\nend\nlocal function tryStart()\n"
            "if loaded and readyCore and not started then\nstarted = true\n"
            "initialize(addon, host, readyCore, resources)\nend\nend\n"
            'local frame = CreateFrame("Frame")\nframe:RegisterEvent("ADDON_LOADED")\n'
            'frame:SetScript("OnEvent", function(self, _, name)\nif name ~= addon then return end\n'
            'self:UnregisterEvent("ADDON_LOADED")\n'
            f"if {saved_variable} == nil then {saved_variable} = {{}} end\n"
            f'assert(type({saved_variable}) == "table", "account SavedVariables must be a table")\n'
            "loaded = true\ntryStart()\nend)\n"
            "ForeverCoreLoader.OnReady(function(core, selected)\n"
            # The loader reports a failed activation once, by name; each consumer's ready step stays quiet.
            "if core == nil then return end\n"
            f'assert(core.API == {API}, "incompatible ForeverCore API")\n'
            'assert(type(core.Register) == "function", "ForeverCore Register unavailable")\n'
            'assert(type(core.TrackerLine) == "table", "ForeverCore TrackerLine unavailable")\n'
            'if selected.mode == "legacy" then\n'
            'assert(type(core.TrackerLine.SetInteractive) == "function", "unsupported legacy TrackerLine")\n'
            # An older unwrapped standalone declares the canonical template but never names it on its facade. Name
            # it there, so consumer code reads core.TrackerLine.template in every mode.
            f'if core.TrackerLine.template == nil then core.TrackerLine.template = "{TEMPLATE}" end\nend\n'
            "local template = core.TrackerLine.template\n"
            'assert(type(template) == "string", "ForeverCore template unavailable")\n'
            "resources = { template = template, mode = selected.mode, root = selected.root }\n"
            "readyCore = core\ntryStart()\nend)\n"
        ).encode()
    )
    loads = [prefix + graph[0], prefix + "Begin.lua"]
    loads.extend(prefix + name for name in graph[1:])
    loads.extend([prefix + "End.lua", "ForeverCoreReady.lua"])
    if standalone:
        headers = [
            line.replace("@project-version@", version)
            for line in (source / "ForeverCore.toc").read_text().splitlines()
            if line.startswith("##")
        ]
    else:
        headers = [
            "## Interface: 16001",
            f"## Title: {folder}",
            f"## Version: {version}",
            f"## SavedVariables: {saved_variable}",
            "## OptionalDeps: ForeverCore",
        ]
    headers.append(f"## X-Forever-Core-Loader: {SCHEMA}")
    output[folder + ".toc"] = (
        "\n".join(headers) + "\n\n" + "\n".join(name.replace("/", "\\") for name in loads) + "\n"
    ).encode()
    output["LICENSE"] = inputs["LICENSE"]
    output["THIRD_PARTY.md"] = inputs["THIRD_PARTY.md"]
    output[prefix + "bundle.json"] = (
        json.dumps(
            {
                "schema": SCHEMA,
                "standalone": standalone,
                "api": API,
                "version": version,
                "build": build,
                "source_digest": identity,
                "producer_digest": producer_digest,
                "source_order": graph,
                "source_files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(inputs.items())},
                "folder": folder,
                "saved_variable": saved_variable,
                "templates": templates,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(output.items())},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    return output


def compose_bundle(
    core_files: dict[str, bytes], consumer_files: dict[str, bytes], consumer_toc: bytes
) -> dict[str, bytes]:
    """Compose an embedded plan with the consumer's explicit files and final TOC."""
    prefix = "Libs/ForeverCore/"
    manifest_name = prefix + "bundle.json"
    manifest = json.loads(core_files[manifest_name])
    if manifest["standalone"]:
        raise ValueError("composition requires an embedded plan")
    toc_name = manifest["folder"] + ".toc"
    replaceable = {toc_name, "LICENSE", "THIRD_PARTY.md"}

    def safe(name):
        if (
            not name
            or "\\" in name
            or ":" in name
            or "\0" in name
            or name.startswith("/")
            or any(p in ("", ".", "..") for p in name.split("/"))
        ):
            raise ValueError(f"unsafe or aliased bundle path: {name}")
        return name

    names = {}
    for name in list(core_files) + list(consumer_files):
        safe(name)
        parts = name.split("/")
        for length in range(1, len(parts) + 1):
            component = "/".join(parts[:length])
            folded = component.casefold()
            if folded in names and names[folded] != component:
                raise ValueError(f"aliased bundle path: {name}")
            names[folded] = component
    all_files = set(core_files) | set(consumer_files)
    for name in all_files:
        if any("/".join(name.split("/")[:i]) in all_files for i in range(1, len(name.split("/")))):
            raise ValueError(f"file/directory collision: {name}")
    for name in consumer_files:
        if name not in replaceable and (
            name in core_files
            or name.casefold().startswith(prefix.casefold())
            or name.casefold() == "forevercoreready.lua"
            or name.lower().endswith(".toc")
        ):
            raise ValueError(f"protected consumer collision: {name}")
    if toc_name in consumer_files and consumer_files[toc_name] != consumer_toc:
        raise ValueError("consumer TOC bytes disagree")

    def loads(data):
        return [
            safe(line.strip().replace("\\", "/"))
            for line in data.decode().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    canonical = loads(core_files[toc_name])
    declared = loads(consumer_toc)
    core_loads = canonical[:-1]
    if (
        canonical[-1] != "ForeverCoreReady.lua"
        or declared[: len(core_loads)] != core_loads
        or not declared
        or declared[-1] != "ForeverCoreReady.lua"
        or len(set(declared)) != len(declared)
    ):
        raise ValueError("TOC requires canonical core order and ready exactly once last")
    graph = declared[len(core_loads) : -1]
    seen = set()

    def visit(name):
        if name not in consumer_files or name in replaceable:
            raise ValueError(f"missing or foreign consumer resource: {name}")
        if name in seen:
            raise ValueError(f"duplicate consumer load: {name}")
        seen.add(name)
        if name.lower().endswith(".xml"):
            for element in ET.fromstring(consumer_files[name]).iter():
                resource = element.get("file")
                if resource is None:
                    continue
                resource = resource.replace("\\", "/")
                if resource.startswith("/") or ":" in resource:
                    raise ValueError(f"foreign consumer resource: {resource}")
                resolved = safe(posixpath.normpath(posixpath.join(posixpath.dirname(name), resource)))
                if resolved.lower().endswith((".lua", ".xml")):
                    visit(resolved)
                elif resolved not in consumer_files:
                    raise ValueError(f"missing consumer resource: {resolved}")

    for name in graph:
        if not name.lower().endswith((".lua", ".xml")):
            raise ValueError(f"unexplained TOC load: {name}")
        visit(name)
    unexplained = {name for name in consumer_files if name.lower().endswith((".lua", ".xml"))} - seen
    if unexplained:
        raise ValueError(f"unexplained consumer loads: {sorted(unexplained)}")
    output = {**core_files, **consumer_files, toc_name: consumer_toc}
    manifest["files"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(output.items()) if name != manifest_name
    }
    output[manifest_name] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return output


def write_bundle(output: Path, files: dict[str, bytes]) -> None:
    """Never overwrite an existing package or mix outputs from different builds."""
    output.mkdir(parents=True, exist_ok=False)
    for name, data in sorted(files.items()):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def check_bundle(output: Path, files: dict[str, bytes]) -> None:
    """Compare a staged producer artifact with a fresh plan from reviewed inputs."""
    actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
    if actual != files.keys():
        raise ValueError(
            f"bundle file selection differs: missing={sorted(files.keys() - actual)}, "
            f"extra={sorted(actual - files.keys())}"
        )
    for name, data in files.items():
        if source_file(output, name).read_bytes() != data:
            raise ValueError(f"bundle bytes differ: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="new consumer addon folder")
    parser.add_argument("--folder", required=True)
    parser.add_argument("--version", required=True, help="ForeverCore version, not consumer version")
    parser.add_argument("--saved-variable", required=True, help="consumer account SavedVariables global")
    parser.add_argument("--standalone", action="store_true", help="build the canonical standalone addon")
    parser.add_argument("--ready-entry", type=Path, help="explicitly converted consumer startup Lua")
    parser.add_argument("--check", action="store_true", help="compare output with canonical inputs instead of writing")
    args = parser.parse_args()
    if args.output.name != args.folder:
        parser.error("output folder name must match --folder, which defines the client's media root")
    if not args.standalone and args.ready_entry is None:
        parser.error("consumer requires --ready-entry")
    files = plan(
        args.source,
        args.folder,
        args.version,
        args.saved_variable,
        args.ready_entry.read_bytes() if args.ready_entry else b"",
        standalone=args.standalone,
    )
    if args.check:
        check_bundle(args.output, files)
    else:
        write_bundle(args.output, files)


if __name__ == "__main__":
    main()
