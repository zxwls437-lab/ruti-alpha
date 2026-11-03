import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['RUTI_API_TOKEN'] = 'test-token'
os.environ.pop('OPENAI_API_KEY', None)
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
HEADERS = {'Authorization': 'Bearer test-token', 'x-ruti-user': 'testuser1'}

def test_health_and_status():
    assert client.get('/health').json()['status'] == 'ok'
    assert client.get('/status').json()['estimated_progress_percent'] == 35

def test_auth_required():
    assert client.get('/memory').status_code == 401

def test_memory_and_safety():
    created = client.post('/memory', headers=HEADERS, json={'content': '가벼운 제형 선호'})
    assert created.status_code == 201
    assert len(client.get('/memory', headers=HEADERS).json()['memories']) >= 1
    safe = client.post('/conversation', headers=HEADERS, json={'message': '호흡곤란이 있어요'}).json()
    assert safe['status'] == 'SAFETY_HOLD'

def test_unapproved_products_not_searched():
    staged = client.post('/products/stage', headers=HEADERS, json={'name': '테스트 제품'})
    assert staged.status_code == 201
    assert staged.json()['approved'] is False
    assert client.get('/products/search', headers=HEADERS).json()['products'] == []
