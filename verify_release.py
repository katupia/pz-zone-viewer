# -*- coding: utf-8 -*-
"""Check the release archive: contents, separators, and that it actually runs."""
import os
import subprocess
import sys
import tempfile
import zipfile

ZIP = os.path.join("dist", "pz-zone-viewer-1.0.0.zip")

z = zipfile.ZipFile(ZIP)
names = [i.filename for i in z.infolist()]
print("archive: %s  (%.1f KB)" % (ZIP, os.path.getsize(ZIP) / 1024.0))
for i in z.infolist():
    print("  %-52s %6d o  mode %o" % (i.filename, i.file_size, i.external_attr >> 16))

bad = [n for n in names if "\\" in n]
print("\nseparateurs backslash : %s" % (bad or "aucun"))
tops = {n.split("/")[0] for n in names}
print("dossier racine unique : %s" % (tops if len(tops) == 1 else "NON: %s" % tops))

with tempfile.TemporaryDirectory() as tmp:
    z.extractall(tmp)
    root = os.path.join(tmp, list(tops)[0])
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import py_compile, os\n"
        "for base, _d, fs in os.walk(%r):\n"
        "    for f in fs:\n"
        "        if f.endswith('.py'): py_compile.compile(os.path.join(base, f), doraise=True)\n"
        "from pzzoneviewer import share, parsers, sources, config\n"
        "u = share.build_url([{'x':100,'y':200,'name':'t',"
        "'rects':[{'x':100,'y':200,'width':3,'height':5}]}], 'test')\n"
        "assert u.startswith('https://pzmap.org/?100x200x0'), u\n"
        "zs = parsers.parse_text('{ name = \"a\", type = \"ParkingStall\", x = 1+1, y = 2, "
        "z = 0, width = 3, height = 5 }')\n"
        "assert len(zs) == 1 and zs[0].x == 2, zs\n"
        "import pzzoneviewer.app as app\n"
        "print('extracted package: compiles, imports, builds a URL, parses a zone')\n"
    ) % (root, root)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    print("\n" + (r.stdout or "").strip())
    if r.returncode:
        print(r.stderr.strip())
        sys.exit(1)

print("\nRELEASE OK")
