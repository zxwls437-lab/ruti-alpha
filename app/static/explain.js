// RUTI 그림 설명: 판정 이유를 피부 단면 애니메이션으로 보여주는 아래쪽 창.
// 그림 7종은 여기 미리 그려져 있고, 문구는 각 사용자의 피부 정보로 채운다 (AI 호출 없음, 비용 0).
// 사용: RUTI.explainer.open([{scenario, ingredient, memo, personal}], {memories, products})
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const CSS = `
.rx-overlay{position:fixed;inset:0;z-index:20;background:rgba(40,32,28,.42);display:flex;align-items:flex-end;justify-content:center}
.rx-sheet{--dermis:#F0C7B6;--dermis-side:#DDAE9B;--epi:#F7DCCB;--epi-side:#E8C6B1;--brick:#FFF6EC;--brick-side:#F1E1D0;--mortar:#E6C9AA;--cell:#EBC3AE;--fiber:#E3B19C;
  --scent:#D69A2E;--alcohol:#8E9BC4;--acid:#A07CC8;--retinol:#E27D3F;--cera:#5E9C7F;--limit:#7C8B96;--water:#5FA3D6;--sun:#F2B33D;--irritate:#E0705F;
  --rx-avoid-bg:#FBE7E3;--rx-avoid-fg:#A44A3F;--rx-check-bg:#FCF1DE;--rx-check-fg:#84601F;
  width:100%;max-width:480px;max-height:94vh;overflow-y:auto;background:var(--card);color:var(--text);border-radius:24px 24px 0 0;
  padding:8px 0 calc(12px + env(safe-area-inset-bottom));box-shadow:0 -8px 30px rgba(40,32,28,.18);word-break:keep-all}
@media (prefers-color-scheme:dark){.rx-sheet{--dermis:#8E5F52;--dermis-side:#764C41;--epi:#A87764;--epi-side:#8F6352;--brick:#D9C3AE;--brick-side:#B9A28D;--mortar:#7A6150;--cell:#9A6B59;--fiber:#A26F5E;
  --scent:#F0B544;--alcohol:#AFBBE0;--acid:#C3A2EA;--retinol:#FF9D5C;--cera:#7FC4A3;--limit:#A8B6C0;--water:#7DBDF0;--sun:#F7C75A;--irritate:#FF8B78;
  --rx-avoid-bg:#3E2622;--rx-avoid-fg:#F0A397;--rx-check-bg:#3A3020;--rx-check-fg:#E8C27A}}
.rx-grip{width:40px;height:5px;border-radius:3px;background:var(--line);margin:0 auto 6px}
.rx-head{display:flex;align-items:center;gap:8px;padding:0 10px 0 20px}
.rx-head h2{flex:1;margin:0;font-size:16px;color:var(--brand)}
.rx-close{width:44px;height:44px;min-height:44px;padding:0;border-radius:22px;background:transparent;color:var(--muted);font-size:22px;line-height:1}
.rx-tabs{display:flex;gap:6px;overflow-x:auto;padding:6px 16px 2px;scrollbar-width:none}.rx-tabs:empty{display:none}
.rx-tab{flex-shrink:0;min-height:36px;padding:0 14px;border-radius:18px;border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:13px;font-weight:500}
.rx-tab[aria-pressed="true"]{background:var(--brand);border-color:var(--brand);color:var(--card);font-weight:700}
.rx-stage{margin:10px 12px 0;border-radius:18px;background:linear-gradient(var(--soft),var(--card))}
.rx-stage svg{display:block;width:100%;height:auto}
.rx-stage text{font-size:11.5px;fill:var(--muted);font-family:inherit}.rx-stage .lbl-strong{fill:var(--text);font-weight:700}
.rx-sheet .f-dermis{fill:var(--dermis)}.rx-sheet .s-dermis{fill:var(--dermis-side)}.rx-sheet .f-epi{fill:var(--epi)}.rx-sheet .s-epi{fill:var(--epi-side)}
.rx-sheet .f-mortar{fill:var(--mortar)}.rx-sheet .brick{fill:var(--brick)}.rx-sheet .brick-side{fill:var(--brick-side)}
.rx-sheet .cell{fill:var(--cell)}.rx-sheet .fiber{fill:none;stroke:var(--fiber);stroke-width:1.6;stroke-linecap:round}
.rx-sheet .cap{fill:none;stroke:var(--irritate);stroke-width:1.4}.rx-sheet .tint{fill:var(--cera)}
.rx-sheet .spark{fill:none;stroke:var(--irritate);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.rx-sheet .drop{fill:var(--water)}
.rx-sheet .p-scent{fill:var(--scent)}.rx-sheet .p-alcohol{fill:var(--alcohol)}.rx-sheet .p-acid{fill:var(--acid)}.rx-sheet .p-retinol{fill:var(--retinol)}.rx-sheet .p-cera{fill:var(--cera)}.rx-sheet .p-limit{fill:var(--limit)}
.rx-sheet .sun{fill:var(--sun)}.rx-sheet .ray{stroke:var(--sun);stroke-width:2;stroke-linecap:round;stroke-dasharray:3 5}
.rx-sheet .g-frame{fill:var(--card);stroke:var(--line)}.rx-sheet .g-fill{fill:var(--limit)}.rx-sheet .g-line{stroke:var(--rx-avoid-fg);stroke-width:2}
.rx-sheet .leader{stroke:var(--muted);stroke-width:1;opacity:.6}
.rx-sheet .bt-avoid{fill:var(--rx-avoid-bg)}.rx-sheet .bt-check{fill:var(--rx-check-bg)}.rx-sheet .bt-good{fill:var(--soft)}
.rx-stage .bf-avoid{fill:var(--rx-avoid-fg);font-weight:700}.rx-stage .bf-check{fill:var(--rx-check-fg);font-weight:700}.rx-stage .bf-good{fill:var(--brand);font-weight:700}
.rx-cap{padding:14px 20px 4px;min-height:176px;display:flex;flex-direction:column;gap:6px}
.rx-step{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.rx-cap h3{margin:0;font-size:19px;line-height:1.4}
.rx-cap p{margin:0;font-size:14.5px;line-height:1.6}
.rx-fade{animation:rxfade .45s ease}@keyframes rxfade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.rx-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}.rx-chips[hidden],.rx-compare[hidden]{display:none}
.rx-chips span{padding:5px 11px;border-radius:14px;font-size:12px;background:var(--bg);border:1px solid var(--line);color:var(--muted)}
.rx-chips span.avoid{background:var(--rx-avoid-bg);border-color:transparent;color:var(--rx-avoid-fg);font-weight:700}
.rx-chips span.check{background:var(--rx-check-bg);border-color:transparent;color:var(--rx-check-fg);font-weight:700}
.rx-chips span.good{background:var(--soft);border-color:transparent;color:var(--brand);font-weight:700}
.rx-compare{display:flex;flex-direction:column;gap:6px;margin-top:6px;font-size:13px}
.rx-compare div{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 12px;border-radius:14px;background:var(--bg);border:1px solid var(--line)}
.rx-compare div.me{border-color:var(--brand)}.rx-compare span{min-width:0}
.rx-compare em{font-style:normal;font-weight:700;font-size:12px;padding:3px 9px;border-radius:12px;flex-shrink:0}
.rx-compare .t-avoid{background:var(--rx-avoid-bg);color:var(--rx-avoid-fg)}.rx-compare .t-check{background:var(--rx-check-bg);color:var(--rx-check-fg)}.rx-compare .t-good{background:var(--soft);color:var(--brand)}
.rx-controls{display:flex;align-items:center;gap:10px;padding:10px 14px 6px}
.rx-btn{min-height:44px;height:44px;border-radius:22px;border:1px solid var(--line);background:var(--card);color:var(--brand);font-weight:700;font-size:14px;padding:0 14px;white-space:nowrap;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.rx-btn.primary{width:44px;padding:0;background:var(--brand);border-color:var(--brand);color:var(--card)}
.rx-dots{display:flex;gap:4px;flex:1;justify-content:center;min-width:0}
.rx-dot{flex:1;max-width:44px;height:44px;min-height:44px;border:0;background:none;padding:0;display:flex;align-items:center;justify-content:center;border-radius:0}
.rx-dot i{display:block;width:100%;height:5px;border-radius:3px;background:var(--line);overflow:hidden;position:relative}
.rx-dot i b{position:absolute;inset:0 auto 0 0;width:0;background:var(--brand);border-radius:3px}
.rx-note{font-size:12px;color:var(--muted);margin:4px 20px 0;line-height:1.6}`;

  // ---------- 글자 도우미 ----------
  const josa = (w, a, b) => { const c = (w || '').charCodeAt(w.length - 1); return c >= 0xAC00 && c <= 0xD7A3 && (c - 0xAC00) % 28 ? a : b; };
  const short = (s, n) => (s || '').length > n ? s.slice(0, n - 1) + '…' : (s || '');
  const BRICKS = ['피부 맨 바깥은 벽돌 담장', '각질층이 벽돌처럼 쌓여서, 바깥 물질이 쉽게 들어오지 못하게 막아 줘요.'];
  const IRRITATE = ['민감한 피부가 낯설게 느끼면', '붉어지거나, 가렵거나, 따가울 수 있어요. 모든 사람에게 생기는 건 아니에요.'];

  // 개인 맞춤 문구: memo가 있으면 '나', 없으면 일반 설명 + 피부 정보 안내
  function personal(c, ing, mid, tip) {
    const m = c.memo;
    if (c.personal && m) return {
      badge: [`내 피부: ${short(m, 11)}`, 'avoid'],
      chips: (c.memories.length ? c.memories : [m]).slice(0, 4).map(x => [x, x === m ? 'avoid' : '']),
      first: ['처음에 알려주신 내 피부', `'${m}'라고 알려주셨어요. RUTI는 이 정보와 성분표를 하나하나 비교해요.`],
      last: ['그래서 나에게는 이렇게 보여드렸어요', `같은 제품도 피부 정보에 따라 결과가 달라져요. ${tip}`],
      compare: [[`'${short(m, 14)}' 나`, 'avoid', '맞지 않을 수 있어요', true], [`${ing}${josa(ing, '이', '가')} 괜찮은 분`, 'good', '잘 맞을 가능성이 높아요']],
      mid,
    };
    return {
      badge: [`성분: ${short(ing, 12)}`, 'check'],
      chips: [[ing, 'check']],
      first: ['이 제품에 들어 있는 성분', `${ing}${josa(ing, '이', '가')} 들어 있어요. 어떤 성분인지 그림으로 볼게요.`],
      last: ['피부 정보에 따라 달라져요', `피부 정보를 알려주시면 나에게 맞는지까지 봐 드릴게요. ${tip}`],
      compare: [[`'${short(ing, 10)}에 민감해요'라고 적은 분`, 'avoid', '맞지 않을 수 있어요'], ['민감하지 않은 분', 'good', '잘 맞을 가능성이 높아요']],
      mid,
    };
  }

  const TEXTS = {
    fragrance: c => personal(c, '향료', [['향료는 아주 작은 알갱이', '민감한 피부는 벽돌 사이 틈이 조금 더 벌어져 있을 수 있어요. 그 틈으로 향료 성분이 들어갈 수 있어요.'], IRRITATE], '무향 제품을 골라 보세요.'),
    generic: c => personal(c, c.ingredient, [[`${short(c.ingredient, 12)}${josa(c.ingredient, '이', '가')} 피부에 닿으면`, '민감한 피부는 벽돌 사이 틈이 조금 더 벌어져 있을 수 있어요. 그 틈으로 성분이 들어갈 수 있어요.'], IRRITATE],
      `성분표에 '${short(c.ingredient, 12)}'${josa(c.ingredient, '이', '가')} 없는 제품을 골라 보세요.`),
    essential_oil: c => personal(c, '에센셜 오일', [['식물에서 뽑은 향기 오일', '라벤더·티트리 같은 에센셜 오일도 향을 내는 성분이에요. 민감한 피부는 벽돌 틈으로 들어온 향 성분에 반응할 수 있어요.'], IRRITATE],
      "성분표에서 식물 이름 + '오일'(씨오일 제외)을 확인해 보세요."),
    paraben: c => personal(c, '파라벤', [['제품이 상하지 않게 지키는 보존제', '파라벤은 식약처 기준 안에서 쓰여 대부분의 피부엔 괜찮아요. 다만 드물게 이 성분에 반응하는 피부가 있어요.'],
      ['반응하는 피부라면', '바른 자리가 붉어지거나 가려울 수 있어요. 모든 사람에게 생기는 건 아니에요.']], "'파라벤 프리' 표시가 있는 제품을 골라 보세요."),
    alcohol: c => personal(c, '알코올', [['알코올은 빨리 날아가는 성분', '피부에 닿은 알코올이 빠르게 날아가면서, 피부 속 수분(파란 방울)도 함께 데려갈 수 있어요.'],
      ['원래 건조한 피부라면', '수분이 더 줄어서 당기고, 각질이 일어날 수 있어요.']], "성분표 앞쪽에 '에탄올'이 없는 제품을 골라 보세요."),
    exfoliant: c => personal(c, '각질 제거 성분', [['AHA·BHA는 묵은 각질을 녹여요', '벽돌 사이를 붙이는 접착제를 느슨하게 해서, 묵은 각질이 빨리 떨어지게 해요.'],
      ['담장이 얇아지면', '민감한 피부는 자극을 더 쉽게 느껴서 따갑거나 붉어질 수 있어요.']], '꼭 써야 한다면 낮은 농도로, 며칠에 한 번부터 시작해 보세요.'),
    retinol: c => personal(c, '레티놀', [['레티놀은 피부가 바뀌는 속도를 높여요', '피부 속까지 들어가서, 아래의 새 세포가 더 빨리 올라오게 도와요.'],
      ['처음엔 따갑고 햇빛에 예민해질 수 있어요', '각질이 일어나거나 붉어질 수 있고, 햇빛 자극도 더 쉽게 느껴요.']], '쓴다면 밤에 조금씩, 낮에는 자외선 차단제를 꼭 발라 주세요.'),
    limit: c => ({
      badge: ['식약처 사용 기준 성분', 'good'],
      chips: [[`${short(c.ingredient, 14)} · 사용 기준 있음`, 'check']],
      first: ['식약처가 정한 사용 기준', `${c.ingredient}${josa(c.ingredient, '은', '는')} '이만큼까지만 넣어요'라는 기준이 법으로 정해진 성분이에요.`],
      mid: [['기준 안에서만 들어가요', '판매되는 화장품은 이 기준을 넘지 않게 만들어야 해요.'],
        ["그래서 이 성분만으로 '맞지 않음'은 아니에요", '기준이 있다는 건 위험하다는 뜻이 아니라, 안전하게 쓰도록 관리된다는 뜻이에요.']],
      last: ['다만 반응한 적이 있다면', '이 성분에 따가웠던 적이 있다면 내 피부 정보에 적어 주세요. 다음부터 바로 알려드려요.'],
      compare: [['피부 정보에 이 성분이 없는 나', 'good', '정보로만 알려드려요', true], [`'${short(c.ingredient, 10)}에 민감해요'라고 적은 분`, 'avoid', '맞지 않을 수 있어요']],
    }),
    ceramide: c => ({
      badge: [`내 피부: ${short(c.memo, 11)}`, 'good'],
      chips: (c.memories.length ? c.memories : [c.memo]).slice(0, 4).map(x => [x, x === c.memo ? 'good' : '']),
      first: ['처음에 알려주신 내 피부', `'${c.memo}'라고 알려주셨어요. 수분을 지키는 데 도움이 되는 성분이 있는지 찾아봤어요.`],
      mid: [['세라마이드가 틈을 채워요', '세라마이드는 원래 벽돌 사이에 있는 성분이에요. 비어 있는 틈을 채워 줘요.'],
        ['수분이 머무르기 쉬워져요', '틈이 촘촘해지면 수분이 덜 날아가서, 촉촉함이 오래가요.']],
      last: ['그래서 나에게는 이렇게 보여드렸어요', '피해야 할 성분도 보이지 않아서 잘 맞을 가능성이 높아요.'],
      compare: [[`'${short(c.memo, 14)}' 나`, 'good', '잘 맞을 가능성이 높아요', true], ['피부 정보를 알려주지 않은 분', 'good', '피해야 할 성분은 보이지 않아요']],
      bricks: ['건조한 피부의 담장', '벽돌 사이 틈이 넓으면 피부 속 수분(파란 방울)이 쉽게 날아가요.'],
    }),
    combo: c => ({
      badge: ['내 화장대: 레티놀 + 각질 제거', 'check'],
      chips: (c.products.length ? c.products : ['레티놀 제품', '각질 제거 제품']).slice(0, 4).map(x => [x, 'check']),
      first: ['내 화장대에 담은 제품', '내 화장대에 담아 두신 제품끼리 함께 써도 괜찮은지 성분을 비교했어요.'],
      mid: [['따로 쓰면 괜찮아도', '각질 제거 성분(보라)은 겉 각질을 녹이고, 레티놀(주황)은 피부 속까지 들어가요.'],
        ['같은 날 쓰면 자극이 겹쳐요', '담장이 얇아진 상태에서 레티놀까지 들어가면, 따가움이나 붉어짐이 더 커질 수 있어요.']],
      last: ['이렇게 나눠 써 보세요', '레티놀은 밤에, 각질 제거 제품은 다른 날 아침처럼 나눠 쓰면 부담을 줄일 수 있어요.'],
      compare: [['같은 날 함께 쓰기', 'check', '자극이 겹칠 수 있어요', true], ['아침·저녁이나 날짜 나눠 쓰기', 'good', '부담이 줄어요']],
    }),
  };
  const LEGEND = {
    fragrance: () => [['p-scent', '향료']], generic: c => [['p-scent', short(c.ingredient, 10)]],
    essential_oil: () => [['p-scent', '에센셜 오일']], paraben: () => [['p-limit', '파라벤(보존제)']],
    alcohol: c => [['p-alcohol', short(c.ingredient, 10)], ['drop', '피부 속 수분']], exfoliant: c => [['p-acid', short(c.ingredient, 10)]],
    retinol: c => [['p-retinol', short(c.ingredient, 10)]], limit: c => [['p-limit', short(c.ingredient, 10)]],
    ceramide: () => [['p-cera', '세라마이드'], ['drop', '피부 속 수분']], combo: () => [['p-retinol', '레티놀류'], ['p-acid', '각질 제거 성분']],
  };
  const TAB = {fragrance: '향료', essential_oil: '에센셜 오일', paraben: '파라벤', generic: null, alcohol: '알코올', exfoliant: '각질 제거', retinol: '레티놀', limit: '사용 기준', ceramide: '세라마이드', combo: '같이 쓰기'};

  // ---------- 그림 엔진 (한 번만 만든다) ----------
  let built = null;
  function build(svg) {
    const S = 26, C = 0.866, SN = 0.5, CX = 135, CY = 140, W = 7, D = 3, Z_DERM = 2.2, Z_EPI = 3.2, Z_TOP = 3.7;
    const P = (x, y, z) => [CX + (x - y) * C * S, CY + (x + y) * SN * S - z * S];
    const pts = a => a.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
    const mk = (tag, attrs, parent = svg) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.append(e); return e; };
    const g = () => mk('g', {});
    const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
    const E = v => { const t = clamp(v); return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };

    const base = g();
    const band = (z0, z1, f, s) => {
      mk('polygon', {class: f, points: pts([P(0, D, z0), P(W, D, z0), P(W, D, z1), P(0, D, z1)])}, base);
      mk('polygon', {class: s, points: pts([P(W, D, z0), P(W, 0, z0), P(W, 0, z1), P(W, D, z1)])}, base);
    };
    band(0, Z_DERM, 'f-dermis', 's-dermis'); band(Z_DERM, Z_EPI, 'f-epi', 's-epi'); band(Z_EPI, Z_TOP, 'f-mortar', 'f-mortar');
    mk('polygon', {class: 'f-mortar', points: pts([P(0, 0, Z_TOP), P(W, 0, Z_TOP), P(W, D, Z_TOP), P(0, D, Z_TOP)])}, base);
    const cellsG = g(), cells = [];
    for (let row = 0; row < 3; row++) for (let i = 0; i < 13; i++) {
      const x = .35 + i * .52 + (row % 2 ? .26 : 0); if (x > W - .2) continue;
      cells.push({x, row, el: mk('ellipse', {class: 'cell', rx: 5.2, ry: 3.6}, cellsG)});
    }
    const wave = (z, amp, k, ph) => { let d = ''; for (let x = .1; x <= W - .1; x += .1) { const [sx, sy] = P(x, D, z + Math.sin(x * k + ph) * amp); d += (d ? 'L' : 'M') + sx.toFixed(1) + ' ' + sy.toFixed(1); } return d; };
    mk('path', {class: 'fiber', d: wave(.6, .12, 2.1, 0)}, base); mk('path', {class: 'fiber', d: wave(1.15, .1, 2.1, 1.7)}, base);
    const cap = mk('path', {class: 'cap', d: wave(1.65, .18, 1.4, 0)});
    const defs = mk('defs', {});
    const rg = mk('radialGradient', {id: 'rxGlow', cx: '50%', cy: '30%', r: '60%'}, defs);
    mk('stop', {offset: '0%', style: 'stop-color:var(--irritate);stop-opacity:.85'}, rg);
    mk('stop', {offset: '100%', style: 'stop-color:var(--irritate);stop-opacity:0'}, rg);
    const glow = mk('polygon', {fill: 'url(#rxGlow)', points: pts([P(0, D, 0), P(W, D, 0), P(W, D, Z_EPI), P(0, D, Z_EPI)])});
    const tintG = g();
    mk('polygon', {class: 'tint', points: pts([P(0, 0, Z_TOP), P(W, 0, Z_TOP), P(W, D, Z_TOP), P(0, D, Z_TOP)])}, tintG);
    mk('polygon', {class: 'tint', points: pts([P(0, D, Z_EPI), P(W, D, Z_EPI), P(W, D, Z_TOP), P(0, D, Z_TOP)])}, tintG);

    const bricksG = g(), topBricks = [], frontBricks = [], sideBricks = [];
    for (let j = 0; j < D; j++) for (let i = 0; i < W; i++) topBricks.push({i, j, el: mk('polygon', {class: 'brick'}, bricksG)});
    for (let i = 0; i < W; i++) frontBricks.push({i, el: mk('polygon', {class: 'brick'}, bricksG)});
    for (let j = 0; j < D; j++) sideBricks.push({j, el: mk('polygon', {class: 'brick-side'}, bricksG)});

    const labels = g();
    [[(Z_EPI + Z_TOP) / 2, '각질층', true], [(Z_DERM + Z_EPI) / 2, '표피'], [Z_DERM / 2, '진피']].forEach(([z, text, strong]) => {
      const [sx, sy] = P(W, 0, z);
      mk('line', {class: 'leader', x1: sx + 3, y1: sy, x2: sx + 12, y2: sy}, labels);
      mk('text', {x: sx + 15, y: sy + 4, class: strong ? 'lbl-strong' : ''}, labels).textContent = text;
    });

    const gauge = g(), GX = 20, GY = 256, GW = 130, GH = 10, LIM = .78;
    mk('text', {x: GX, y: GY - 8, class: 'lbl-strong'}, gauge).textContent = '제품 속 양';
    mk('rect', {class: 'g-frame', x: GX, y: GY, width: GW, height: GH, rx: 5}, gauge);
    const gFill = mk('rect', {class: 'g-fill', x: GX, y: GY, width: 0, height: GH, rx: 5}, gauge);
    mk('line', {class: 'g-line', x1: GX + GW * LIM, y1: GY - 4, x2: GX + GW * LIM, y2: GY + GH + 4}, gauge);
    mk('text', {x: GX + GW * LIM - 30, y: GY + GH + 17}, gauge).textContent = '식약처 기준';

    const sunG = g(), SUNX = 34, SUNY = 96;
    [[60, 108], [70, 124], [52, 128]].forEach(([x2, y2]) => mk('line', {class: 'ray', x1: SUNX + 8, y1: SUNY + 6, x2, y2}, sunG));
    for (let a = 0; a < 8; a++) { const r = a * Math.PI / 4; mk('line', {class: 'ray', 'stroke-dasharray': 'none', x1: SUNX + Math.cos(r) * 13, y1: SUNY + Math.sin(r) * 13, x2: SUNX + Math.cos(r) * 17, y2: SUNY + Math.sin(r) * 17}, sunG); }
    mk('circle', {class: 'sun', cx: SUNX, cy: SUNY, r: 9}, sunG);

    const dropsG = g(), partsG = g(), sparksG = g();
    const drops = Array.from({length: 10}, () => mk('ellipse', {class: 'drop', rx: 3.4, ry: 4.4, opacity: 0}, dropsG));
    const parts = Array.from({length: 26}, () => ({halo: mk('circle', {r: 6.5, opacity: 0}, partsG), dot: mk('circle', {r: 3.4, opacity: 0}, partsG)}));
    const sparks = Array.from({length: 8}, () => mk('polyline', {class: 'spark', opacity: 0}, sparksG));

    const legend = g();
    const legendItems = [0, 1].map(k => ({
      halo: mk('circle', {cx: 26, cy: 24 + k * 20, r: 7, opacity: .35}, legend),
      dot: mk('circle', {cx: 26, cy: 24 + k * 20, r: 3.6}, legend),
      text: mk('text', {x: 38, y: 28 + k * 20, class: 'lbl-strong'}, legend),
    }));
    const badge = g();
    const badgeBg = mk('rect', {y: 10, height: 28, rx: 14}, badge), badgeI1 = mk('circle', {cy: 21, r: 3.6}, badge), badgeI2 = mk('path', {}, badge), badgeT = mk('text', {y: 28}, badge);

    let st, pi, di, si;
    const reset = () => {
      st = {gap: .1, shed: null, frontTop: Z_TOP - .02, cellShift: 0}; pi = di = si = 0;
      glow.setAttribute('opacity', 0); cap.setAttribute('opacity', .2); tintG.setAttribute('opacity', 0);
      gauge.setAttribute('opacity', 0); sunG.setAttribute('opacity', 0);
    };
    const put = (cls, x, y, z, op) => {
      const p = parts[pi++]; if (!p) return; const [sx, sy] = P(x, y, z);
      p.dot.setAttribute('class', cls); p.halo.setAttribute('class', cls);
      p.dot.setAttribute('cx', sx); p.dot.setAttribute('cy', sy); p.halo.setAttribute('cx', sx); p.halo.setAttribute('cy', sy);
      p.dot.setAttribute('opacity', op); p.halo.setAttribute('opacity', op * .3);
    };
    const drop = (x, z, op) => { const d = drops[di++]; if (!d) return; const [sx, sy] = P(x, D, z); d.setAttribute('cx', sx); d.setAttribute('cy', sy); d.setAttribute('opacity', op); };
    const fallZ = k => 5.8 - (5.8 - (Z_TOP + .12)) * E(k);
    const irritate = (level, t, spots) => {
      glow.setAttribute('opacity', (level * (.78 + .22 * Math.sin(t * 4)) * .8).toFixed(3));
      cap.setAttribute('opacity', (.2 + .65 * level).toFixed(2));
      spots.forEach(([x, z], k) => [-1, 1].forEach(s => {
        const el = sparks[si++]; if (!el) return; const [sx, sy] = P(x, D, z);
        el.setAttribute('points', `${sx + s * 7},${sy - 6} ${sx + s * 11},${sy - 2} ${sx + s * 9},${sy + 1} ${sx + s * 14},${sy + 5}`);
        el.setAttribute('opacity', (level * clamp(.5 + .5 * Math.sin(t * 9 + k * 1.7 + s))).toFixed(2));
      }));
    };
    const seeded = (n, s) => { let seed = s; const r = () => (seed = (seed * 9301 + 49297) % 233280) / 233280; return Array.from({length: n}, () => ({x: .5 + r() * 6, y: .3 + r() * 2.4, d: r() * 1.4})); };
    const surfaceFall = (list, cls, t, start, fadeAt) => list.forEach(p => {
      const lt = t - start - p.d; if (lt <= 0) return;
      put(cls, p.x, p.y, fallZ(lt / 1.1), clamp(lt / .3) * (fadeAt == null ? 1 : 1 - .7 * clamp((t - fadeAt) / 1)));
    });
    const enterGap = (xs, cls, t, start, endZ) => xs.forEach((x, k) => {
      const lt = t - start - k * .45; if (lt <= 0) return;
      put(cls, x, D, lt < 1.25 ? fallZ(lt) : (Z_TOP + .1) - (Z_TOP + .1 - endZ[k]) * E((lt - 1.25) / 1.6), clamp(lt / .3));
    });
    const WATER = [[.9, 2.6], [1.8, 1.4], [2.6, 2.75], [3.4, 1.0], [4.2, 2.5], [5.1, 1.7], [5.8, 2.8], [6.4, 1.2]];
    const SURF = seeded(14, 7), SURF2 = seeded(10, 31), SURF3 = seeded(8, 53);
    const shedFn = (t, start, pick, dzMax, opDrop) => (i, j) => (pick(i, j) ? (() => { const k = E((t - start - i * .12) / 1.4); return {dz: dzMax * k, op: 1 - opDrop * k}; })() : null);
    const fade = t => 1 - .45 * clamp((t - 10.5) / 1);

    const SCENES = {
      fragrance(t, cls = 'p-scent') {
        st.gap = .1 + .16 * E((t - 3.2) / 1);
        surfaceFall(SURF, cls, t, 3, 6.5);
        enterGap([2, 4, 5], cls, t, 3.3, [1.55, 1.43, 1.31]);
        irritate(E((t - 7) / 1.2) * fade(t), t, [[2, 1.55], [4, 1.43], [5, 1.31]]);
      },
      generic(t) { SCENES.fragrance(t, 'p-scent'); },
      essential_oil(t) { SCENES.fragrance(t, 'p-scent'); },
      paraben(t) { SCENES.fragrance(t, 'p-limit'); },
      alcohol(t) {
        WATER.forEach(([x, z0], i) => {
          let z = z0 + .05 * Math.sin(t * 2 + i), xx = x, op = clamp((t + .5) / .5);
          const k = [1, 3, 5, 6].indexOf(i);
          if (k >= 0 && t > 4.8) { const e = E((t - 4.8 - k * .3) / 1.8), gx = Math.round(x) || 1; xx = x + (gx - x) * clamp(e * 2); z = z0 + (Z_TOP + 1.4 - z0) * e; op *= 1 - clamp((e - .6) / .4); }
          drop(xx, z, op);
        });
        SURF2.forEach(p => {
          const lt = t - 3 - p.d * .8; if (lt <= 0) return; const rise = E((lt - 1.5) / 1.6);
          put('p-alcohol', p.x, p.y, lt < 1.5 ? fallZ(lt / 1.1) : Z_TOP + .12 + 1.6 * rise, clamp(lt / .3) * (1 - rise));
        });
        st.gap = .1 + .12 * E((t - 7) / 1);
        st.shed = (i, j) => ((i + j) % 3 === 0 ? {dz: .14 * E((t - 7.3) / 1), op: 1} : null);
      },
      exfoliant(t) {
        surfaceFall(SURF, 'p-acid', t, 3, 4.9);
        st.shed = shedFn(t, 4.8, (i, j) => (i * 3 + j) % 2 === 0, .7, 1);
        st.frontTop = Z_TOP - .02 - .2 * E((t - 4.8) / 1.5);
        irritate(E((t - 7) / 1.2) * fade(t), t, [[1.5, 2.6], [3.5, 2.7], [5.5, 2.6]]);
      },
      retinol(t) {
        st.cellShift = t < 3 ? t * .1 : .3 + (t - 3) * .32;
        surfaceFall(SURF3, 'p-retinol', t, 3, 6);
        enterGap([1, 3, 4, 6], 'p-retinol', t, 3.2, [1.2, 1.0, 1.3, 1.1]);
        st.shed = shedFn(t, 5.5, (i, j) => (i + 2 * j) % 3 === 1, .5, .9);
        sunG.setAttribute('opacity', E((t - 7) / .8));
        irritate(E((t - 7.6) / 1.2) * fade(t), t, [[1.5, 2.9], [4, 2.8], [6, 2.9]]);
      },
      combo(t) {
        surfaceFall(SURF2, 'p-acid', t, 3, 5);
        st.shed = shedFn(t, 4.6, (i, j) => (i * 3 + j) % 2 === 0, .6, 1);
        st.frontTop = Z_TOP - .02 - .18 * E((t - 4.6) / 1.5);
        enterGap([2, 3, 5], 'p-retinol', t, 4.2, [1.25, 1.1, 1.35]);
        irritate(E((t - 7) / 1) * (1 - .4 * clamp((t - 10.5) / 1)), t, [[2, 1.25], [3, 1.1], [5, 1.35], [4.2, 2.7]]);
      },
      limit(t) {
        surfaceFall(SURF3.slice(0, 6), 'p-limit', t, 3, null);
        gauge.setAttribute('opacity', E((t - 3) / .6));
        gFill.setAttribute('width', (GW * .46 * E((t - 3.6) / 1.5)).toFixed(1));
      },
      ceramide(t) {
        st.gap = t < 3 ? .26 : .26 - .18 * E((t - 4.6) / 2);
        tintG.setAttribute('opacity', (.3 * E((t - 4.6) / 2)).toFixed(2));
        WATER.forEach(([x, z0], i) => {
          let z = z0 + .05 * Math.sin(t * 2 + i), xx = x, op = clamp((t + .5) / .5);
          if ((i === 2 || i === 4) && t < 7) { const e = E((t - .6 - (i === 4 ? .5 : 0)) / 2.2), gx = Math.round(x); xx = x + (gx - x) * clamp(e * 2); z = z0 + (Z_TOP + 1.3 - z0) * e; op *= 1 - clamp((e - .6) / .4); }
          else if (i === 2 || i === 4) op *= E((t - 7) / .8);
          drop(xx, z, op);
        });
        surfaceFall(SURF2, 'p-cera', t, 3, 5.6);
        [1, 2, 3, 4, 5, 6].forEach((x, k) => { const lt = t - 3.4 - k * .25; if (lt <= 0) return; put('p-cera', x, D, lt < 1.2 ? fallZ(lt) : (Z_TOP + .1) - .45 * E((lt - 1.2) / 1), clamp(lt / .3)); });
      },
    };

    function drawBricks(t) {
      const appear = n => E((t - n * .045) / .5), h = st.gap / 2;
      topBricks.forEach((b, n) => {
        const off = b.j % 2 ? .5 : 0; let x0 = b.i + off + h, x1 = b.i + 1 + off - h; if (x1 > W) x1 = W - h;
        if (x0 >= x1) { b.el.setAttribute('opacity', 0); return; }
        const sh = st.shed && st.shed(b.i, b.j), z = Z_TOP + (sh ? sh.dz : 0);
        b.el.setAttribute('points', pts([P(x0, b.j + h, z), P(x1, b.j + h, z), P(x1, b.j + 1 - h, z), P(x0, b.j + 1 - h, z)]));
        b.el.setAttribute('opacity', (appear(n) * (sh ? sh.op : 1)).toFixed(3));
      });
      frontBricks.forEach((b, n) => {
        b.el.setAttribute('points', pts([P(b.i + h, D, Z_EPI + .06), P(b.i + 1 - h, D, Z_EPI + .06), P(b.i + 1 - h, D, st.frontTop), P(b.i + h, D, st.frontTop)]));
        b.el.setAttribute('opacity', appear(n));
      });
      sideBricks.forEach((b, n) => {
        const y0 = b.j + h, y1 = b.j + 1 - h;
        b.el.setAttribute('points', pts([P(W, y1, Z_EPI + .06), P(W, y0, Z_EPI + .06), P(W, y0, st.frontTop), P(W, y1, st.frontTop)]));
        b.el.setAttribute('opacity', appear(n + 7));
      });
    }
    function drawCells(t) {
      const shift = st.cellShift || t * .08;
      cells.forEach(c => {
        const f = ((c.row * .3 + shift) % .9 + .9) % .9, [sx, sy] = P(c.x, D, Z_DERM + .08 + f);
        c.el.setAttribute('cx', sx.toFixed(1)); c.el.setAttribute('cy', sy.toFixed(1));
        c.el.setAttribute('opacity', (.7 * Math.min(1, f / .12, (.9 - f) / .12)).toFixed(2));
      });
    }
    return {
      setup(scenario, badgeSpec, legendSpec) {
        const [text, tone] = badgeSpec, w = 40 + [...text].reduce((a, ch) => a + (/[가-힣]/.test(ch) ? 11.6 : 6.4), 0), x = Math.max(120, 352 - w);
        badgeBg.setAttribute('class', 'bt-' + tone); badgeBg.setAttribute('x', x.toFixed(1)); badgeBg.setAttribute('width', (352 - x).toFixed(1));
        for (const e of [badgeI1, badgeI2, badgeT]) e.setAttribute('class', 'bf-' + tone);
        badgeI1.setAttribute('cx', (x + 16).toFixed(1));
        badgeI2.setAttribute('d', `M${(x + 9.5).toFixed(1)} 31.5c.9-3.6 3.4-5.4 6.5-5.4s5.6 1.8 6.5 5.4z`);
        badgeT.setAttribute('x', (x + 28).toFixed(1)); badgeT.textContent = text;
        legendItems.forEach((it, k) => {
          const l = legendSpec[k];
          [it.halo, it.dot, it.text].forEach(e => { e.style.display = l ? '' : 'none'; });
          if (l) { it.halo.setAttribute('class', l[0]); it.dot.setAttribute('class', l[0]); it.text.textContent = l[1]; }
        });
        this.scene = SCENES[scenario] || SCENES.generic;
      },
      render(T, OFF) {
        reset();
        const t = T - OFF;
        this.scene(t);
        for (; pi < parts.length; pi++) { parts[pi].dot.setAttribute('opacity', 0); parts[pi].halo.setAttribute('opacity', 0); }
        for (; di < drops.length; di++) drops[di].setAttribute('opacity', 0);
        for (; si < sparks.length; si++) sparks[si].setAttribute('opacity', 0);
        drawBricks(t); drawCells(t);
        labels.setAttribute('opacity', (clamp((t - .6) / .6) * (t > 3 ? .55 + .45 * (1 - clamp((t - 3) / .5)) : 1)).toFixed(2));
        legend.setAttribute('opacity', E((t - 2.6) / .5));
        badge.setAttribute('opacity', E((T - .3) / .6));
      },
    };
  }

  // ---------- 아래쪽 창 ----------
  const OFF = 3.5, STEP_TIMES = [0, OFF, OFF + 3, OFF + 7, OFF + 10.5], END = OFF + 14;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let ui = null, list = [], ctxBase = {}, cur = null, t = 0, playing = false, last = 0, raf = 0, shown = -1, opener = null;

  function h(tag, props = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) { if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); }
    for (const c of kids.flat()) if (c != null) e.append(c);
    return e;
  }
  function makeUI() {
    if (!document.getElementById('rx-style')) document.head.append(h('style', {id: 'rx-style'}, CSS));
    const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 360 290'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-labelledby', 'rxTitle rxText');
    const u = {};
    u.tabs = h('div', {class: 'rx-tabs', role: 'group', 'aria-label': '이유 고르기'});
    u.step = h('div', {class: 'rx-step'}); u.title = h('h3', {id: 'rxTitle'}); u.text = h('p', {id: 'rxText'});
    u.chips = h('div', {class: 'rx-chips'}); u.compare = h('div', {class: 'rx-compare'});
    u.cap = h('div', {class: 'rx-cap', 'aria-live': 'polite'}, u.step, u.title, u.text, u.chips, u.compare);
    u.play = h('button', {class: 'rx-btn primary', type: 'button', onclick: () => { if (t >= END) t = 0; playing = !playing; last = performance.now(); sync(); }});
    u.dots = STEP_TIMES.map((at, i) => {
      const fill = h('b');
      const b = h('button', {class: 'rx-dot', type: 'button', 'aria-label': `${i + 1}단계`, onclick: () => {
        if (reduce) { t = (i + 1 < STEP_TIMES.length ? STEP_TIMES[i + 1] : END) - .05; playing = false; } else { t = at + .001; playing = true; }
        last = performance.now(); sync(true);
      }}, h('i', {}, fill));
      return {b, fill};
    });
    const replay = h('button', {class: 'rx-btn', type: 'button', onclick: () => { t = reduce ? STEP_TIMES[3] - .05 : 0; playing = !reduce; last = performance.now(); sync(true); }}, '다시 보기');
    u.close = h('button', {class: 'rx-close', type: 'button', 'aria-label': '닫기', onclick: close}, '×');
    u.sheet = h('div', {class: 'rx-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': '왜 그런지 그림으로 보기'},
      h('div', {class: 'rx-grip'}),
      h('div', {class: 'rx-head'}, h('h2', {}, '왜 그런지 그림으로 볼까요?'), u.close),
      u.tabs, h('div', {class: 'rx-stage'}, svg), u.cap,
      h('div', {class: 'rx-controls'}, u.play, h('div', {class: 'rx-dots'}, u.dots.map(d => d.b)), replay),
      h('p', {class: 'rx-note'}, '모든 사람에게 생기는 반응은 아니에요. RUTI는 의료 진단을 대신하지 않아요. 붉어짐이나 가려움이 계속되면 피부과 전문의와 상담해 주세요.'));
    u.overlay = h('div', {class: 'rx-overlay', onclick: e => { if (e.target === u.overlay) close(); }}, u.sheet);
    u.overlay.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
    built = built || build(svg);
    return u;
  }

  function select(i) {
    const item = list[i];
    const c = {...ctxBase, ...item, memories: ctxBase.memories || [], products: ctxBase.products || []};
    const tx = (TEXTS[item.scenario] || TEXTS.generic)(c);
    cur = {
      steps: [tx.first, tx.bricks || BRICKS, ...tx.mid, tx.last],
      chips: tx.chips, compare: tx.compare,
    };
    built.setup(item.scenario, tx.badge, (LEGEND[item.scenario] || LEGEND.generic)(c));
    ui.chips.replaceChildren(...cur.chips.map(([x, cls]) => h('span', cls ? {class: cls} : {}, x)));
    ui.compare.replaceChildren(...cur.compare.map(([label, tone, txt, me]) => h('div', me ? {class: 'me'} : {}, h('span', {}, label), h('em', {class: 't-' + tone}, txt))));
    [...ui.tabs.children].forEach((b, k) => b.setAttribute('aria-pressed', String(k === i)));
    shown = -1; t = reduce ? STEP_TIMES[3] - .05 : 0; playing = !reduce; last = performance.now(); sync(true);
  }
  function sync(force) {
    const idx = STEP_TIMES.reduce((a, at, i) => t >= at ? i : a, 0);
    STEP_TIMES.forEach((at, i) => {
      const end = i + 1 < STEP_TIMES.length ? STEP_TIMES[i + 1] : END;
      ui.dots[i].fill.style.width = (clamp((t - at) / (end - at)) * 100) + '%';
      ui.dots[i].b.setAttribute('aria-current', i === idx ? 'step' : 'false');
    });
    if (idx !== shown || force) {
      shown = idx; const [title, text] = cur.steps[idx];
      ui.step.textContent = `${idx + 1} / ${STEP_TIMES.length}`; ui.title.textContent = title; ui.text.textContent = text;
      ui.chips.hidden = idx !== 0; ui.compare.hidden = idx !== STEP_TIMES.length - 1;
      ui.cap.classList.remove('rx-fade'); void ui.cap.offsetWidth; ui.cap.classList.add('rx-fade');
    }
    built.render(t, OFF);
    ui.play.setAttribute('aria-label', playing ? '일시정지' : '재생');
    ui.play.innerHTML = playing
      ? '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5l11 7-11 7z" fill="currentColor"/></svg>';
  }
  function frame(now) {
    if (playing) { t += (now - last) / 1000; if (t >= END) { t = END; playing = false; } }
    last = now; sync(); raf = requestAnimationFrame(frame);
  }
  function close() {
    cancelAnimationFrame(raf); raf = 0;
    if (ui && ui.overlay.isConnected) ui.overlay.remove();
    document.body.style.overflow = '';
    if (opener && opener.focus) opener.focus();
  }
  function open(items, ctx = {}) {
    list = (items || []).filter(x => x && x.scenario);
    if (!list.length) return;
    ctxBase = ctx; opener = document.activeElement;
    if (!ui) ui = makeUI();
    ui.tabs.replaceChildren(...(list.length > 1 ? list.map((it, k) => h('button', {class: 'rx-tab', type: 'button', onclick: () => select(k)},
      TAB[it.scenario] || short(it.ingredient, 8))) : []));
    document.body.append(ui.overlay); document.body.style.overflow = 'hidden';
    select(ctx.start || 0);
    ui.close.focus();
    cancelAnimationFrame(raf); raf = requestAnimationFrame(frame);
  }
  const label = it => it.scenario === 'combo' ? '같이 쓰기' : (it.scenario === 'limit' ? `${short(it.ingredient, 10)} (사용 기준)` : short(it.ingredient, 10));
  // common.js의 RUTI(전역 const)에 붙인다. common.js 없이 쓰면 window.RUTI에 붙인다.
  const root = typeof RUTI !== 'undefined' ? RUTI : (window.RUTI = window.RUTI || {});
  root.explainer = {open, close, label};
})();
