import os
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

RUN=Path(os.environ['ORDERS_VALIDATION_RUN']).resolve()
ROOT=Path(__file__).resolve().parents[2]
expected=json.loads((RUN/'original-hashes.json').read_text())
result={}
for rel,digest in expected.items():
    if rel.startswith('student-'):
        result[rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest
for label,container,source in [('orders','student-4-database-1','/app/database/orders.db'),('customers','retail-management-student3-database-1','/app/database/customer.db')]:
    with tempfile.TemporaryDirectory(dir=RUN) as directory:
        target=Path(directory)/'check.db'
        subprocess.run(['docker','cp',container+':'+source,str(target)],check=True,capture_output=True)
        result[label+' original container DB unchanged']=hashlib.sha256(target.read_bytes()).hexdigest()==expected[label+'-container-snapshot']
print('Original DB preservation:',json.dumps(result))
assert all(result.values())
probe="import os,requests; u=os.environ['MCP_URL']; print('Docker MCP target:',u); r=requests.get(u,timeout=5); print('MCP HTTP status:',r.status_code); r=requests.get('http://host.docker.internal:11434/api/tags',timeout=5); print('Docker-to-Ollama HTTP status:',r.status_code)"
subprocess.run(['docker','exec','orders-mcp-validation-orders-backend-1','python','-c',probe],check=True)
logs=subprocess.run(['docker','logs','orders-mcp-validation-orders-backend-1'],capture_output=True,text=True,check=True)
lines=(logs.stdout+logs.stderr).splitlines()
internal=[line for line in lines if '/api/internal/mcp/orders/' in line and 'GET ' in line]
print('Internal Orders callbacks recorded:',len(internal))
print('Internal HTTP statuses:',{status:sum((' '+status+' ') in line for line in internal) for status in ['200','401','403','404']})
subprocess.run(['docker','ps','-a','--format','{{.Names}}\t{{.Status}}\t{{.Ports}}'],check=True)
(RUN/'preservation-results.json').write_text(json.dumps(result,indent=2))
