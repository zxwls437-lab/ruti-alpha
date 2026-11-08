from tests.conftest import signup


def test_block_hides_content_everywhere(client):
    a, b = signup(client, "blocker"), signup(client, "troll1")
    pid = client.post("/community/posts", headers=b, json={"kind": "talk", "title": "광고글", "body": "제 쇼핑몰 오세요"}).json()["post"]["id"]
    mine = client.post("/community/posts", headers=a, json={"kind": "question", "title": "질문", "body": "토너 추천해 주세요"}).json()["post"]["id"]
    cid = client.post(f"/community/posts/{mine}/comments", headers=b, json={"body": "제 쇼핑몰 오세요"}).json()["id"]
    rid = client.post("/reviews", headers=b, json={"product_name": "어떤 크림", "rating": 1, "text": "별로예요 별로예요 별로예요"}).json()["review"]["id"]
    assert client.post("/blocks", headers=a, json={"target": "post", "id": mine}).status_code == 400
    assert client.post("/blocks", headers=a, json={"target": "post", "id": 999}).status_code == 404
    assert client.post("/blocks", headers=a, json={"target": "comment", "id": cid}).status_code == 201
    assert client.post("/blocks", headers=a, json={"target": "review", "id": rid}).status_code == 201  # 중복 차단은 무시
    assert [p["id"] for p in client.get("/community/posts", headers=a).json()["posts"]] == [mine]
    assert client.get(f"/community/posts/{pid}", headers=a).status_code == 404
    assert client.get(f"/community/posts/{mine}", headers=a).json()["comments"] == []
    assert client.get("/reviews", headers=a, params={"product": "어떤 크림"}).json()["total"] == 0
    # 다른 사람에게는 그대로 보임
    c = signup(client, "other1")
    assert client.get("/community/posts", headers=c).json()["total"] == 2
    blocks = client.get("/blocks", headers=a).json()["blocks"]
    assert len(blocks) == 1 and blocks[0]["nickname"]
    assert client.delete(f"/blocks/{blocks[0]['id']}", headers=c).status_code == 404
    client.delete(f"/blocks/{blocks[0]['id']}", headers=a)
    assert client.get("/community/posts", headers=a).json()["total"] == 2
