"""Protected cloud integration, with billable submissions deliberately unavailable."""
import os
import secrets
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from app import app as draft_app
from unlockbase import query, ProviderError

app = FastAPI(title='Carrier Unlock Pro', version='0.2.0')
app.include_router(draft_app.router)

@app.middleware('http')
async def protect(request, call_next):
    public = request.url.path in {'/', '/health'}
    if not public:
        expected = os.getenv('CUP_ADMIN_TOKEN', '')
        received = request.headers.get('authorization', '').removeprefix('Bearer ')
        if not expected or not secrets.compare_digest(received, expected):
            return JSONResponse({'detail': 'Authentication required'}, status_code=401)
        if request.url.path.startswith('/requests') and request.method != 'GET':
            return JSONResponse({'detail': 'Cloud draft storage requires a durable database'}, status_code=503)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

async def provider(action, parameters=None):
    try:
        return await query(action, parameters)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from None

@app.get('/', response_class=HTMLResponse)
def home():
    return '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>Carrier Unlock Pro</title><body style="font:18px system-ui;max-width:680px;margin:60px auto;padding:24px"><h1>Carrier Unlock Pro</h1><p>Authorized UnlockBase XML API integration service.</p><p>Account connection, service catalog and order status require the administrator bearer token stored in Render.</p><p>Paid unlock submissions and checkout are not enabled.</p></body></html>'

@app.get('/provider/account')
async def account():
    root = await provider('AccountInfo')
    if any(root.find(k) is None for k in ['Email', 'Credits', 'Currency']):
        raise HTTPException(502, 'Incomplete account response')
    return {'provider': 'UnlockBase', 'connected': True,
            'credits': root.findtext('Credits'), 'currency': root.findtext('Currency'),
            'paid_orders_enabled': False}

@app.get('/provider/services')
async def services():
    root = await provider('GetTools')
    return {'provider': 'UnlockBase', 'services': [
        {'id': t.findtext('ID'), 'name': t.findtext('Name'),
         'credits': t.findtext('Credits'), 'group': g.findtext('Name'),
         'requirements': {c.tag.removeprefix('Requires.'): c.text for c in t if c.tag.startswith('Requires.')}}
        for g in root.findall('Group') for t in g.findall('Tool')]}

@app.get('/provider/orders/{order_id}')
async def order(order_id: str):
    if not order_id.isascii() or not order_id.isdigit() or len(order_id) > 20:
        raise HTTPException(422, 'Numeric provider order ID required')
    root = await provider('GetOrders', {'ID': order_id})
    matches = [o for o in root.findall('Order') if o.findtext('ID') == order_id]
    if not matches:
        raise HTTPException(404, 'Provider order not found')
    o = matches[0]
    return {'id': order_id, 'status': o.findtext('Status'),
            'available': o.findtext('Available'), 'imei_last4': (o.findtext('IMEI') or '')[-4:]}

@app.post('/provider/orders')
def disabled_order():
    raise HTTPException(503, 'Paid orders require approved pricing, payment verification and durable idempotency')
