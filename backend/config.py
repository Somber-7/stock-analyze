import sys
import os
from dotenv import load_dotenv

# PyInstaller 번들 실행 시 exe 옆의 .env를 읽고,
# 일반 실행 시 프로젝트 루트의 .env를 읽음
if getattr(sys, 'frozen', False):
    base_dir = os.environ.get('STOCK_BASE_DIR', os.path.dirname(sys.executable))
else:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(base_dir, '.env'))


