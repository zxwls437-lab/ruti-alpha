"""데모용 예시 데이터 넣기 (미리보기·시연용). 실제 운영 DB에는 쓰지 마세요.

사용법:  DATABASE_URL=sqlite:///./demo.db python -m scripts.demo_seed
- 회원이 이미 있는 DB에는 넣지 않는다 (실수 방지).
- 체험 계정: 아이디 demo / 비밀번호 ruti1234
- 성분 규제 문구는 화면 시연용 예시이며, 실제 규제 정보는 식약처 데이터로 확인해야 한다.
"""
import json
import sys

from sqlalchemy import func, select

from app import account
from app.db import SessionLocal, init_db
from app.models import Ingredient, Memory, Post, ProductIngredientList, Review, ScanResult, User
from app.scan import analyze, name_key, normalize
from app.security import hash_password

INGREDIENTS = [
    ("정제수", "Water", "", ""), ("글리세린", "Glycerin", "보습제", "[중국] 제한 - 불순물 기준 (데모)"),
    ("부틸렌글라이콜", "Butylene Glycol", "보습제", ""), ("나이아신아마이드", "Niacinamide", "비타민 B3 유도체", ""),
    ("판테놀", "Panthenol", "프로비타민 B5", ""), ("세라마이드엔피", "Ceramide NP", "피부 컨디셔닝제", ""),
    ("소듐하이알루로네이트", "Sodium Hyaluronate", "보습제", ""), ("알란토인", "Allantoin", "피부 컨디셔닝제", ""),
    ("병풀추출물", "Centella Asiatica Extract", "식물 추출물", ""), ("1,2-헥산다이올", "1,2-Hexanediol", "보습제", ""),
    ("페녹시에탄올", "Phenoxyethanol", "보존제", "[대한민국] 배합한도 (데모)"), ("향료", "Fragrance", "", ""),
    ("리모넨", "Limonene", "향료 성분", "[EU] 표시 의무 알레르기 유발 성분 (데모)"), ("리날룰", "Linalool", "향료 성분", "[EU] 표시 의무 알레르기 유발 성분 (데모)"),
    ("레티놀", "Retinol", "비타민 A", "[EU] 제한 - 농도 기준 (데모)"), ("살리실릭애씨드", "Salicylic Acid", "각질 제거 성분", "[대한민국] 배합한도 (데모)"),
    ("글라이콜릭애씨드", "Glycolic Acid", "각질 제거 성분", ""), ("아스코빅애씨드", "Ascorbic Acid", "비타민 C", ""),
    ("하이드로퀴논", "Hydroquinone", "", "[대한민국] 금지 (데모)"), ("스쿠알란", "Squalane", "피부 컨디셔닝제", ""),
    ("토코페롤", "Tocopherol", "비타민 E", ""), ("아데노신", "Adenosine", "주름 개선 기능성 성분", ""),
    ("징크옥사이드", "Zinc Oxide", "자외선 차단 성분", "[대한민국] 배합한도 (데모)"), ("에탄올", "Alcohol", "용제", ""),
]
PRODUCTS = {
    "[예시] 세라마이드 수분 크림": ["정제수", "글리세린", "부틸렌글라이콜", "세라마이드엔피", "판테놀", "소듐하이알루로네이트", "스쿠알란", "1,2-헥산다이올"],
    "[예시] 라벤더 바디 로션": ["정제수", "글리세린", "에탄올", "향료", "리모넨", "리날룰", "페녹시에탄올"],
    "[예시] 레티놀 나이트 세럼": ["정제수", "부틸렌글라이콜", "레티놀", "토코페롤", "아데노신", "페녹시에탄올"],
    "[예시] BHA 클리어 토너": ["정제수", "살리실릭애씨드", "글라이콜릭애씨드", "병풀추출물", "알란토인"],
}
REVIEWS = [  # (피부 정보, 제품, 별점, 보습, 자극, 재구매, 글)
    (["건성 피부", "민감한 편"], "[예시] 세라마이드 수분 크림", 5, True, False, True, "[예시] 바르고 자면 아침까지 당김이 없어요. 향이 없어서 편해요."),
    (["건성 피부", "민감한 편"], "[예시] 세라마이드 수분 크림", 4, True, False, True, "[예시] 조금 무거운 편이라 저녁에만 써요."),
    (["건성 피부", "민감한 편"], "[예시] 세라마이드 수분 크림", 5, True, False, False, "[예시] 겨울철 각질이 덜 올라와요."),
    (["건성 피부", "민감한 편"], "[예시] 세라마이드 수분 크림", 4, True, True, False, "[예시] 컨디션 안 좋은 날엔 살짝 따끔했어요."),
    (["건성 피부", "민감한 편"], "[예시] 세라마이드 수분 크림", 5, True, False, True, "[예시] 무난하고 순해요. 재구매 예정이에요."),
    (["지성 피부"], "[예시] 세라마이드 수분 크림", 3, False, False, False, "[예시] 지성에겐 조금 답답했어요."),
]
POSTS = [
    ("question", "[예시] 레티놀이랑 BHA 같이 쓰시는 분 계세요?", "아침저녁으로 나눠 쓰는 게 나을까요?", "", None, ""),
    ("talk", "[예시] 민감성 피부 겨울 루틴 공유해요", "세안 후 바로 보습, 각질 제거는 주 1회만 하고 있어요.", "", None, "[예시] 세라마이드 수분 크림"),
    ("video", "[예시] 건성 피부 저녁 루틴 영상", "영상에 나온 로션 성분이 궁금해서 공유해요.", "M7lc1UVf-VE", False, "[예시] 라벤더 바디 로션"),
]
CONSENTS = {k: True for k in account.CONSENT_KINDS}


def main() -> None:
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            sys.exit("이미 회원이 있는 DB예요. 데모 데이터는 빈 DB에만 넣어요.")
        db.add_all([Ingredient(name_ko=k, name_en=e, description=d, restriction=r) for k, e, d, r in INGREDIENTS])
        for name, ings in PRODUCTS.items():
            db.add(ProductIngredientList(name=name, name_key=name_key("", name), ingredients=json.dumps(ings, ensure_ascii=False),
                                         list_hash=normalize("|".join(ings))[:64], confirmations=3))
        db.flush()

        def make_user(username: str, name: str, skin: list[str]) -> User:
            u = User(username=username, password_hash=hash_password("ruti1234"), name=name, nickname=account.generate_nickname(db))
            db.add(u)
            db.flush()
            account.record_consents(db, u, CONSENTS)
            for s in skin:
                db.add(Memory(user_id=u.id, content=s))
            return u

        demo = make_user("demo", "체험", ["건성 피부", "향료에 민감해요"])
        for i, (skin, product, rating, moist, irr, rebuy, text) in enumerate(REVIEWS):
            u = make_user(f"sample{i}", f"예시{i}", skin)
            tags = ",".join(t for t in ("건성", "지성") if any(t in s for s in skin)) + (",민감성" if any("민감" in s for s in skin) else "")
            db.add(ScanResult(user_id=u.id, source="image", product_name=product, result=json.dumps({"items": [], "summary": {}})))
            db.add(Review(user_id=u.id, product_name=product, name_key=name_key("", product), rating=rating, text=text,
                          felt_moisture=moist, felt_irritation=irr, would_rebuy=rebuy, verified=True, skin_tags=tags))
        writer = db.scalar(select(User).where(User.username == "sample0"))
        for kind, title, body, vid, sponsored, product in POSTS:
            db.add(Post(user_id=writer.id, kind=kind, title=title, body=body, video_id=vid, sponsored=bool(sponsored),
                        product_name=product, skin_tags="건성,민감성"))
        # 체험 계정의 분석 기록 하나
        names = PRODUCTS["[예시] 라벤더 바디 로션"]
        result = analyze(db, names, ["건성 피부", "향료에 민감해요"])
        db.add(ScanResult(user_id=demo.id, source="text", product_name="[예시] 라벤더 바디 로션", result=json.dumps(result, ensure_ascii=False)))
        db.commit()
    print("데모 데이터를 넣었어요. 체험 계정: demo / ruti1234")


if __name__ == "__main__":
    main()
