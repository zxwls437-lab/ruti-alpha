import json

from app import community
from app.db import SessionLocal
from app.models import Comment, CommunityVote, Post
from tests.conftest import make_admin, signup

YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_youtube_id():
    assert community.youtube_id(YT) == "dQw4w9WgXcQ"
    assert community.youtube_id("https://youtu.be/dQw4w9WgXcQ?t=10") == "dQw4w9WgXcQ"
    assert community.youtube_id("https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert community.youtube_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert community.youtube_id("https://evil.com/watch?v=dQw4w9WgXcQ") is None
    assert community.youtube_id("javascript:alert(1)") is None


def test_create_posts_and_validation(client):
    h = signup(client, "poster")
    q = client.post("/community/posts", headers=h, json={"kind": "question", "title": "레티놀이랑 비타민C 같이?", "body": "아침저녁 나눠 쓰는 게 나을까요?"})
    assert q.status_code == 201 and q.json()["post"]["kind_label"] == "질문"
    assert client.post("/community/posts", headers=h, json={"kind": "question", "title": "제목", "body": "짧"}).status_code == 422
    assert client.post("/community/posts", headers=h, json={"kind": "blog", "title": "제목", "body": "내용입니다"}).status_code == 422
    # 영상: 주소 확인 + 협찬 여부 필수
    assert client.post("/community/posts", headers=h, json={"kind": "video", "title": "루틴 영상", "video_url": "https://vimeo.com/1"}).status_code == 422
    r = client.post("/community/posts", headers=h, json={"kind": "video", "title": "루틴 영상", "video_url": YT})
    assert r.status_code == 422 and "협찬" in r.json()["detail"]
    v = client.post("/community/posts", headers=h, json={"kind": "video", "title": "루틴 영상", "video_url": YT, "sponsored": True}).json()["post"]
    assert v["video"]["thumbnail"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg" and v["sponsored"] is True
    assert v["video"]["embed_url"].startswith("https://www.youtube-nocookie.com/embed/")
    # 의약품 표현 감지
    m = client.post("/community/posts", headers=h, json={"kind": "talk", "title": "후기", "body": "이 크림 쓰고 아토피가 나았어요"}).json()
    assert m["post"]["medical_claim"] and m["notices"]


def test_feed_filters_and_product_check(client):
    from app.models import Ingredient
    with SessionLocal() as db:
        db.add_all([Ingredient(name_ko="정제수"), Ingredient(name_ko="글리세린"), Ingredient(name_ko="향료")])
        db.commit()
    a = signup(client, "dry1")
    client.post("/memory", headers=a, json={"content": "건성 피부"})
    client.post("/memory", headers=a, json={"content": "향료에 민감"})
    # 제품 전성분 공유(사진 대신 글자+제품명)
    client.post("/scan/text", headers=a, json={"text": "정제수, 글리세린, 향료", "product_name": "향기 로션"})
    client.post("/community/posts", headers=a, json={"kind": "video", "title": "건성 루틴", "video_url": YT, "sponsored": False, "product_name": "향기 로션"})
    b = signup(client, "oily1")
    client.post("/memory", headers=b, json={"content": "지성 피부"})
    client.post("/community/posts", headers=b, json={"kind": "question", "title": "지성 선크림", "body": "번들거리지 않는 선크림 있을까요?"})

    viewer = signup(client, "viewer9")
    client.post("/memory", headers=viewer, json={"content": "건성이고 향료에 민감해요"})
    feed = client.get("/community/posts", headers=viewer).json()
    assert feed["total"] == 2
    assert client.get("/community/posts", headers=viewer, params={"kind": "video"}).json()["total"] == 1
    sim = client.get("/community/posts", headers=viewer, params={"similar": True}).json()["posts"]
    assert [p["title"] for p in sim] == ["건성 루틴"]
    check = sim[0]["product_check"]
    assert check["found"] and check["level"] == "avoid"  # 보는 사람이 향료 민감
    assert sim[0]["skin_tags"] == ["건성", "민감성", "향료 민감"]


def test_comments_helpful_report_admin(client):
    author = signup(client, "auth9")
    pid = client.post("/community/posts", headers=author, json={"kind": "question", "title": "질문있어요", "body": "민감성 토너 추천해 주세요"}).json()["post"]["id"]
    others = [signup(client, f"c{i}user") for i in range(3)]
    cid = client.post(f"/community/posts/{pid}/comments", headers=others[0], json={"body": "저는 무향 토너 써요"}).json()["id"]
    client.post(f"/community/posts/{pid}/comments", headers=author, json={"body": "감사해요!"})
    d = client.get(f"/community/posts/{pid}", headers=others[1]).json()
    assert d["post"]["comment_count"] == 2 and [c["is_post_author"] for c in d["comments"]] == [False, True]
    assert client.post(f"/community/posts/{pid}/helpful", headers=author).status_code == 400
    assert client.post(f"/community/posts/{pid}/helpful", headers=others[1]).json()["helpful_count"] == 1
    # 댓글 신고 3건 → 숨김
    for o, reason in zip([author, others[1], others[2]], ["광고", "도배", "욕설"]):
        client.post(f"/community/comments/{cid}/report", headers=o, json={"reason": reason})
    assert len(client.get(f"/community/posts/{pid}", headers=others[1]).json()["comments"]) == 1
    admin = make_admin(client)
    items = client.get("/admin/community", headers=admin, params={"status": "hidden"}).json()["items"]
    assert items[0]["target"] == "comment" and sorted(items[0]["report_reasons"]) == ["광고", "도배", "욕설"]
    client.post(f"/admin/community/comment/{cid}/restore", headers=admin)
    assert len(client.get(f"/community/posts/{pid}", headers=others[1]).json()["comments"]) == 2
    client.post(f"/admin/community/post/{pid}/delete", headers=admin)
    with SessionLocal() as db:
        assert db.query(Post).count() == 0 and db.query(Comment).count() == 0 and db.query(CommunityVote).count() == 0


def test_delete_own_and_account_deletion(client):
    h = signup(client, "leaver")
    keep = signup(client, "stayer")
    pid = client.post("/community/posts", headers=keep, json={"kind": "talk", "title": "남는 글", "body": "이 글은 남아요"}).json()["post"]["id"]
    mine = client.post("/community/posts", headers=h, json={"kind": "talk", "title": "내 글", "body": "곧 탈퇴해요"}).json()["post"]["id"]
    client.post(f"/community/posts/{pid}/comments", headers=h, json={"body": "제 댓글이에요"})
    client.post(f"/community/posts/{pid}/helpful", headers=h)
    assert client.delete(f"/community/posts/{mine}", headers=keep).status_code == 404
    data = json.loads(client.get("/me/export", headers=h).content)
    assert data["posts"][0]["title"] == "내 글" and data["comments"][0]["body"] == "제 댓글이에요"
    client.request("DELETE", "/me", headers=h, json={"password": "password123"})
    post = client.get(f"/community/posts/{pid}", headers=keep).json()
    assert post["post"]["comment_count"] == 0 and post["comments"] == [] and post["post"]["helpful_count"] == 0 or post["post"]["comment_count"] == 0
    with SessionLocal() as db:
        assert db.query(Post).count() == 1
