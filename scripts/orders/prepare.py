import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(os.environ['ORDERS_VALIDATION_RUN']).resolve()
os.umask(0o077)
if RUN.is_relative_to(ROOT):
    raise SystemExit('Validation data must be outside the repository')
RUN.mkdir(mode=0o700, parents=True, exist_ok=True)
if (RUN / 'runtime.json').exists():
    raise SystemExit('Already prepared; refusing to overwrite runtime or snapshots.')
(RUN / "data").mkdir(exist_ok=True)
manifest = {}
for label, rel, container, source in [
    ('orders', 'student-4/database/orders.db', 'student-4-database-1', '/app/database/orders.db'),
    ('customers', 'student-3/database/customer.db', 'retail-management-student3-database-1', '/app/database/customer.db'),
    ('products', 'student-2/database/data/products.db', None, None),
]:
    original = ROOT / rel
    manifest[rel] = hashlib.sha256(original.read_bytes()).hexdigest()
    backup = RUN / (label + '-snapshot.db')
    if container:
        subprocess.run(['docker', 'cp', f'{container}:{source}', str(backup)], check=True, capture_output=True)
    else:
        with sqlite3.connect(f'file:{original}?mode=ro', uri=True) as src, sqlite3.connect(backup) as dst:
            src.backup(dst)
    with sqlite3.connect(f'file:{backup}?mode=ro', uri=True) as src, sqlite3.connect(RUN / 'data' / (label + '.db')) as dst:
        src.backup(dst)
    manifest[label + '-container-snapshot' if container else label + '-snapshot'] = hashlib.sha256(backup.read_bytes()).hexdigest()
    print(label + ': snapshot and independent working copy ready')
(RUN / 'original-hashes.json').write_text(json.dumps(manifest, indent=2))
runtime = {name: secrets.token_hex(32) for name in ['SECRET_KEY', 'ORDERS_MCP_SECRET', 'STAFF_PASSWORD']}
runtime.update({'email': secrets.token_hex(8) + '@example.test', 'other_email': secrets.token_hex(8) + '@example.test',
                'password': secrets.token_urlsafe(20), 'staff_email': secrets.token_hex(8) + '@example.test'})
(RUN / 'runtime.json').write_text(json.dumps(runtime))
(RUN / 'compose.env').write_text('ORDERS_MCP_SECRET=' + runtime['ORDERS_MCP_SECRET'] + '\n')
(RUN / 'login.txt').write_text('Temporary validation accounts (copied DB only)\nCustomer email: ' + runtime['email'] + '\nCustomer password: ' + runtime['password'] + '\nStaff email: ' + runtime['staff_email'] + '\nStaff password: ' + runtime['STAFF_PASSWORD'] + '\n')
(RUN / 'Dockerfile').write_text('FROM python:3.11-slim\nCOPY student-4/backend/requirements.txt /tmp/requirements.txt\nRUN pip install --no-cache-dir -r /tmp/requirements.txt\nENV PYTHONUNBUFFERED=1\n')
(RUN / 'data' / 'serve_db.py').write_text("import os,sys\nsys.path.insert(0,'/app')\nimport app\nsetattr(app, os.environ['DB_ATTRIBUTE'], os.environ['DB_FILE'])\napp.app.run(host='0.0.0.0', port=int(os.environ['DB_PORT']), debug=False)\n")

def service(folder, port, environment=None):
    return {'image': 'orders-mcp-validation:local', 'working_dir': '/app',
            'command': ['python', '-m', 'flask', '--app', '/app/app.py', 'run', '--host=0.0.0.0', f'--port={port}'],
            'volumes': [f'{ROOT / folder}:/app:ro'],
            'ports': [f'127.0.0.1:{port}:{port}'], 'environment': environment or {}}
services = {}
for name, folder, port, label, attr in [
    ('orders-db', 'student-4/database', 6004, 'orders', 'DB_PATH'),
    ('customers-db', 'student-3/database', 6003, 'customers', 'DB_PATH'),
    ('products-db', 'student-2/database', 6002, 'products', 'DATABASE_NAME'),
]:
    s = service(folder, port, {'DB_FILE': '/data/' + label + '.db', 'DB_ATTRIBUTE': attr, 'DB_PORT': str(port)})
    s['command'] = ['python', '/data/serve_db.py']
    s['volumes'].append(f'{RUN / "data"}:/data')
    services[name] = s
services['orders-backend'] = service('student-4/backend', 5004, {
    'DATABASE_URL': 'http://orders-db:6004', 'OLLAMA_URL': 'http://host.docker.internal:11434/api/generate',
    'OLLAMA_MODEL': 'qwen2.5:0.5b', 'MCP_ENABLED': 'true',
    'MCP_URL': 'http://host.docker.internal:8100/mcp', 'ORDERS_MCP_SECRET': '${ORDERS_MCP_SECRET:?required}',
    'RAG_URL': 'http://host.docker.internal:8200', 'RAG_ENABLED': 'true',
})
services['orders-backend']['volumes'].append(f'{ROOT / "student-4/prompts"}:/prompts:ro')
services['orders-frontend'] = service('student-4/frontend', 3004, {'API_BASE': 'http://localhost:5004', 'SHARED_BASE': 'http://localhost:5000'})
services['customers-backend'] = service('student-3/backend', 5003, {'DATABASE_URL': 'http://customers-db:6003'})
services['customers-backend']['volumes'].extend([f'{ROOT / "student-3/frontend"}:/frontend:ro', f'{ROOT / "student-3/prompts"}:/prompts:ro'])
# Products DB API already implements the read routes needed by shared shop; use the real Products backend on a free port.
services['products-backend'] = service('student-2/backend', 5102, {'DATABASE_URL': 'http://products-db:6002'})
services['products-backend']['volumes'].extend([f'{ROOT / "student-2/prompts"}:/prompts:ro'])
(RUN / 'compose.json').write_text(json.dumps({'name': 'orders-mcp-validation', 'services': services}, indent=2))
print('Prepared isolated Compose and private credentials. No original DB modified; no keys printed.')
