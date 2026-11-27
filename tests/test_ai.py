

def test_recommend_only_one_and_skip_conflicts():
    from app import ai
    prods = [{"id": 1, "name": "향 크림", "brand": "", "category": "크림", "skin_types": [], "key_ingredients": "향료, 글리세린", "description": ""},
             {"id": 2, "name": "순한 크림", "brand": "", "category": "크림", "skin_types": [], "key_ingredients": "세라마이드, 글리세린", "description": ""}]
    assert ai.conflicts_with_memories(prods[0], ["향료에 민감해요"]) is True
    assert ai.conflicts_with_memories(prods[1], ["향료에 민감해요"]) is False
    assert ai.conflicts_with_memories(prods[0], []) is False
