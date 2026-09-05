# -*- coding: utf-8 -*-
"""Headless-ish smoke test: build the UI, scan, pick a zone, build links.

Run with:  python selftest.py
It needs a display (or an X server) because Tk really is created.
"""
import sys
import time
import tkinter as tk

from pzzoneviewer import share, parsers
from pzzoneviewer.app import App


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main():
    ok = True

    # 1. encoder round-trip shape
    pois = [{"x": 100, "y": 200, "name": "t", "desc": "d", "color": "#3CC84B",
             "icon": "map_target", "rects": [{"x": 100, "y": 200, "width": 3, "height": 5}]}]
    url = share.build_url(pois, "test")
    assert url.startswith("https://pzmap.org/?100x200x0&v=42.20.0&import=PZPOI2."), url
    print("[ok] share.build_url ->", url[:70], "...")

    # 2. parser on inline samples
    sample = '''
      { name = "bigtrailerparkinglot", type = "ParkingStall", x = 5553+5, y = 9801, z = 0,
        width = 23, height = 4, properties = { Direction = "N", FaceDirection = true } },
      --{ name = "skipme", type = "ParkingStall", x = 1, y = 1, z = 0, width = 2, height = 2 },
      PZKZones.addZone("semi", "ParkingStall", 12038, 7137, 0, 5, 3, "W", mod)
      getWorld():registerZone("nav", "Nav", 1, 2, 0, 3, 4)
    '''
    zs = parsers.parse_text(sample)
    names = sorted(z.name for z in zs)
    assert names == ["bigtrailerparkinglot", "semi"], names
    assert zs[0].x == 5558 and zs[0].direction == "N", (zs[0].x, zs[0].direction)
    assert zs[1].direction == "W"
    print("[ok] parsers: %d zones, arithmetic and comments handled" % len(zs))

    # 3. the real UI
    root = tk.Tk()
    root.title("selftest")
    app = App(root)
    pump(root, 0.5)
    app.scan()
    for _ in range(200):
        pump(root, 0.1)
        if app.sources:
            break
    print("[ok] scan found %d sources" % len(app.sources))
    if not app.sources:
        ok = False

    # pick the first source that actually defines something
    picked = None
    for i, s in enumerate(app.sources):
        app.src_list.selection_clear(0, "end")
        app.src_list.selection_set(i)
        app.on_source()
        for _ in range(100):
            pump(root, 0.05)
            if getattr(app, "groups", None):
                break
        if getattr(app, "groups", None):
            picked = s
            break
    if picked:
        print("[ok] %s -> %d zone names" % (picked.label, len(app.groups)))
        app.zone_list.selection_clear(0, "end")
        app.zone_list.selection_set(0)
        app.build_links()
        pump(root, 0.3)
        print("[ok] built %d link(s); first = %s..." % (len(app.urls), app.urls[0][:60]))
        assert app.urls and app.urls[0].startswith("https://pzmap.org/?")
    else:
        print("[!!] no source defined any zone -- check the folder settings")
        ok = False

    root.destroy()
    print("SELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
