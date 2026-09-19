# -*- coding: utf-8 -*-
"""Encoder for pzmap.org's "PZPOI2" personal-POI share payload.

Port of ``buildShareBinaryV3`` / ``appendPoiListToWriter`` / ``ShareByteWriter``
from pzmap.org's ``static/js/personal_pois.js`` (SHARE_BINARY_VERSION = 3).

The resulting string goes in the ``import`` query parameter:

    https://pzmap.org/?<x>x<y>x<layer>&v=<build>&import=<payload>

Opening that URL shows pzmap's own import dialog; nothing is uploaded, the
payload is decoded in the browser.
"""

import base64
import zlib

PREFIX = "PZPOI2."
VERSION = 3

HDR_FLAG_NAME = 1
F_DESC, F_COLOR, F_ICON, F_RECTS = 1, 2, 4, 8
F_LAYER, F_CATEGORY, F_COLOR_RGB, F_DELTA = 16, 32, 64, 128

#: pzmap caps is removed. windows cmd size is now limiting.
MAX_MARKERS_PER_LINK = 1000

COLOR_PRESETS = [
    "#E040FB", "#FF1744", "#FF9100", "#FFEA00",
    "#00E676", "#00E5FF", "#304FFE", "#FFFFFF",
]
DEFAULT_COLOR = COLOR_PRESETS[0]
DEFAULT_ICON = "poi"
DEFAULT_CATEGORY = "Other"

ICON_IDS = [
    "map_anvil", "map_apple", "map_armor", "map_arroweast", "map_arrowISOeast",
    "map_arrowISOnorth", "map_arrowISOnortheast", "map_arrowISOnorthwest",
    "map_arrowISOsouth", "map_arrowISOsoutheast", "map_arrowISOsouthwest",
    "map_arrowISOwest", "map_arrownorth", "map_arrownortheast", "map_arrownorthwest",
    "map_arrowsouth", "map_arrowsouthwest", "map_arrowwest", "map_asterisk", "map_axe",
    "map_baseball", "map_bed", "map_bird", "map_boat", "map_bomb", "map_book",
    "map_bullets", "map_burger", "map_checkmark", "map_chicken", "map_club",
    "map_columns", "map_cow", "map_cross", "map_crossedswords", "map_deer",
    "map_diamond", "map_dollarsign", "map_door", "map_egg", "map_exclamation",
    "map_eye", "map_facedead", "map_facesad", "map_firet", "map_fish", "map_flower",
    "map_fuel", "map_furnace", "map_garbage", "map_gears", "map_gun", "map_hammer",
    "map_heart", "map_heartbroken", "map_house", "map_key", "map_knife",
    "map_knifefork", "map_ladder", "map_leaf", "map_lightbulb", "map_lightning",
    "map_lock", "map_medcross", "map_minus", "map_moon", "map_o", "map_pawprint",
    "map_pig", "map_pill", "map_plus", "map_police", "map_question", "map_rabbit",
    "map_raccoon", "map_radiation", "map_rodent", "map_satellite", "map_sheep",
    "map_shirt", "map_skull", "map_skyscraper", "map_snowflake", "map_spade",
    "map_star", "map_steeringwheel", "map_sun", "map_target", "map_tent", "map_tick",
    "map_tire", "map_trap", "map_tree", "map_triangle", "map_turkey", "map_vhs",
    "map_waves", "map_wrench", "map_x", "map_z",
]
ICON_INDEX = {name: i for i, name in enumerate(ICON_IDS)}


class _Writer(object):
    def __init__(self):
        self.b = bytearray()

    def u8(self, v):
        self.b.append(v & 0xFF)

    def varint(self, v):
        v &= 0xFFFFFFFF
        while v >= 0x80:
            self.b.append((v & 0x7F) | 0x80)
            v >>= 7
        self.b.append(v)

    def zigzag(self, v):
        self.varint(((v << 1) ^ (v >> 31)) & 0xFFFFFFFF)

    def string(self, s):
        data = s.encode("utf-8")
        self.varint(len(data))
        self.b += data


def normalize_color(color):
    if isinstance(color, str):
        t = color.strip()
        if t.startswith("#") and len(t) == 7:
            return t.upper()
        if len(t) == 6:
            return "#" + t.upper()
    return DEFAULT_COLOR


def normalize_icon(icon):
    return icon if isinstance(icon, str) and icon in ICON_INDEX else DEFAULT_ICON


def encode(pois, group_name=""):
    """Encode markers into a ``PZPOI2.`` payload string.

    Each marker is a dict with ``x``, ``y``, ``name`` and optionally ``desc``,
    ``color``, ``icon``, ``layer`` and ``rects`` (a list of
    ``{x, y, width, height}``).
    """
    w = _Writer()
    w.u8(VERSION)
    name = (group_name or "").strip()[:80]
    w.u8(HDR_FLAG_NAME if name else 0)
    if name:
        w.string(name)
    w.varint(len(pois))

    prev_x = prev_y = None
    for index, poi in enumerate(pois):
        layer = int(poi.get("layer") or 0)
        desc = poi.get("desc") or ""
        color = normalize_color(poi.get("color"))
        icon = normalize_icon(poi.get("icon"))
        category = poi.get("category") or DEFAULT_CATEGORY
        if category != DEFAULT_CATEGORY:
            raise ValueError("only the default category %r is supported" % DEFAULT_CATEGORY)
        rects = [r for r in (poi.get("rects") or [])
                 if int(r["width"]) > 0 and int(r["height"]) > 0]
        preset = COLOR_PRESETS.index(color) if color in COLOR_PRESETS else -1

        flags = 0
        if desc:
            flags |= F_DESC
        if color != DEFAULT_COLOR:
            flags |= F_COLOR
            if preset < 0:
                flags |= F_COLOR_RGB
        if icon != DEFAULT_ICON:
            flags |= F_ICON
        if rects:
            flags |= F_RECTS
        if layer != 0:
            flags |= F_LAYER
        if index > 0:
            flags |= F_DELTA

        w.u8(flags)
        if flags & F_DELTA:
            w.zigzag(int(poi["x"]) - prev_x)
            w.zigzag(int(poi["y"]) - prev_y)
        else:
            w.varint(int(poi["x"]))
            w.varint(int(poi["y"]))
        if flags & F_LAYER:
            w.zigzag(layer)
        w.string(poi["name"])
        if flags & F_DESC:
            w.string(desc)
        if flags & F_COLOR:
            if flags & F_COLOR_RGB:
                w.u8(int(color[1:3], 16))
                w.u8(int(color[3:5], 16))
                w.u8(int(color[5:7], 16))
            else:
                w.u8(preset)
        if flags & F_ICON:
            w.u8(ICON_INDEX.get(icon, 0))
        if flags & F_RECTS:
            w.varint(len(rects))
            for r in rects:
                w.varint(int(r["x"]))
                w.varint(int(r["y"]))
                w.varint(int(r["width"]))
                w.varint(int(r["height"]))
        prev_x, prev_y = int(poi["x"]), int(poi["y"])

    # CompressionStream('deflate') on the pzmap side is zlib-wrapped deflate
    raw = zlib.compress(bytes(w.b), 9)
    return PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def build_url(pois, group_name, build="42.20.0", base="https://pzmap.org/"):
    """Build one pzmap.org URL centred on the markers it carries."""
    payload = encode(pois, group_name)
    cx = sum(int(p["x"]) for p in pois) // len(pois)
    cy = sum(int(p["y"]) for p in pois) // len(pois)
    return "%s?%dx%dx0&v=%s&import=%s" % (base.rstrip("/") + "/", cx, cy, build, payload)


def split(pois, size=MAX_MARKERS_PER_LINK):
    """Split markers into even batches small enough for one import."""
    if not pois:
        return []
    nparts = (len(pois) + size - 1) // size
    per = (len(pois) + nparts - 1) // nparts
    return [pois[i:i + per] for i in range(0, len(pois), per)]
