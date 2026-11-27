

def test_recommend_only_one_and_skip_conflicts():
    from app import ai
    prods = [{"id": 1, "name": "향 크림", "brand": "", "category": "크림", "skin_types": [], "key_ingredients": "향료, 글리세린", "description": ""},
             {"id": 2, "name": "순한 크림", "brand": "", "category": "크림", "skin_types": [], "key_ingredients": "세라마이드, 글리세린", "description": ""}]
    assert ai.conflicts_with_memories(prods[0], ["향료에 민감해요"]) is True
    assert ai.conflicts_with_memories(prods[1], ["향료에 민감해요"]) is False
    assert ai.conflicts_with_memories(prods[0], []) is False


def test_audience_mismatch():
    from app import ai
    mat = {"name": "부담제로매터니티크림", "category": "기능성화장품"}
    baby = {"name": "순한 베이비 로션", "category": ""}
    men = {"name": "옴므 올인원", "category": ""}
    plain = {"name": "데일리 수분 크림", "category": ""}
    assert ai.audience_mismatch(mat, ["건성 피부"], "크림 추천해 줘") is True
    assert ai.audience_mismatch(mat, ["임신·수유 중이에요"], "크림 추천해 줘") is False
    assert ai.audience_mismatch(baby, [], "크림 추천") is True and ai.audience_mismatch(baby, [], "아기한테 쓸 로션") is False
    assert ai.audience_mismatch(men, [], "추천") is True and ai.audience_mismatch(men, [], "남편 선물로 추천") is False
    assert ai.audience_mismatch(plain, [], "추천") is False


def test_mentioned_products():
    from app import ai
    prods = [{"id": 1, "name": "나이아신화이트닝 로션(건성/모든피부용)"}, {"id": 2, "name": "오아닉오트밀딥모이스쳐크림"}, {"id": 3, "name": "기타 크림"}]
    text = "아침용 '나이아신화이트닝 로션'과 저녁용 오아닉 오트밀딥모이스쳐크림을 추천해요"
    assert ai.mentioned_products(text, prods) == [1, 2]
    assert ai.mentioned_products("나이아신화이트닝로션을 추천해요", prods) == [1]


def test_with_name():
    from app import ai
    assert ai.with_name("여드름 때문에 힘드셨죠.", "태현") == "태현님, 여드름 때문에 힘드셨죠."
    assert ai.with_name("태현님, 안녕하세요.", "태현") == "태현님, 안녕하세요."
    assert ai.with_name("안녕하세요.", "") == "안녕하세요."
