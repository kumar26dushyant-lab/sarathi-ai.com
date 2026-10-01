# -*- coding: utf-8 -*-
"""The Layout Planner's blocks (biz_nidaan_nav.BLOCKS) must be exactly the ops menu's options
(buildSidebar in static/nidaan_ops.html) - or the planner offers a block the menu does not have,
or misses one. Fails the build if they disagree.

    py -3.13 deploy/verify-nav-blocks.py
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import biz_nidaan_nav as nav  # noqa: E402

src = io.open(os.path.join(ROOT, "static", "nidaan_ops.html"), encoding="utf-8").read()
start = src.index("function buildSidebar")
body = src[start:src.index("const sb = document.getElementById('sidebar');", start)]
menu = re.findall(r"\{id:'([a-z0-9_]+)'", body)
planner = list(nav.BLOCK_IDS)
only_menu = [i for i in menu if i not in planner]
only_planner = [i for i in planner if i not in menu]
if only_menu or only_planner or len(set(menu)) != len(menu):
    print("  FAIL  menu and planner blocks differ")
    if only_menu:
        print("        in the menu, not the planner: " + ", ".join(only_menu))
    if only_planner:
        print("        in the planner, not the menu: " + ", ".join(only_planner))
    sys.exit(1)
print("  OK   the planner offers exactly the %d menu options" % len(menu))
