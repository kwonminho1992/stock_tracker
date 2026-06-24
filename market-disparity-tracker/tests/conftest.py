"""테스트가 scripts/ 의 모듈을 import 할 수 있도록 경로를 추가한다."""
import os
import sys

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
