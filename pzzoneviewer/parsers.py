# -*- coding: utf-8 -*-
"""Read Project Zomboid parking-stall zone definitions out of Lua files.

Three shapes are understood, which between them cover the base game and the
zone mods people actually ship:

1. Lua table entries -- ``media/maps/<Map>/objects.lua`` (vanilla) and
   ``media/mapszones/<Map>/*.lua`` (tsarslib and friends)::

       { name = "bigtrailerparkinglot", type = "ParkingStall",
         x = 11853, y = 9801, z = 0, width = 23, height = 4,
         properties = { Direction = "N" } },

2. Helper calls used by PZK Vanilla Plus Car Pack and similar packs::

       PZKZones.addZone("semi", "ParkingStall", 12038, 7137, 0, 5, 3, "W", mod)

3. The engine calls themselves::

       getWorld():registerZone("name", "ParkingStall", x, y, z, w, h)
       getWorld():registerVehiclesZone("name", "ParkingStall", x, y, z, w, h, props)
"""

import os
import re

#: zone types that place vehicles, i.e. the ones worth drawing
VEHICLE_TYPES = ("ParkingStall", "Vehicle")

_NUM = r"[-+0-9 ()*/]+"

_TABLE_RE = re.compile(
    r'\{\s*name\s*=\s*"(?P<name>[^"]*)"\s*,\s*type\s*=\s*"(?P<type>[^"]+)"\s*,'
    r'\s*x\s*=\s*(?P<x>' + _NUM + r')\s*,\s*y\s*=\s*(?P<y>' + _NUM + r')\s*,'
    r'\s*z\s*=\s*(?P<z>' + _NUM + r')\s*,\s*width\s*=\s*(?P<w>' + _NUM + r')\s*,'
    r'\s*height\s*=\s*(?P<h>' + _NUM + r')\s*(?P<rest>[^}]*)')

_CALL_RE = re.compile(
    r'(?:addZone|registerZone|registerVehiclesZone)\s*\(\s*'
    r'"(?P<name>[^"]*)"\s*,\s*"(?P<type>[^"]+)"\s*,\s*'
    r'(?P<x>' + _NUM + r')\s*,\s*(?P<y>' + _NUM + r')\s*,\s*'
    r'(?P<z>' + _NUM + r')\s*,\s*(?P<w>' + _NUM + r')\s*,\s*'
    r'(?P<h>' + _NUM + r')\s*(?:,\s*"(?P<dir>[NSEW])"\s*)?')

_DIR_RE = re.compile(r'Direction\s*=\s*"?([NSEW])"?')


def _num(text):
    """Evaluate the small arithmetic the zone files use, e.g. ``5553+5``."""
    expr = text.strip()
    if not expr or not re.fullmatch(r"[-+0-9 ()*/]+", expr):
        raise ValueError(expr)
    return int(eval(expr, {"__builtins__": {}}, {}))


class Zone(object):
    __slots__ = ("name", "type", "x", "y", "z", "w", "h", "direction", "source", "line")

    def __init__(self, name, type_, x, y, z, w, h, direction, source, line):
        self.name = name
        self.type = type_
        self.x, self.y, self.z, self.w, self.h = x, y, z, w, h
        self.direction = direction
        self.source = source
        self.line = line

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def __repr__(self):
        return "<Zone %s %s (%d,%d) %dx%d>" % (self.name, self.type, self.x, self.y,
                                               self.w, self.h)


def _mask_comments(text):
    """Blank out commented-out lines, keeping offsets so line numbers stay true."""
    parts = []
    for line in text.splitlines(True):
        if line.lstrip().startswith("--"):
            parts.append(" " * (len(line) - 1) + "\n" if line.endswith("\n")
                         else " " * len(line))
        else:
            parts.append(line)
    return "".join(parts)


def parse_text(text, source="", wanted_types=VEHICLE_TYPES):
    """Pull every zone definition out of one Lua file's text.

    Entries may span several lines; lines commented out with ``--`` are ignored.
    """
    masked = _mask_comments(text)
    starts = [0]
    for line in masked.splitlines(True):
        starts.append(starts[-1] + len(line))

    def lineno_at(pos):
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    out = []
    for rx, is_call in ((_TABLE_RE, False), (_CALL_RE, True)):
        for m in rx.finditer(masked):
            if wanted_types and m.group("type") not in wanted_types:
                continue
            try:
                x, y, z = _num(m.group("x")), _num(m.group("y")), _num(m.group("z"))
                w, h = _num(m.group("w")), _num(m.group("h"))
            except ValueError:
                continue
            if w <= 0 or h <= 0:
                continue
            if is_call:
                direction = m.group("dir")
            else:
                d = _DIR_RE.search(m.group("rest") or "")
                direction = d.group(1) if d else None
            out.append(Zone(m.group("name"), m.group("type"), x, y, z, w, h,
                            direction, source, lineno_at(m.start())))
    out.sort(key=lambda z: z.line)
    return out


def parse_file(path, wanted_types=VEHICLE_TYPES):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    return parse_text(text, source=path, wanted_types=wanted_types)


#: file names worth opening; anything else is skipped for speed
_INTERESTING = ("objects.lua",)
_INTERESTING_DIRS = ("mapszones", "maps")


def looks_interesting(path):
    base = os.path.basename(path).lower()
    if base in _INTERESTING:
        return True
    if not base.endswith(".lua"):
        return False
    low = path.replace("\\", "/").lower()
    if any(("/%s/" % d) in low for d in _INTERESTING_DIRS):
        return True
    # zone scripts usually say so in their name
    return "zone" in base


def scan_tree(root, wanted_types=VEHICLE_TYPES, max_files=4000):
    """Walk a mod or game folder and collect every zone it defines."""
    zones = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in
                       (".git", "__pycache__", "anims_x", "models_x", "textures")]
        for fn in filenames:
            if not fn.lower().endswith(".lua"):
                continue
            path = os.path.join(dirpath, fn)
            if not looks_interesting(path):
                continue
            seen += 1
            if seen > max_files:
                return zones
            zones.extend(parse_file(path, wanted_types))
    return zones
