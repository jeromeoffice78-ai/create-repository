from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import sqlite3, os, uuid

app = FastAPI(title='Carrier Unlock Pro', version='0.1.0')
DB = os.getenv('CUP_DB', 'carrier_unlock.db')

def connect():
    db = sqlite3.connect(DB)
    db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, imei_last4 TEXT, carrier TEXT, status TEXT, notes TEXT)')
    return db

class Eligibility(BaseModel):
    carrier: str = Field(min_length=2, max_length=100)
    paid_off: bool
    account_in_good_standing: bool
    device_reported_lost_or_stolen: bool
    ownership_confirmed: bool

class Request(BaseModel):
    carrier: str = Field(min_length=2, max_length=100)
    imei_last4: str = Field(pattern=r'^\d{4}$')
    ownership_confirmed: bool
    notes: str = Field(default='', max_length=500)

@app.get('/health')
def health(): return {'status':'ok'}

@app.post('/eligibility')
def eligibility(data: Eligibility):
    blockers = []
    if not data.ownership_confirmed: blockers.append('Ownership not confirmed')
    if data.device_reported_lost_or_stolen: blockers.append('Reported lost or stolen')
    if not data.paid_off: blockers.append('Device financing not confirmed paid')
    if not data.account_in_good_standing: blockers.append('Account standing not confirmed')
    return {'precheck': 'review_required' if blockers else 'ready_for_carrier_review', 'blockers':blockers, 'carrier_decision':'not_checked', 'disclaimer':'Precheck is not a carrier eligibility determination. Carrier policies and legal obligations vary.'}

@app.post('/requests')
def create_request(data: Request):
    if not data.ownership_confirmed: raise HTTPException(400, 'Ownership confirmation required')
    request_id = str(uuid.uuid4())
    with connect() as db:
        db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',(request_id,data.imei_last4,data.carrier,'draft',data.notes))
    return {'id':request_id,'status':'draft','submitted_to_carrier':False}

@app.get('/requests/{request_id}')
def get_request(request_id: str):
    with connect() as db:
        row = db.execute('SELECT id,imei_last4,carrier,status,notes FROM requests WHERE id=?',(request_id,)).fetchone()
    if not row: raise HTTPException(404,'Request not found')
    return dict(zip(('id','imei_last4','carrier','status','notes'),row))
