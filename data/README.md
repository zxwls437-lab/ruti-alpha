# 제품 데이터

`products_template.json`은 **형식 예시**이고 실제 제품이 아닙니다.

| 필드 | 필수 | 설명 |
|---|---|---|
| name | ✅ | 제품명 |
| brand | | 브랜드 |
| category | | 크림, 토너, 세럼, 선크림, 클렌저 등 |
| skin_types | | 권장 피부 타입 배열: 건성, 지성, 복합성, 민감성, 중성 |
| key_ingredients | | 주요 성분 (쉼표 구분) |
| description | | 제품 설명 (AI가 참고) |
| cautions | | 주의사항 |
| source_url | 승인 시 필수 | 공식 제품 페이지·전성분표 등 근거 자료 |

## 흐름
1. 실제 제품 정보로 JSON 파일을 만든다 (공식 페이지에서 직접 확인한 정보만).
2. `python -m scripts.import_products 파일.json` → 모두 **검토 대기**로 들어감
3. `/admin` 에서 근거 자료를 확인하고 승인 → 그때부터 검색·AI 상담에 사용

AI는 승인된 제품만 추천할 수 있고, 응답에 들어간 제품 ID도 서버가 승인 목록과 대조해 검증합니다.
