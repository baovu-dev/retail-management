import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import requests
from playwright.sync_api import sync_playwright, expect
from validation_checks import mcp_success, result_exit_code, route_resource

RUN = Path(os.environ['ORDERS_VALIDATION_RUN']).resolve()
os.umask(0o077)
runtime = json.loads((RUN/'runtime.json').read_text())
report = []
if (RUN/'browser-results.json').exists():
    (RUN/('browser-attempt-' + str(int(time.time())) + '.json')).write_text((RUN/'browser-results.json').read_text())
stage = 'readiness'
def record(name, ok, detail):
    report.append({'check': name, 'result': 'PASS' if ok else 'FAIL', 'detail': detail})
    (RUN/'browser-results.json').write_text(json.dumps(report, indent=2))
    print(('PASS ' if ok else 'FAIL ') + name + ': ' + str(detail), flush=True)
def require(condition, name, detail):
    record(name, bool(condition), detail)
    if not condition: raise RuntimeError(name)
def wait_mcp():
    for _ in range(40):
        try:
            requests.get('http://localhost:8100/mcp', timeout=1); return
        except requests.RequestException: time.sleep(.25)
    raise RuntimeError('MCP readiness')
def check_mcp(page, order_id):
    page.locator('#mcpOrderId').fill(str(order_id))
    with page.expect_response(lambda r: '/api/mcp/order-status' in r.url, timeout=30000) as captured:
        page.get_by_role('button', name='Check with MCP').click()
    expect(page.locator('#mcpStatusButton')).to_be_enabled(timeout=30000)
    response = captured.value
    return response.status, response.json(), page.locator('#mcpStatusResult').inner_text()

try:
    for url in ['http://localhost:5000/', 'http://localhost:3004/', 'http://localhost:5004/api/health', 'http://localhost:5003/', 'http://localhost:5102/products']:
        response=requests.get(url,timeout=10)
        require(response.status_code==200,'ready '+url, response.status_code)
    models=requests.get('http://localhost:11434/api/tags',timeout=5).json()
    record('local Ollama models',True,[m['name'] for m in models.get('models',[])])

    stage='test data'
    for email_key, id_key in [('email','customer_id'),('other_email','other_customer_id')]:
        if id_key not in runtime:
            logged=requests.post('http://localhost:5003/login',json={'email':runtime[email_key],'password':runtime['password']},timeout=10)
            if logged.status_code==401:
                response=requests.post('http://localhost:5003/register',json={'first_name':'MCP','last_name':'Validation','email':runtime[email_key],'password':runtime['password']},timeout=10)
                require(response.status_code==201,'register '+id_key,response.status_code)
                logged=requests.post('http://localhost:5003/login',json={'email':runtime[email_key],'password':runtime['password']},timeout=10)
            require(logged.status_code==200,'real customer authentication '+id_key,logged.status_code)
            runtime[id_key]=logged.json()['customer_id']
            (RUN/'runtime.json').write_text(json.dumps(runtime))
    if 'order_id' not in runtime:
        product=requests.get('http://localhost:5102/products',timeout=5).json()[0]
        runtime['product_id']=product['product_id']
        for customer_key, order_key in [('customer_id','order_id'),('other_customer_id','other_order_id')]:
            response=requests.post('http://localhost:5004/api/orders',json={'customer_id':runtime[customer_key], 'items':[{'product_id':product['product_id'],'quantity':1,'unit_price':product['price']}]},timeout=10)
            require(response.status_code==201,'create isolated '+order_key,response.status_code)
            runtime[order_key]=response.json()['order_id']
            (RUN/'runtime.json').write_text(json.dumps(runtime))

    stage='browser login'
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        record('Chrome launch', True, browser.version)
        context=browser.new_context(viewport={'width':1280,'height':900})
        context.route('**/*', route_resource)
        page=context.new_page()
        page.set_default_timeout(15000)
        cors=[]
        def observe(response):
            if '/api/orders/mcp-token' in response.url:
                headers=response.headers
                cors.append({'status':response.status,'allow_origin':headers.get('access-control-allow-origin'), 'allow_credentials':headers.get('access-control-allow-credentials')})
        page.on('response',observe)
        page.goto('http://localhost:5000/',wait_until='domcontentloaded')
        page.get_by_role('link',name='Log in',exact=True).first.click()
        page.locator('#email').fill(runtime['email'])
        page.locator('#password').fill(runtime['password'])
        page.get_by_role('button',name='Log In',exact=True).click()
        expect(page).to_have_url('http://localhost:5000/')
        require(any(c['name']=='session' and c['httpOnly'] for c in context.cookies()),'real login cookie','HttpOnly session cookie present; value omitted')
        page.get_by_role('link',name='My Orders',exact=True).first.click()
        expect(page).to_have_url(re.compile(r'http://localhost:3004/\?customer_id='))
        stage='MCP normal'
        status,payload,text=check_mcp(page,runtime['order_id'])
        require(mcp_success(status, payload, text, runtime['order_id'], 'PENDING'),'browser MCP success',{'http':status,'screen':text})
        require(any(c['status']==200 and c['allow_origin']=='http://localhost:3004' and c['allow_credentials']=='true' for c in cors),'credentialed browser CORS',cors)
        page.screenshot(path=str(RUN/'mcp-success.png'),full_page=True)

        # Keep this token only in page memory while real wall-clock time elapses.
        page.evaluate('''async (id) => { const r=await fetch('http://localhost:5000/api/orders/mcp-token',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:id})}); window.validationToken=(await r.json()).access_token; }''',runtime['order_id'])
        issued=time.monotonic()
        stage='ownership'
        status,payload,text=check_mcp(page,runtime['other_order_id'])
        require(status==403,'other customer denied',{'http':status,'screen':text})
        forged=page.evaluate('''async (id)=>{const r=await fetch('http://localhost:5004/api/mcp/order-status',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer forged','X-Customer-ID':'1'},body:JSON.stringify({order_id:id})});return r.status;}''',runtime['order_id'])
        require(forged==401,'forged token/header denied',forged)

        stage='existing order details'
        card=page.locator('.order-card').filter(has=page.locator('h2',has_text=re.compile(r'^\s*#'+str(runtime['order_id'])+r'\s*$')))
        card.get_by_role('button',name='View Details',exact=True).click()
        expect(page.locator('#orderModal')).to_be_visible()
        require(str(runtime['order_id']) in page.locator('#orderDetail').inner_text(),'existing order details', 'modal shows owned test order')
        page.locator('#modalClose').click()

        stage='existing AI'
        page.locator('#assistantOrderId').fill(str(runtime['order_id']))
        page.locator('#assistantQuestion').fill('What is the current status of this order?')
        with page.expect_response(lambda r:'/api/order-assistant' in r.url,timeout=45000) as ai_capture:
            page.get_by_role('button',name=re.compile('Ask AI')).click()
        ai=ai_capture.value
        body=ai.json()
        record('existing AI endpoint', ai.status==200, {'http':ai.status,'source':body.get('source'),'answer_present':bool(body.get('answer'))})
        record('actual Ollama generation', body.get('source')=='ollama', {'source':body.get('source')})

        stage='existing shop order creation'
        shop=context.new_page()
        shop.goto('http://localhost:5000/shop',wait_until='domcontentloaded')
        shop.get_by_role('link',name='Order Now',exact=True).first.click()
        shop.get_by_role('button',name='Place Order',exact=True).click()
        expect(shop).to_have_url(re.compile(r'/order-success/\d+$'))
        runtime['created_order_id']=int(shop.url.rsplit('/',1)[1])
        (RUN/'runtime.json').write_text(json.dumps(runtime))
        record('shared shop create order',True,{'order_id':runtime['created_order_id']})
        shop.close()

        stage='staff dashboard and status update'
        staff_context=browser.new_context()
        staff_context.route('**/*', route_resource)
        staff=staff_context.new_page()
        staff.on('dialog',lambda d:d.accept())
        staff.goto('http://localhost:5000/staff-login',wait_until='domcontentloaded')
        staff.locator('input[name=email]').fill(runtime['staff_email'])
        staff.locator('input[name=password]').fill(runtime['STAFF_PASSWORD'])
        staff.locator('button[type=submit]').click()
        expect(staff).to_have_url('http://localhost:5000/staff_dashboard')
        staff.get_by_role('link',name=re.compile('View all orders')).click()
        expect(staff).to_have_url('http://localhost:3004/admin')
        staffcard=staff.locator('.order-card').filter(has=staff.locator('h2',has_text=re.compile(r'^\s*#'+str(runtime['created_order_id'])+r'\s*$')))
        staffcard.get_by_role('button',name='Confirm',exact=True).click()
        expect(staff.locator('#statusMessage')).to_contain_text('confirmed successfully')
        staff.get_by_role('link',name='Staff Dashboard',exact=True).click()
        require(staff.url=='http://localhost:5000/staff_dashboard','admin return across origins',staff.url)
        record('existing staff confirm order',True,{'order_id':runtime['created_order_id']})
        staff_context.close()

        stage='existing customer cancel'
        page.on('dialog',lambda d:d.accept())
        # Reload would lose the in-memory expiry token: refresh only the order list.
        page.evaluate('loadOrders()')
        cancelcard=page.locator('.order-card').filter(has=page.locator('h2',has_text=re.compile(r'^\s*#'+str(runtime['created_order_id'])+r'\s*$')))
        cancelcard.get_by_role('button',name='Cancel',exact=True).click()
        expect(page.locator('#statusMessage')).to_contain_text('cancelled successfully')
        record('existing customer cancel order',True,{'order_id':runtime['created_order_id']})

        stage='MCP outage'
        subprocess.run([sys.executable,str(Path(__file__).with_name('host_servers.py')),'mcp','stop'],check=True,capture_output=True)
        time.sleep(1)
        try:
            status,payload,text=check_mcp(page,runtime['order_id'])
            require(status==503 and 'unavailable' in text.lower(),'MCP outage screen',{'http':status,'screen':text})
            page.screenshot(path=str(RUN/'mcp-outage.png'),full_page=True)
        finally:
            subprocess.run([sys.executable,str(Path(__file__).with_name('host_servers.py')),'mcp'],check=True,capture_output=True)
            wait_mcp()
        status,payload,text=check_mcp(page,runtime['order_id'])
        require(mcp_success(status, payload, text, runtime['order_id'], 'PENDING'),'MCP recovery',{'http':status,'screen':text})

        stage='real token expiry'
        while time.monotonic()-issued<123:
            remaining=123-(time.monotonic()-issued)
            print('Waiting for real token expiry:',round(remaining),'seconds',flush=True)
            time.sleep(min(20,remaining))
        expired=page.evaluate('''async (id)=>{const r=await fetch('http://localhost:5004/api/mcp/order-status',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+window.validationToken},body:JSON.stringify({order_id:id})}); const body=await r.json();delete window.validationToken;return {status:r.status,error:body.error};}''',runtime['order_id'])
        require(expired['status']==401 and 'expired' in expired['error'].lower(),'real 120-second expiry',expired)
        status,payload,text=check_mcp(page,runtime['order_id'])
        require(mcp_success(status, payload, text, runtime['order_id'], 'PENDING'),'fresh token retry from UI',{'http':status,'screen':text})
        browser.close()
except Exception as exc:
    # Never dump browser call arguments, passwords, cookies or bearer tokens.
    message=str(exc).split('Call log:')[0]
    for key in ['password','SECRET_KEY','ORDERS_MCP_SECRET','STAFF_PASSWORD']:
        message=message.replace(runtime[key], '[REDACTED]')
    record(stage,False,{'exception_type':type(exc).__name__, 'message':message[:400]})
    raise SystemExit(1)

raise SystemExit(result_exit_code(report))
