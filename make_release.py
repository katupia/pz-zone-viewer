# -*- coding: utf-8 -*-
"""Build the release archive.

Zips only what is needed to run the app, with forward-slash separators so the
archive extracts correctly on Linux and macOS as well as Windows.

    python make_release.py
"""
import hashlib
import os
import zipfile

from pzzoneviewer import __version__

NAME = "pz-zone-viewer"
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "dist")

#: files that go in the release, in this order
FILES = [
    "main.py",
    "run.bat",
    "run.sh",
    "README.md",
    "LICENSE",
    "docs/screenshot.png",
    "pzzoneviewer/__init__.py",
    "pzzoneviewer/__main__.py",
    "pzzoneviewer/app.py",
    "pzzoneviewer/config.py",
    "pzzoneviewer/parsers.py",
    "pzzoneviewer/share.py",
    "pzzoneviewer/sources.py",
]

EXECUTABLE = {"run.sh"}


def build():
    os.makedirs(OUT_DIR, exist_ok=True)
    stem = "%s-%s" % (NAME, __version__)
    path = os.path.join(OUT_DIR, stem + ".zip")
    missing = [f for f in FILES if not os.path.isfile(os.path.join(ROOT, f))]
    if missing:
        raise SystemExit("missing from the tree: %s" % ", ".join(missing))

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in FILES:
            src = os.path.join(ROOT, rel)
            info = zipfile.ZipInfo(stem + "/" + rel)      # always "/"
            info.date_time = (2026, 1, 1, 0, 0, 0)        # reproducible archive
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if rel in EXECUTABLE else 0o644) << 16
            with open(src, "rb") as f:
                z.writestr(info, f.read())

    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(path + ".sha256", "w", encoding="utf-8") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(path)))
    return path, digest


if __name__ == "__main__":
    path, digest = build()
    size = os.path.getsize(path)
    print("%s  (%.1f KB, %d files)" % (path, size / 1024.0, len(FILES)))
    print("sha256  %s" % digest)
