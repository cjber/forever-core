"""Per-app UI drivers. Each exposes setup, install, uninstall, rescan, reinstall, records, view, shot, version."""

import json
import time
from typing import Any

from . import apps, cdp, ui

ROW_JS = """
((name, rowSel, nameSel) => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const rows = [...document.querySelectorAll(rowSel)].filter(r => r.getBoundingClientRect().height > 0);
  const row = rows.find(r => [...r.querySelectorAll(nameSel)].some(e => norm(e.innerText) === name));
  if (!row) return null;
  row.scrollIntoView({block: 'center'});
  const rr = row.getBoundingClientRect();
  const buttons = [...row.querySelectorAll('button')].map(b => {
    const r = b.getBoundingClientRect();
    return {text: norm(b.innerText), x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
  });
  const n = [...row.querySelectorAll(nameSel)].find(e => norm(e.innerText) === name).getBoundingClientRect();
  return {text: norm(row.innerText), buttons, x: Math.round(n.x + n.width / 2), y: Math.round(n.y + n.height / 2),
          rowx: Math.round(rr.x + 40), rowy: Math.round(rr.y + rr.height / 2)};
})(%s, %s, %s)
"""


def row(d, name, row_sel, name_sel):
    return d.eval(ROW_JS % (json.dumps(name), json.dumps(row_sel), json.dumps(name_sel)))


def wait_row(d, name, row_sel, name_sel, timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        r = row(d, name, row_sel, name_sel)
        if r:
            return r
        time.sleep(1)
    raise TimeoutError(f"row {name!r} not found")


def wait_records(fn, pred, timeout=120, what="records"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = fn()
            if pred(last):
                return last
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise TimeoutError(f"timed out waiting for {what}; last={json.dumps(last)[:600]}")


class WowUp:
    name = "wowup"
    ROW = ".ag-center-cols-container .ag-row[row-index]"

    def __init__(self, opts):
        self.o = opts
        self.ud = apps.state_dir("wowup") / apps.APPS["wowup"]["userdata"]
        self.dialogs = []

    def version(self):
        m = json.loads((apps.APPS["wowup"]["bin"].parent / "resources/bundle-manifest.json").read_text())
        return f"WowUp-CF {m['version']} ({m['channel']})"

    def setup(self):
        apps.reset_app_state("wowup")
        apps.seed_wowup(self.o.channel)
        prefs = json.loads((self.ud / "preferences.json").read_text())
        prefs["main-window-state"] = {"x": 0, "y": 0, "width": 1380, "height": 980}
        prefs["main-window-is-maximized"] = False
        (self.ud / "preferences.json").write_text(json.dumps(prefs, indent=1))
        apps.start("wowup")
        time.sleep(3)
        self.d = cdp.Page(apps.APPS["wowup"]["port"])
        ui.wait_for(self.d, "document.body.innerText.includes('My Addons')", what="WowUp shell")
        time.sleep(3)

    def records(self):
        p = self.ud / "addons.json"
        if not p.exists():
            return []
        out: list[dict[str, Any]] = []
        for v in json.loads(p.read_text()).values():
            out.append(
                {
                    "project_id": int(v["externalId"]),
                    "name": v["name"],
                    "file_id": int(v.get("installedExternalReleaseId") or 0),
                    "version": v.get("installedVersion"),
                    "channel": v.get("channelType"),
                    "folders": v.get("installedFolderList"),
                    "download_url": v.get("downloadUrl"),
                    "dependencies": v.get("dependencies"),
                    "installed_at": v.get("installedAt"),
                }
            )
        return sorted(out, key=lambda r: r["name"])

    def _nav(self, text):
        ui.click_text(self.d, text, sel="a, div, span")
        time.sleep(2)

    def install(self, pid, name):
        self._nav("Get Addons")
        self.d.eval(
            f"""(() => {{ const i = [...document.querySelectorAll('input')].find(x => /Search/i.test(
                 x.closest('.mat-mdc-form-field, mat-form-field')?.innerText || ''));
               i.focus(); i.value = {json.dumps(name)}; i.dispatchEvent(new Event('input', {{bubbles: true}}));
               [...document.querySelectorAll('button')].find(b => b.innerText.trim() === 'Search').click();
               return 1 }})()"""
        )
        r = wait_row(self.d, name, ".ag-row[row-index]", ".addon-title")
        if "Curse" not in r["text"]:
            raise RuntimeError(f"row for {name!r} is not a CurseForge result: {r['text']}")
        b = next((b for b in r["buttons"] if b["text"] == "Install"), None)
        if not b:
            return {"note": f"no Install button: {r['text']}"}
        self.d.click(b["x"], b["y"])
        wait_records(self.records, lambda rs: any(x["project_id"] == pid for x in rs), what=f"record {pid}")
        time.sleep(3)
        return {"row": r["text"]}

    def _menu(self, name, item):
        self._nav("My Addons")
        r = wait_row(self.d, name, self.ROW, ".addon-title, [col-id=name] a, [col-id=name] .addon-name")
        self.d.eval(
            f"""(() => {{ const rows = [...document.querySelectorAll({json.dumps(self.ROW)})];
               const r = rows.find(x => x.innerText.includes({json.dumps(name)}));
               const c = r.querySelector('[col-id=name]') || r;
               const b = c.getBoundingClientRect();
               c.dispatchEvent(new MouseEvent('contextmenu', {{bubbles: true,
                  clientX: b.x + 20, clientY: b.y + 20, button: 2}}));
               return 1 }})()"""
        )
        time.sleep(1)
        ui.click_text(self.d, item, sel="[role=menuitem]")
        return r

    def _dialog(self):
        return self.d.eval("[...document.querySelectorAll('mat-dialog-container')].map(d => d.innerText).pop() || null")

    def _answer(self, text):
        self.d.eval(
            f"[...document.querySelectorAll('mat-dialog-container button')].reverse()"
            f".find(b => b.innerText.trim() === {json.dumps(text)}).click()"
        )

    def uninstall(self, pid, name):
        self._menu(name, "Remove")
        seen = []
        time.sleep(1.5)
        txt = self._dialog()
        self.d.shot(str(self.o.out / f"dialog-uninstall-{pid}.png"))
        seen.append({"dialog": txt, "answer": "Yes"})
        self._answer("Yes")
        time.sleep(2)
        txt = self._dialog()
        if txt and "Dependencies" in txt:
            ans = "Yes" if self.o.remove_deps == "yes" else "No"
            self.d.shot(str(self.o.out / f"dialog-deps-{pid}.png"))
            seen.append({"dialog": txt, "answer": ans})
            self._answer(ans)
        wait_records(self.records, lambda rs: all(x["project_id"] != pid for x in rs), what=f"{pid} removed")
        time.sleep(3)
        return {"dialogs": seen}

    def rescan(self):
        self._nav("My Addons")
        # "Re-Scan Folders" sits in the menu behind the arrow beside "Update All".
        if not ui.find(self.d, "Re-Scan Folders", sel="button, [role=menuitem]"):
            p = self.d.eval(
                """(() => { const bs = [...document.querySelectorAll('button')];
                   const u = bs.findIndex(b => b.innerText.trim() === 'Check Updates');
                   const b = bs.slice(u + 1).find(x => x.getAttribute('aria-haspopup') === 'menu');
                   const r = b.getBoundingClientRect();
                   return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)} })()"""
            )
            self.d.click(p["x"], p["y"])
            time.sleep(1)
        ui.click_text(self.d, "Re-Scan Folders", sel="button, [role=menuitem]")
        time.sleep(1.5)
        dlg = self._dialog()
        if dlg:
            self.d.eval("[...document.querySelectorAll('mat-dialog-container button')].pop().click()")
        ui.wait_for(self.d, "!document.body.innerText.includes('Scanning')", timeout=90, what="scan finished")
        time.sleep(4)
        return {
            "control": "Check Updates menu: Re-Scan Folders",
            "dialogs": [{"dialog": dlg, "answer": "last button"}] if dlg else [],
        }

    def reinstall(self, pid, name):
        self._menu(name, "Re-Install")
        time.sleep(2)
        dlg = self._dialog()
        if dlg:
            self._answer("Yes")
        time.sleep(8)
        return {"dialog": dlg}

    def install_core(self, pid, name):
        if any(x["project_id"] == pid for x in self.records()):
            return {"how": "existing record: Re-Install", **self.reinstall(pid, name)}
        return {"how": "Get Addons: Install", **self.install(pid, name)}

    def set_channel(self, pid, name, channel):
        label = {"release": "Stable", "beta": "Beta", "alpha": "Alpha"}[channel]
        self._menu(name, "Channel")
        time.sleep(1)
        self.d.shot(str(self.o.out / f"channel-menu-{pid}.png"))
        ui.click_text(self.d, label, sel="mat-radio-button, label, [role=menuitemradio], button, span")
        time.sleep(1)
        self.d.key("Escape")
        rec = wait_records(
            self.records,
            lambda rs: any(x["project_id"] == pid and x["channel"] == apps.CHANNELS[channel] for x in rs),
            timeout=30,
            what=f"{pid} channel {channel}",
        )
        time.sleep(3)
        return {
            "control": f"context menu Channel > {label}",
            "record_channel": next(x["channel"] for x in rec if x["project_id"] == pid),
        }

    def _row_after_check(self, name):
        self._nav("My Addons")
        ui.click_text(self.d, "Check Updates", sel="button")
        time.sleep(6)
        return wait_row(self.d, name, self.ROW, ".addon-title, [col-id=name] a, [col-id=name] .addon-name")

    def update(self, pid, name):
        before = next((x["file_id"] for x in self.records() if x["project_id"] == pid), None)
        r = self._row_after_check(name)
        b = next((b for b in r["buttons"] if b["text"] == "Update"), None)
        if not b:
            return {"note": "no Update button after Check Updates", "row": r["text"]}
        self.d.click(b["x"], b["y"])
        wait_records(
            self.records,
            lambda rs: any(x["project_id"] == pid and x["file_id"] != before for x in rs),
            what=f"{pid} updated",
        )
        time.sleep(4)
        return {"row_before": r["text"], "file_before": before}

    def update_all(self):
        self._nav("My Addons")
        ui.click_text(self.d, "Check Updates", sel="button")
        time.sleep(6)
        enabled = self.d.eval(
            "(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='Update All');"
            " return b && !b.disabled})()"
        )
        if enabled:
            ui.click_text(self.d, "Update All", sel="button")
            time.sleep(15)
        return {"control": "Update All", "enabled": bool(enabled)}

    def restart(self):
        self.close()
        left = apps.stop("wowup")
        apps.start("wowup")
        time.sleep(3)
        self.d = cdp.Page(apps.APPS["wowup"]["port"])
        ui.wait_for(self.d, "document.body.innerText.includes('My Addons')", what="WowUp shell")
        time.sleep(10)
        return {"stopped_left": left}

    def view(self):
        try:
            self._nav("My Addons")
            return self.d.eval(
                f"[...document.querySelectorAll({json.dumps(self.ROW)})]"
                f".map(r => r.innerText.replace(/\\s+/g, ' ').trim())"
            )
        except Exception as e:  # noqa: BLE001 - the view is evidence, never a reason to abort
            return [f"error: {e}"]

    def shot(self, path):
        return self.d.shot(path)

    def close(self):
        try:
            self.d.close()
        except Exception:  # noqa: BLE001
            pass


class CurseForge:
    name = "curseforge"
    INSPECT = 9312
    ROW = ".table-row"

    def __init__(self, opts):
        self.o = opts
        self.ud = apps.state_dir("curseforge") / apps.APPS["curseforge"]["userdata"]

    def version(self):
        version = self.d.maineval('require("electron").app.getVersion()')
        electron = self.d.maineval("process.versions.electron")
        return f"CurseForge {version} (Electron {electron})"

    def setup(self):
        apps.reset_app_state("curseforge")
        apps.start("curseforge", [f"--inspect={self.INSPECT}"], ready_port=self.INSPECT, ready_type="node")
        time.sleep(3)
        self.d = cdp.MainBridge(self.INSPECT)
        ui.wait_for(self.d, "document.body && document.body.innerText.length > 0", what="CF window")
        # First-run screens: Continue until the guest choice, then guest (no login).
        end = time.time() + 120
        while time.time() < end:
            if ui.find(self.d, "Continue As Guest", sel="button"):
                ui.click_text(self.d, "Continue As Guest", sel="button")
                break
            if ui.find(self.d, "Continue", sel="button"):
                ui.click_text(self.d, "Continue", sel="button")
            time.sleep(2)
        ui.wait_for(self.d, "document.body.innerText.includes('Choose a Game')", what="game list")
        time.sleep(2)
        self._dismiss_modals()
        # The game folder comes from a native folder picker; answer it with the fake client.
        self.d.maineval(
            "(()=>{const dl=require('electron').dialog; globalThis.__dlg=[];"
            " dl.showOpenDialog=async(...a)=>{globalThis.__dlg.push(JSON.stringify(a.slice(-1)));"
            f" return {{canceled:false,filePaths:[{json.dumps(str(apps.FAKE))}]}}}}; return 1}})()"
        )
        ui.click_text(self.d, "World of Warcraft", sel="div, span, p, h3, h2")
        time.sleep(3)
        self._dismiss_modals()
        ui.click_text(self.d, "Locate Game", sel="button, div, span")
        time.sleep(1)
        ui.click_text(self.d, "Manually add a game", sel="ul.left-bottom li")
        ui.wait_for(self.d, "document.body.innerText.includes('Game Successfully Added')", what="game added")
        ui.click_text(self.d, "Done", sel="button")
        time.sleep(2)
        self._settings()

    def _dismiss_modals(self):
        # The "what's new" changelog modal opens on some launches; close it if present.
        self.d.eval(
            "(()=>{const b=[...document.querySelectorAll('button')].find(b=>/close/i.test(b"
            ".getAttribute('aria-label')||'')"
            " && b.closest('[class*=modal], [class*=dialog], dialog')); if(b){b.click();return 1} return 0})()"
        )
        time.sleep(1)

    def _menu_button(self):
        """The instance's three-dot menu right of the search bar (not the window's title-bar buttons)."""
        return ui.wait_for(
            self.d,
            "(()=>{const b=document.querySelector('button.addon-options-btn');"
            " if(!b || !b.getBoundingClientRect().width) return null;"
            " const r=b.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()",
            what="instance menu button",
        )

    def _settings(self):
        """Instance settings: preferred release, delete orphaned libraries, install libraries separately."""
        menu = self._menu_button()
        self.d.click(menu["x"], menu["y"])
        time.sleep(1)
        ui.click_text(self.d, "Open instance settings", sel="li")
        ui.wait_for(self.d, "document.body.innerText.includes('Preferred Release')", what="instance settings")
        label = {"release": "Release (Recommended)", "beta": "Beta", "alpha": "Alpha"}[self.o.channel]
        p = self.d.eval(
            "(()=>{const row=[...document.querySelectorAll('.settings-item-row')]"
            ".find(r=>r.innerText.includes('Preferred Release'));"
            " const b=row.querySelector('button.selected-item'); b.scrollIntoView({block:'center'});"
            " const r=b.getBoundingClientRect();"
            " return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2), cur:b.innerText.trim()}})()"
        )
        if p["cur"] != label:
            self.d.click(p["x"], p["y"])
            time.sleep(1)
            ui.click_text(self.d, label, sel="li.dropdown-option")
            time.sleep(1)
        for toggle, want in (
            ("delete-orphaned-libraries", self.o.remove_deps == "yes"),
            ("library-preference", self.o.cf_libs_separate == "yes"),
        ):
            st = self.d.eval(
                f"(()=>{{const i=document.getElementById('{toggle}');"
                f" const l=document.querySelector('label[for={toggle}] span')"
                f"?.parentElement || document.querySelectorAll('label[for={toggle}]')[1];"
                f" l.scrollIntoView({{block:'center'}});"
                " const r=l.getBoundingClientRect();"
                " return {checked:i.checked,x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()"
            )
            if st["checked"] != want:
                self.d.click(st["x"], st["y"])
                time.sleep(1)
        self.settings = self.d.eval(
            "(()=>({release:[...document.querySelectorAll('.settings-item-row')]"
            ".find(r=>r.innerText.includes('Preferred Release'))"
            ".querySelector('button.selected-item').innerText.trim(),"
            " deleteOrphaned:document.getElementById('delete-orphaned-libraries').checked,"
            " librariesSeparately:document.getElementById('library-preference').checked}))()"
        )
        self.shot(str(self.o.out / "settings.png"))
        # Close settings with its X button.
        x = self.d.eval(
            "(()=>{const b=[...document.querySelectorAll('button')].filter(b=>{const r=b.getBoundingClientRect();"
            " return r.x>900&&r.x<980&&r.y<110&&r.width>0}).pop(); const r=b.getBoundingClientRect();"
            " return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()"
        )
        self.d.click(x["x"], x["y"])
        time.sleep(2)

    def records(self):
        p = self.ud / "agent/GameInstances/AddonGameInstance.json"
        if not p.exists():
            return []
        inst = json.loads(p.read_text())
        out: list[dict[str, Any]] = []
        for gi in inst:
            for a in gi.get("installedAddons", []):
                f = a.get("installedFile") or {}
                out.append(
                    {
                        "project_id": a["addonID"],
                        "name": a["name"],
                        "file_id": f.get("id"),
                        "file_name": f.get("fileName"),
                        "release_type": f.get("releaseType"),
                        "download_url": f.get("downloadUrl"),
                        "hashes": {str(h["type"]): h["value"] for h in f.get("hashes", [])},
                        "modules": [[m["foldername"], m["fingerprint"]] for m in f.get("modules", [])],
                        "dependencies": f.get("dependencies"),
                        "folders": sorted(
                            {fp.split("/AddOns/")[1].split("/")[0] for fp in a.get("filePaths", []) if "/AddOns/" in fp}
                        ),
                        "file_paths": len(a.get("filePaths", [])),
                        "status": a.get("status"),
                        "install_source": a.get("installSource"),
                        "is_modified": a.get("isModified"),
                        "preference_release_type": a.get("preferenceReleaseType"),
                        "date_installed": a.get("dateInstalled"),
                    }
                )
        return sorted(out, key=lambda r: r["name"])

    def instance_prefs(self):
        p = self.ud / "agent/GameInstances/AddonGameInstance.json"
        gi = json.loads(p.read_text())[0]
        return {
            k: v
            for k, v in gi.items()
            if k.startswith("preference") or k in ("gameVersionTypeId", "name", "installPath")
        }

    def _tab(self, text):
        ui.click_text(self.d, text, sel="a, button, li, div, span")
        time.sleep(2)

    def install(self, pid, name):
        self._tab("Browse")
        p = self.d.eval(
            "(()=>{const i=document.querySelector(\"input[placeholder^='Search for World']\"); i.focus(); i.select();"
            " const r=i.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()"
        )
        self.d.click(p["x"], p["y"])
        self.d.maineval(f"({cdp.MainBridge.WIN}.selectAll(), 1)")
        self.d.type_text(name)
        time.sleep(1)
        ui.click_text(self.d, f'Search for "{name}"')
        r = wait_row(self.d, name, self.ROW, "*")
        b = next((b for b in r["buttons"] if b["text"] == "Install"), None)
        if not b:
            return {"note": f"no Install button: {r['text']}"}
        self.d.click(b["x"], b["y"])
        wait_records(self.records, lambda rs: any(x["project_id"] == pid for x in rs), what=f"record {pid}")
        ui.wait_for(self.d, "!document.body.innerText.includes('Downloading')", what="download finished")
        time.sleep(4)
        return {"row": r["text"]}

    def _context(self, name, item):
        self._tab("My Addons")
        for _ in range(3):
            r = wait_row(self.d, name, self.ROW, "*")
            self.d.click(r["x"], r["y"], "right")
            time.sleep(1.5)
            if ui.find(self.d, item, sel="li"):
                ui.click_text(self.d, item, sel="li")
                return r
            self.d.key("Escape")
            time.sleep(1)
        raise TimeoutError(f"context menu item {item!r} not shown for {name!r}")

    def uninstall(self, pid, name):
        self._context(name, "Delete Addon")
        time.sleep(1.5)
        dlg = ui.body_text(self.d, 20000)
        dlg = dlg[dlg.find("Delete " + name) :][:400] if ("Delete " + name) in dlg else None
        self.d.shot(str(self.o.out / f"dialog-uninstall-{pid}.png"))
        ui.click_text(self.d, "Delete", sel="button")
        # Deletion waits for the "Undo" toast to expire.
        wait_records(
            self.records, lambda rs: all(x["project_id"] != pid for x in rs), timeout=90, what=f"{pid} removed"
        )
        time.sleep(4)
        return {"dialogs": [{"dialog": dlg, "answer": "Delete"}]}

    def rescan(self):
        # The Refresh button in the My Addons toolbar re-reads the AddOns folder (the kebab menu's
        # "Scan addons folder" did not change any row's state in testing).
        self._tab("My Addons")
        p = ui.wait_for(
            self.d,
            "(()=>{const b=document.querySelector('button[aria-label=Refresh]'); if(!b) return null;"
            " const r=b.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()",
            what="Refresh button",
        )
        self.d.click(p["x"], p["y"])
        time.sleep(8)
        return {"control": "My Addons toolbar: Refresh"}

    def reinstall(self, pid, name):
        self._tab("My Addons")
        r = wait_row(self.d, name, self.ROW, "*")
        b = next((b for b in r["buttons"] if b["text"] == "Reinstall"), None)
        how = "row action Reinstall"
        if b:
            self.d.click(b["x"], b["y"])
        else:
            how = "context menu Reinstall"
            self._context(name, "Reinstall")
        time.sleep(3)
        ui.wait_for(self.d, "!document.body.innerText.includes('Downloading')", what="reinstall finished")
        time.sleep(4)
        return {"how": how, "row_before": r["text"]}

    def install_core(self, pid, name):
        if any(x["project_id"] == pid for x in self.records()):
            return self.reinstall(pid, name)
        return self.install(pid, name)

    def set_channel(self, pid, name, channel):
        label = {"release": "Release", "beta": "Beta", "alpha": "Alpha"}[channel]
        self._tab("My Addons")
        for _ in range(3):
            r = wait_row(self.d, name, self.ROW, "*")
            self.d.click(r["x"], r["y"], "right")
            time.sleep(1.5)
            p = self.d.eval(
                "(()=>{const li=[...document.querySelectorAll('li')].find(e=>e.getBoundingClientRect().width"
                " && /^Release Type/.test(e.innerText.trim())); if(!li) return null;"
                " const r=li.getBoundingClientRect();"
                " return {x:Math.round(r.x+40),y:Math.round(r.y+Math.min(r.height,40)/2)}})()"
            )
            if p:
                self.d.hover(p["x"], p["y"])
                time.sleep(1)
                self.shot(str(self.o.out / f"channel-menu-{pid}.png"))
                ui.click_text(self.d, label, sel="li")
                break
            self.d.key("Escape")
            time.sleep(1)
        else:
            raise TimeoutError("Release Type menu not shown")
        want = apps.CHANNELS[channel] + 1
        # The agent persists the per-addon preference lazily (seen saved only with the next file
        # change), so the record is evidence when present, not a gate.
        try:
            wait_records(
                self.records,
                lambda rs: any(x["project_id"] == pid and x["preference_release_type"] == want for x in rs),
                timeout=20,
            )
        except TimeoutError:
            pass
        time.sleep(1)
        self.d.key("Escape")
        time.sleep(1)
        rec = next((x["preference_release_type"] for x in self.records() if x["project_id"] == pid), None)
        r = wait_row(self.d, name, self.ROW, "*")
        return {"control": f"context menu Release Type > {label}", "record_preference_now": rec, "row": r["text"]}

    def update(self, pid, name):
        before = next((x["file_id"] for x in self.records() if x["project_id"] == pid), None)
        self.rescan()
        r = wait_row(self.d, name, self.ROW, "*")
        b = next((b for b in r["buttons"] if b["text"] == "Update"), None)
        if not b:
            return {"note": "no Update button after Refresh", "row": r["text"]}
        self.d.click(b["x"], b["y"])
        wait_records(
            self.records,
            lambda rs: any(x["project_id"] == pid and x["file_id"] != before for x in rs),
            what=f"{pid} updated",
        )
        ui.wait_for(self.d, "!document.body.innerText.includes('Downloading')", what="update finished")
        time.sleep(5)
        return {"row_before": r["text"], "file_before": before}

    def update_all(self):
        self.rescan()
        p = ui.find(self.d, "Update All", sel="button")
        if p:
            self.d.click(p["x"], p["y"])
            time.sleep(15)
        return {"control": "Update All", "shown": bool(p)}

    def restart(self):
        self.close()
        left = apps.stop("curseforge")
        apps.start("curseforge", [f"--inspect={self.INSPECT}"], ready_port=self.INSPECT, ready_type="node")
        time.sleep(3)
        self.d = cdp.MainBridge(self.INSPECT)
        # A relaunch can come up with its main window hidden (tray); show it so it can be driven.
        end = time.time() + 90
        while time.time() < end:
            n = self.d.maineval(
                "(()=>{const ws=require('electron').BrowserWindow.getAllWindows();"
                " ws.forEach(w=>{if(!w.isVisible()) w.show()});"
                " return ws.filter(w=>w.isVisible()).length})()"
            )
            if n:
                break
            time.sleep(2)
        ui.wait_for(self.d, "document.body && document.body.innerText.length > 0", what="CF window")
        time.sleep(10)
        self._dismiss_modals()
        if not ui.find(self.d, "My Addons", sel="a, button, li, div, span"):
            ui.click_text(self.d, "World of Warcraft", sel="div, span, p, h3, h2")
            time.sleep(3)
        return {"stopped_left": left}

    def view(self):
        try:
            self._tab("My Addons")
            return self.d.eval(
                "[...document.querySelectorAll('.table-row')].filter(r=>r.getBoundingClientRect().height>0)"
                ".map(r => r.innerText.replace(/\\s+/g, ' ').trim())"
            )
        except Exception as e:  # noqa: BLE001
            return [f"error: {e}"]

    def shot(self, path):
        return self.d.shot(path)

    def close(self):
        try:
            self.d.close()
        except Exception:  # noqa: BLE001
            pass


DRIVERS = {"wowup": WowUp, "curseforge": CurseForge}
