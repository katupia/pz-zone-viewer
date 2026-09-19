# -*- coding: utf-8 -*-
"""Tkinter front end: pick a source, pick a zone name, get pzmap.org links."""

import os
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import config, parsers, share, sources

BUILDS = ["42.20.0", "42.19.0", "41.78.16"]

PALETTE = ["#3CC84B", "#00B4D8", "#B57BFF", "#FF9F1C", "#EF476F",
           "#06D6A0", "#118AB2", "#FFD166", "#8D99AE", "#F72585"]
ICONS = ["map_target", "map_checkmark", "map_steeringwheel", "map_tire", "map_plus",
         "map_star", "map_gears", "map_fuel", "map_house", "map_x"]


def colour_for(name, index):
    return PALETTE[index % len(PALETTE)]


def icon_for(name, index):
    return ICONS[index % len(ICONS)]


class Source(object):
    def __init__(self, label, path, kind):
        self.label = label
        self.path = path
        self.kind = kind          # "map" or "mod"
        self.zones = None         # filled during the scan, then cached

    def load(self):
        if self.zones is None:
            if self.kind == "map":
                self.zones = parsers.parse_file(os.path.join(self.path, "objects.lua"))
            else:
                self.zones = parsers.scan_tree(self.path)
        return self.zones

    def count(self, vehicle_only):
        zones = self.zones or []
        if vehicle_only:
            zones = [z for z in zones if z.type in parsers.VEHICLE_TYPES]
        return len(zones)


class App(ttk.Frame):
    def __init__(self, master):
        ttk.Frame.__init__(self, master, padding=10)
        self.grid(row=0, column=0, sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.cfg = config.load()
        self.sources = []
        self.visible = []
        self.link_buttons = []
        self.queue = queue.Queue()

        self._build_paths()
        self._build_panes()
        self._build_status()
        self.after(120, self._pump)
        self.autodetect(initial=True)

    # ---------------------------------------------------------------- layout
    def _build_paths(self):
        box = ttk.LabelFrame(self, text="Folders", padding=8)
        box.grid(row=0, column=0, columnspan=3, sticky="ew")
        box.columnconfigure(1, weight=1)
        self.vars = {}
        rows = [("game", "Game folder"), ("zomboid", "Zomboid folder"),
                ("workshop", "Workshop folder")]
        for i, (key, label) in enumerate(rows):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=1)
            v = tk.StringVar(value=self.cfg.get(key, ""))
            self.vars[key] = v
            ttk.Entry(box, textvariable=v).grid(row=i, column=1, sticky="ew", pady=1)
            ttk.Button(box, text="Browse...", width=10,
                       command=lambda k=key: self._browse(k)).grid(row=i, column=2, padx=4)

        bar = ttk.Frame(box)
        bar.grid(row=len(rows), column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(bar, text="Auto-detect", command=self.autodetect).pack(side="left")
        ttk.Button(bar, text="Scan for zones", command=self.scan).pack(side="left", padx=6)
        ttk.Label(bar, text="pzmap build:").pack(side="left", padx=(16, 4))
        self.build = tk.StringVar(value=self.cfg.get("build", BUILDS[0]))
        ttk.Combobox(bar, textvariable=self.build, values=BUILDS, width=10,
                     state="readonly").pack(side="left")
        self.only_vehicle = tk.BooleanVar(value=self.cfg.get("only_vehicle", True))
        ttk.Checkbutton(bar, text="Parking / vehicle zones only",
                        variable=self.only_vehicle,
                        command=self._refilter).pack(side="left", padx=16)
        self.show_empty = tk.BooleanVar(value=self.cfg.get("show_empty", False))
        ttk.Checkbutton(bar, text="Show sources with no zones",
                        variable=self.show_empty,
                        command=self._refilter).pack(side="left")

    def _build_panes(self):
        self.rowconfigure(1, weight=1)
        for c, wt in ((0, 2), (1, 2), (2, 3)):
            self.columnconfigure(c, weight=wt)

        left = ttk.LabelFrame(self, text="Source", padding=6)
        left.grid(row=1, column=0, sticky="nsew", pady=(10, 0), padx=(0, 6))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.src_list = tk.Listbox(left, exportselection=False, activestyle="none")
        self.src_list.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.src_list.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.src_list.config(yscrollcommand=sb.set)
        self.src_list.bind("<<ListboxSelect>>", lambda e: self.on_source())

        mid = ttk.LabelFrame(self, text="Zone name", padding=6)
        mid.grid(row=1, column=1, sticky="nsew", pady=(10, 0), padx=(0, 6))
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)
        self.zone_list = tk.Listbox(mid, exportselection=False, activestyle="none",
                                    selectmode="extended")
        self.zone_list.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(mid, orient="vertical", command=self.zone_list.yview)
        sb2.grid(row=0, column=1, sticky="ns")
        self.zone_list.config(yscrollcommand=sb2.set)
        self.zone_list.bind("<<ListboxSelect>>", lambda e: self.on_zone())

        right = ttk.LabelFrame(self, text="pzmap.org links", padding=6)
        right.grid(row=1, column=2, sticky="nsew", pady=(10, 0))
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        top = ttk.Frame(right)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Button(top, text="Build links", command=self.build_links).pack(side="left")
        ttk.Button(top, text="Open all", command=self.open_all).pack(side="left", padx=6)
        ttk.Button(top, text="Copy all URLs", command=self.copy_all).pack(side="left")
        self.hint = ttk.Label(right, wraplength=380, foreground="#555",
                              text=("pzmap starts running slow on my end with 1000 markers per browser, so a "
                                    "selection is split into several links. Open one, then "
                                    "choose “Overwrite and add markers” in the import dialog."))
        self.hint.grid(row=1, column=0, sticky="ew", pady=(8, 6))

        wrap = ttk.Frame(right)
        wrap.grid(row=2, column=0, sticky="nsew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        bg = ttk.Style().lookup("TFrame", "background") or None
        self.canvas = tk.Canvas(wrap, highlightthickness=0, borderwidth=0,
                                background=bg)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        sb3 = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        sb3.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=sb3.set)
        self.links_frame = ttk.Frame(self.canvas)
        self._links_window = self.canvas.create_window((0, 0), window=self.links_frame,
                                                       anchor="nw")
        self.links_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._links_window, width=e.width))

    def _build_status(self):
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, anchor="w").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    # ------------------------------------------------------------- behaviour
    def _browse(self, key):
        path = filedialog.askdirectory(title="Select the %s folder" % key,
                                       initialdir=self.vars[key].get() or os.path.expanduser("~"))
        if path:
            self.vars[key].set(path)

    def autodetect(self, initial=False):
        if not self.vars["game"].get():
            self.vars["game"].set(sources.find_game_dir())
        if not self.vars["zomboid"].get():
            self.vars["zomboid"].set(sources.user_zomboid_dir())
        if not self.vars["workshop"].get():
            self.vars["workshop"].set(sources.find_workshop_dir())
        found = [k for k in ("game", "zomboid", "workshop") if self.vars[k].get()]
        self.status.set("Detected: " + ", ".join(found) if found else
                        "Nothing detected -- set the folders by hand.")
        if not initial:
            self.scan()

    def _save_cfg(self):
        self.cfg.update({k: v.get() for k, v in self.vars.items()})
        self.cfg["build"] = self.build.get()
        self.cfg["only_vehicle"] = bool(self.only_vehicle.get())
        self.cfg["show_empty"] = bool(self.show_empty.get())
        config.save(self.cfg)

    def scan(self):
        self._save_cfg()
        self.src_list.delete(0, "end")
        self.zone_list.delete(0, "end")
        self._clear_links()
        self.sources = []
        self.status.set("Scanning...")
        # Tk variables must only be touched from the main thread
        paths = (self.vars["game"].get(), self.vars["zomboid"].get(),
                 self.vars["workshop"].get())
        threading.Thread(target=self._scan_worker, args=paths, daemon=True).start()

    def _scan_worker(self, game, zomboid, workshop):
        try:
            found = []
            if game:
                for name, path in sources.game_map_dirs(game):
                    found.append(Source("Vanilla map: %s" % name, path, "map"))
            mods = sources.list_mod_dirs(zomboid, workshop)
            for label, path in mods:
                found.append(Source(label, path, "mod"))
            # read every source now, so we know which ones define nothing
            for i, src in enumerate(found):
                self.queue.put(("status", "Reading %d/%d: %s" % (i + 1, len(found), src.label)))
                try:
                    src.load()
                except Exception:
                    src.zones = []
            self.queue.put(("sources", found))
        except Exception as exc:                      # keep the UI alive
            self.queue.put(("error", str(exc)))

    def _pump(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "status":
                    self.status.set(payload)
                elif kind == "sources":
                    self._fill_sources(payload)
                elif kind == "zones":
                    self._fill_zones(payload)
                elif kind == "error":
                    self.status.set("Error: " + payload)
        except queue.Empty:
            pass
        self.after(120, self._pump)

    def _fill_sources(self, found):
        self.sources = found
        self._refilter()

    def _refilter(self):
        """Redraw the source list for the current filter checkboxes."""
        if not self.sources:
            return
        keep_empty = bool(self.show_empty.get())
        vehicle_only = bool(self.only_vehicle.get())
        previous = None
        if getattr(self, "visible", None):
            sel = self.src_list.curselection()
            if sel:
                previous = self.visible[sel[0]]

        self.visible = [s for s in self.sources
                        if keep_empty or s.count(vehicle_only) > 0]
        self.src_list.delete(0, "end")
        for s in self.visible:
            n = s.count(vehicle_only)
            self.src_list.insert("end", "%s  (%d)" % (s.label, n) if n else s.label)
        if previous in self.visible:
            i = self.visible.index(previous)
            self.src_list.selection_set(i)
            self.src_list.see(i)
        hidden = len(self.sources) - len(self.visible)
        with_zones = sum(1 for s in self.sources if s.count(vehicle_only) > 0)
        if hidden:
            msg = ("%d source(s) with zones, %d empty one(s) hidden."
                   % (with_zones, hidden))
        else:
            msg = ("%d source(s), %d with zones."
                   % (len(self.visible), with_zones))
        self.status.set(msg + " Pick one to list its zones.")
        self._save_cfg()

    def on_source(self):
        sel = self.src_list.curselection()
        if not sel:
            return
        src = self.visible[sel[0]]
        self.zone_list.delete(0, "end")
        self._clear_links()
        self.status.set("Reading %s..." % src.label)
        threading.Thread(target=self._zone_worker, args=(src,), daemon=True).start()

    def _zone_worker(self, src):
        try:
            zones = src.load()
            self.queue.put(("zones", (src, zones)))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    def _fill_zones(self, payload):
        src, zones = payload
        if self.only_vehicle.get():
            zones = [z for z in zones if z.type in parsers.VEHICLE_TYPES]
        groups = {}
        for z in zones:
            groups.setdefault((z.name or "(unnamed)", z.type), []).append(z)
        self.groups = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        self.zone_list.delete(0, "end")
        for (name, type_), zs in self.groups:
            self.zone_list.insert("end", "%-34s %-14s %4d" % (name[:34], type_, len(zs)))
        if not self.groups:
            self.status.set("%s defines no zone." % src.label)
        else:
            self.status.set("%s: %d zone names, %d zones."
                            % (src.label, len(self.groups), len(zones)))

    def on_zone(self):
        sel = self.zone_list.curselection()
        if not sel:
            return
        total = sum(len(self.groups[i][1]) for i in sel)
        parts = len(share.split(list(range(total)))) if total else 0
        self.status.set("%d zones selected -> %d link(s)." % (total, parts))

    # ----------------------------------------------------------------- links
    def _clear_links(self):
        for w in self.link_buttons:
            w.destroy()
        self.link_buttons = []
        self.urls = []

    def build_links(self, confirm=True):
        sel = self.zone_list.curselection()
        if not sel:
            messagebox.showinfo("Nothing selected", "Pick at least one zone name.")
            return
        pois = []
        for order, i in enumerate(sel):
            (name, type_), zs = self.groups[i]
            colour, icon = colour_for(name, order), icon_for(name, order)
            for z in zs:
                desc = "%d,%d  %dx%d" % (z.x, z.y, z.w, z.h)
                if z.direction:
                    desc += "  Direction=%s" % z.direction
                desc += "  -  %s / %s" % (name, type_)
                pois.append({"x": z.cx, "y": z.cy, "layer": max(int(z.z), 0),
                             "name": name, "desc": desc, "color": colour, "icon": icon,
                             "rects": [{"x": z.x, "y": z.y, "width": z.w, "height": z.h}]})
        if not pois:
            messagebox.showinfo("Nothing to show", "That selection holds no zone.")
            return
        pois.sort(key=lambda p: (p["y"], p["x"]))
        batches = share.split(pois)
        if confirm and len(batches) > 40 and not messagebox.askokcancel(
                "That is a lot of links",
                "%d zones would need %d links of up to %d markers.\n\n"
                "Vanilla car parks hold thousands of stalls; you may want a "
                "narrower selection.\n\nBuild them anyway?"
                % (len(pois), len(batches), share.MAX_MARKERS_PER_LINK)):
            self.status.set("Cancelled -- pick fewer zones.")
            return
        self._clear_links()
        label = "+".join(self.groups[i][0][0] for i in sel)[:40]
        for n, batch in enumerate(batches, 1):
            title = "%s %d/%d" % (label, n, len(batches))
            url = share.build_url(batch, title, build=self.build.get())
            self.urls.append(url)
            row = ttk.Frame(self.links_frame)
            row.pack(fill="x", pady=2)
            ttk.Button(row, text="Open %d/%d  (%d markers)" % (n, len(batches), len(batch)),
                       width=28, command=lambda u=url: webbrowser.open(u)
                       ).pack(side="left")
            ttk.Button(row, text="Copy", width=7,
                       command=lambda u=url: self._copy(u)).pack(side="left", padx=4)
            ttk.Label(row, text="y %d-%d" % (batch[0]["y"], batch[-1]["y"]),
                      foreground="#666").pack(side="left", padx=4)
            self.link_buttons.append(row)
        self.status.set("%d markers -> %d link(s)." % (len(pois), len(batches)))
        self._save_cfg()

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set("URL copied to the clipboard.")

    def copy_all(self):
        if not getattr(self, "urls", None):
            return
        self._copy("\n".join(self.urls))
        self.status.set("%d URLs copied." % len(self.urls))

    def open_all(self):
        for u in getattr(self, "urls", []):
            webbrowser.open(u)


def main():
    root = tk.Tk()
    root.title("PZ Zone Viewer -- parking zones on pzmap.org")
    root.geometry("1180x720")
    root.minsize(940, 560)
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
