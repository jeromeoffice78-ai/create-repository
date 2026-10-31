import os, tempfile
fd,path=tempfile.mkstemp();os.close(fd)
os.environ['CUP_DB']=path
from fastapi.testclient import TestClient
from app import app
client=TestClient(app)
def test_health(): assert client.get('/health').json()['status']=='ok'
def test_precheck():
    r=client.post('/eligibility',json={'carrier':'Example','paid_off':True,'account_in_good_standing':True,'device_reported_lost_or_stolen':False,'ownership_confirmed':True})
    assert r.json()['precheck']=='ready_for_carrier_review'
    assert r.json()['carrier_decision']=='not_checked'
def test_request():
    r=client.post('/requests',json={'carrier':'Example','imei_last4':'1234','ownership_confirmed':True})
    assert r.status_code==200
    assert client.get('/requests/'+r.json()['id']).json()['status']=='draft'
def test_ownership_required():
    assert client.post('/requests',json={'carrier':'Example','imei_last4':'1234','ownership_confirmed':False}).status_code==400
