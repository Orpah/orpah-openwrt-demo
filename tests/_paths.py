# -*- coding: utf-8 -*-
"""测试专用的 import 路径设置。**每个 test_*.py 与 fake_air.py 都要最先 import 本模块。**

让测试既能 `python tests/test_daemon.py` 跑，也能 `python -m unittest discover -s tests` 跑。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))

for _p in (ROOT, os.path.join(ROOT, "vendor", "orpah"), TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
