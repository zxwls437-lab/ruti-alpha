import gzip
import json

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

    class InlineThread:  # 테스트용 메모리 DB는 연결 하나를 같이 써서, 백그라운드 대신 바로 실행
        def __init__(self, target, **_kw):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(datasync.threading, "Thread", InlineThread)
    assert client.post("/admin/data/mfds-sync", headers=admin).status_code == 202
    assert datasync.job["state"] == "done", datasync.job
    with SessionLocal() as db:
        assert db.query(Ingredient).filter_by(name_ko="글리세린").count() == 1


def test_bulk_product_lists_preview_then_save(client):
    from tests.test_scan import seed_ingredients
    seed_ingredients()
    admin = make_admin(client)
    text = """라운드랩 | 독도 토너
정제수, 글리세린, 부틸렌글라이콜,
향료

브랜드 | 성분적은제품 | 정제수
브랜드만 |
정제수, 글리세린, 향료"""
    r = client.post("/admin/data/product-lists", json={"text": text, "dry_run": True}, headers=admin).json()
    assert [p["status"] for p in r["products"]] == ["ok", "error", "error"]
    assert r["products"][0]["count"] == 4
    assert client.get("/admin/data/product-lists", headers=admin).json()["items"] == []  # 미리 확인은 저장 안 함
    r = client.post("/admin/data/product-lists", json={"text": text, "dry_run": False}, headers=admin).json()
    assert r["ok"] == 1
    items = client.get("/admin/data/product-lists?q=독도", headers=admin).json()["items"]
    assert len(items) == 1 and items[0]["confirmations"] == datasync.ADMIN_CONFIRMATIONS
    # 사용자가 제품명만 알아도 등록된 전성분을 찾음
    from app import scan
    with SessionLocal() as db:
        assert scan.find_ingredient_list(db, "", "독도 토너") is not None
    assert client.delete(f"/admin/data/product-lists/{items[0]['id']}", headers=admin).status_code == 200
    user = signup(client, "normaluser")
    assert client.post("/admin/data/product-lists", json={"text": text}, headers=user).status_code == 403
