

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
