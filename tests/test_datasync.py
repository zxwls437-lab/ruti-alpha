import gzip
import json
import time

from app import datasync, mfds
from app.db import SessionLocal
from app.models import Ingredient
from tests.conftest import make_admin, signup


def _upload(client, headers, raw):
    return client.post("/admin/data/ingredients-import", content=raw,
                       headers={**headers, "Content-Type": "application/octet-stream"})


def test_import_export_roundtrip_admin_only(client):
    user = signup(client, "normaluser")
    admin = make_admin(client)
    payload = {"format": "ruti-ingredients-v1", "ingredients": [
        {"name_ko": "향료", "name_en": "Fragrance"},
        {"name_ko": "페녹시에탄올", "restriction": "[대한민국] 배합한도 1%"},
        {"name_ko": "", "name_en": "skip me"},
    ]}
    raw = gzip.compress(json.dumps(payload, ensure_ascii=False).encode())
    assert _upload(client, user, raw).status_code == 403
    r = _upload(client, admin, raw)
    assert r.status_code == 200 and r.json() == {"imported": 2, "restricted": 1}
    # 업로드한 성분이 바로 분석에 쓰임 (색인 초기화)
    scan = client.post("/scan/text", json={"text": "정제수, 향료"}, headers=admin).json()
    assert any(i["ingredient"] and i["ingredient"]["name_ko"] == "향료" for i in scan["items"])
    st = client.get("/admin/data/status", headers=admin).json()
    assert st["ingredients"] == 2 and st["restricted"] == 1
    exp = client.get("/admin/data/ingredients-export", headers=admin)
    data = json.loads(gzip.decompress(exp.content))
    assert data["count"] == 2 and {r["name_ko"] for r in data["ingredients"]} == {"향료", "페녹시에탄올"}
    # 같은 파일을 다시 올리면 개수가 그대로 (교체)
    assert _upload(client, admin, exp.content).json()["imported"] == 2


def test_import_rejects_bad_files(client):
    admin = make_admin(client)
    assert _upload(client, admin, b"not json").status_code == 400
    assert _upload(client, admin, json.dumps({"ingredients": []}).encode()).status_code == 400
    assert _upload(client, admin, b"").status_code == 400


def test_mfds_sync_needs_key_and_runs_in_background(client, monkeypatch):
    admin = make_admin(client)
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    assert client.post("/admin/data/mfds-sync", headers=admin).status_code == 400
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "dummy")
    pages = {"ingredient": [{"INGR_KOR_NAME": "글리세린", "INGR_ENG_NAME": "Glycerin"}], "restricted": []}
    monkeypatch.setattr(mfds, "iter_pages", lambda d, rows=100, max_pages=0: iter([(1, len(pages.get(d, [])), pages.get(d, []))]))
    datasync.job.update(state="idle")
    assert client.post("/admin/data/mfds-sync", headers=admin).status_code == 202
    for _ in range(50):
        if datasync.job["state"] != "running":
            break
        time.sleep(0.05)
    assert datasync.job["state"] == "done", datasync.job
    with SessionLocal() as db:
        assert db.query(Ingredient).filter_by(name_ko="글리세린").count() == 1
