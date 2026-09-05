# -*- coding: utf-8 -*-
"""Locate the game install, the user's Zomboid folder and every zone-defining mod."""

import os
import re
import sys

APP_ID = "108600"


# --------------------------------------------------------------------------- #
# platform paths
# --------------------------------------------------------------------------- #

def user_zomboid_dir():
    """The folder holding mods/, Saves/, Workshop/ -- same layout on every OS."""
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, "Zomboid")]
    if sys.platform == "darwin":
        candidates.insert(0, os.path.join(home, "Library", "Application Support", "Zomboid"))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def _steam_roots():
    home = os.path.expanduser("~")
    roots = []
    if os.name == "nt":
        for drive in "CDEFGH":
            roots += [r"%s:\Program Files (x86)\Steam" % drive,
                      r"%s:\Program Files\Steam" % drive,
                      r"%s:\Steam" % drive,
                      r"%s:\SteamLibrary" % drive]
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        for value in ("SteamPath", "InstallPath"):
                            try:
                                roots.insert(0, winreg.QueryValueEx(k, value)[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
    elif sys.platform == "darwin":
        roots.append(os.path.join(home, "Library", "Application Support", "Steam"))
    else:
        roots += [os.path.join(home, ".steam", "steam"),
                  os.path.join(home, ".steam", "root"),
                  os.path.join(home, ".local", "share", "Steam"),
                  os.path.join(home, ".var", "app", "com.valvesoftware.Steam",
                               "data", "Steam")]
    return [r for r in roots if r and os.path.isdir(r)]


def steam_libraries():
    """Every Steam library folder, read from libraryfolders.vdf where possible."""
    libs = []
    for root in _steam_roots():
        libs.append(root)
        for rel in (("steamapps", "libraryfolders.vdf"),
                    ("SteamApps", "libraryfolders.vdf")):
            vdf = os.path.join(root, *rel)
            if not os.path.isfile(vdf):
                continue
            try:
                with open(vdf, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            for m in re.finditer(r'"path"\s*"([^"]+)"', text):
                libs.append(m.group(1).replace("\\\\", "\\"))
    out = []
    for lib in libs:
        if os.path.isdir(lib) and lib not in out:
            out.append(lib)
    return out


def find_game_dir():
    """Folder containing ``media/maps`` -- the installed game."""
    names = ["ProjectZomboid", "Project Zomboid"]
    for lib in steam_libraries():
        for sub in ("steamapps", "SteamApps"):
            for name in names:
                p = os.path.join(lib, sub, "common", name)
                if os.path.isdir(os.path.join(p, "media", "maps")):
                    return p
    return ""


def find_workshop_dir():
    for lib in steam_libraries():
        for sub in ("steamapps", "SteamApps"):
            p = os.path.join(lib, sub, "workshop", "content", APP_ID)
            if os.path.isdir(p):
                return p
    return ""


# --------------------------------------------------------------------------- #
# mod discovery
# --------------------------------------------------------------------------- #

def _mod_name(mod_dir):
    """Prefer the human name from mod.info, fall back to the folder name."""
    for root, _dirs, files in os.walk(mod_dir):
        if "mod.info" in files:
            try:
                with open(os.path.join(root, "mod.info"), "r",
                          encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.lower().startswith("name="):
                            name = line.split("=", 1)[1].strip()
                            if name:
                                return name
            except OSError:
                pass
            break
        if root.count(os.sep) - mod_dir.count(os.sep) > 2:
            _dirs[:] = []
    return os.path.basename(mod_dir.rstrip(os.sep))


def list_mod_dirs(zomboid_dir, workshop_dir):
    """-> [(label, path)] for every installed mod, local first then Workshop."""
    out = []
    local = os.path.join(zomboid_dir, "mods")
    if os.path.isdir(local):
        for entry in sorted(os.listdir(local)):
            p = os.path.join(local, entry)
            if os.path.isdir(p):
                out.append((entry, p))
    if workshop_dir and os.path.isdir(workshop_dir):
        for entry in sorted(os.listdir(workshop_dir)):
            item = os.path.join(workshop_dir, entry, "mods")
            if not os.path.isdir(item):
                continue
            for sub in sorted(os.listdir(item)):
                p = os.path.join(item, sub)
                if os.path.isdir(p):
                    out.append(("%s (workshop %s)" % (sub, entry), p))
    return out


def game_map_dirs(game_dir):
    """-> [(map name, path)] for the base game's maps."""
    maps = os.path.join(game_dir, "media", "maps")
    if not os.path.isdir(maps):
        return []
    out = []
    for entry in sorted(os.listdir(maps)):
        p = os.path.join(maps, entry)
        if os.path.isfile(os.path.join(p, "objects.lua")):
            out.append((entry, p))
    return out
