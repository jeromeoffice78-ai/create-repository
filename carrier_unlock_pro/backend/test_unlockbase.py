import os
import httpx
import pytest
from fastapi.testclient import TestClient
import unlockbase
from cloud import app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('CUP_ADMIN_TOKEN', 'test-admin')
    monkeypatch.setenv('UNLOCKBASE_API_KEY', 'test-provider')
    return TestClient(app)

@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient
    def install(handler):
        monkeypatch.setattr(unlockbase.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    return install

def test_auth_and_billable_disabled(client):
    assert client.get('/health').status_code == 200
    assert client.get('/provider/account').status_code == 401
    h = {'Authorization': 'Bearer test-admin'}
    assert client.post('/provider/orders', headers=h).status_code == 503
    assert client.post('/requests', json={}, headers=h).status_code == 503

def test_actual_contract_fields(client, transport):
    def handler(req):
        assert str(req.url) == unlockbase.ENDPOINT
        assert req.method == 'POST'
        assert b'Key=test-provider' in req.content
        assert b'Action=AccountInfo' in req.content
        return httpx.Response(200, text='<API><Email>owner@example.com</Email><Credits>0.00</Credits><Currency>USD</Currency></API>')
    transport(handler)
    r = client.get('/provider/account', headers={'Authorization':'Bearer test-admin'})
    assert r.status_code == 200
    assert r.json()['connected'] is True
    assert 'test-provider' not in r.text
    assert 'owner@example.com' not in r.text

def test_rejected_xml_and_secret_redaction(client, transport):
    transport(lambda req: httpx.Response(200,text='<API><Error>test-provider private data</Error></API>'))
    r = client.get('/provider/account', headers={'Authorization':'Bearer test-admin'})
    assert r.status_code == 502
    assert 'test-provider' not in r.text

def test_order_filter(client, transport):
    transport(lambda req: httpx.Response(200,text='<API><Order><ID>98</ID><IMEI>123456789012345</IMEI><Status>Waiting</Status></Order></API>'))
    h = {'Authorization':'Bearer test-admin'}
    assert client.get('/provider/orders/99',headers=h).status_code == 404
    r=client.get('/provider/orders/98',headers=h)
    assert r.json()['imei_last4']=='2345'
    assert '123456789012345' not in r.text

def test_entity_payload_rejected(client, transport):
    transport(lambda req: httpx.Response(200,text='<!DOCTYPE API [<!ENTITY x "secret">]><API><Email>&x;</Email></API>'))
    assert client.get('/provider/account',headers={'Authorization':'Bearer test-admin'}).status_code == 502
