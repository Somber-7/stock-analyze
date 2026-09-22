import sys
import os

# Third-party market libraries print Korean text and emoji on Windows.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8')

# PyInstaller 번들 실행 시 .env 경로를 exe 옆으로 맞춤
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

os.environ.setdefault('STOCK_BASE_DIR', base_dir)

import uvicorn
from backend.main import app
from backend.runtime import bind_server_socket

if __name__ == '__main__':
    with bind_server_socket(int(os.environ.get('STOCK_PORT', '8000'))) as server_socket:
        port = server_socket.getsockname()[1]
        print(f'STOCK_PORT={port}', flush=True)
        config = uvicorn.Config(app, host='127.0.0.1', port=port,
                                log_level='warning', access_log=False)
        uvicorn.Server(config).run(sockets=[server_socket])
