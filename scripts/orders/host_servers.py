import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

RUN = Path(os.environ['ORDERS_VALIDATION_RUN']).resolve()
ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
os.umask(0o077)
runtime = json.loads((RUN / 'runtime.json').read_text())
pid_file = RUN / 'pids.json'
pids = json.loads(pid_file.read_text()) if pid_file.exists() else {}
name = sys.argv[1]
action = sys.argv[2] if len(sys.argv) > 2 else 'start'
port = {'shared': 5000, 'mcp': 8100, 'rag': 8200}[name]
if action == 'stop':
    pid = pids.get(name)
    if pid:
        os.kill(pid, signal.SIGTERM)
        pids.pop(name)
        pid_file.write_text(json.dumps(pids))
        print(name, 'validation process stopped')
    raise SystemExit()
with socket.socket() as check:
    occupied = check.connect_ex(('127.0.0.1', port)) == 0
if occupied:
    raise SystemExit(name + ' port already occupied; refusing duplicate launch')
env = dict(os.environ)
if name == 'shared':
    env.update({k:runtime[k] for k in ['SECRET_KEY','ORDERS_MCP_SECRET','STAFF_PASSWORD']})
    env.update(STAFF_EMAIL=runtime['staff_email'], ORDERS_FRONTEND_ORIGIN='http://localhost:3004',
               PRODUCTS_API='http://localhost:5102', CUSTOMERS_API='http://localhost:5003', ORDERS_API='http://localhost:5004')
    command = [PY, '-m', 'flask', '--app', str(ROOT/'shared/backend/app.py'), 'run', '--host=127.0.0.1', '--port=5000']
elif name == 'mcp':
    env.update(ORDERS_API_URL='http://localhost:5004', MCP_HOST='0.0.0.0', MCP_PORT='8100')
    command = [PY, str(ROOT/'ai-services/mcp-server/server.py')]
else:
    env.update(PORT='8200', OLLAMA_MODEL='qwen2.5:0.5b', ANONYMIZED_TELEMETRY='False')
    command = [PY, str(ROOT/'scripts/orders/serve_rag.py')]
with (RUN / (name + '.log')).open('a') as log:
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
pids[name] = process.pid
pid_file.write_text(json.dumps(pids))
print(name, 'started; PID', process.pid)
