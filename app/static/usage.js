// RUTI 사용법 애니메이션: 화장품 종류(클렌저·토너·세럼·크림·선크림·아이크림·마스크팩·각질 제거·레티놀·미스트)마다
// 얼굴 그림 위에서 바르는 순서를 보여준다. 제품 이름으로 종류를 알아내서 DB의 모든 화장품에 자동으로 붙는다 (AI 비용 0).
// 사용: RUTI.usage.open({name, brand, usage, category})
(() => {
  const CSS = `
.us-sheet{--skin:#F6DCCB;--skin-d:#E9C2AB;--hair:#5B4639;--line:#B98C76;--cream:#FFFFFF;--foam:#F4F9FF;--water:#5FA3D6;--warn:#E0705F;--sun:#F2B33D;
  width:100%;max-width:480px;max-height:94vh;overflow-y:auto;background:var(--card);color:var(--text);border-radius:24px 24px 0 0;padding:8px 0 calc(12px + env(safe-area-inset-bottom))}
@media (prefers-color-scheme:dark){.us-sheet{--skin:#C99A82;--skin-d:#B4856E;--hair:#2E2420;--line:#8E6655;--cream:#F4ECE4;--foam:#E3ECF5}}
.us-head{display:flex;align-items:center;gap:8px;padding:0 10px 0 20px}.us-head h2{flex:1;margin:0;font-size:16px;color:var(--brand)}
.us-x{width:44px;height:44px;min-height:44px;padding:0;background:transparent;color:var(--muted);font-size:22px}
.us-prod{padding:0 20px;margin:2px 0 0;font-size:13px;color:var(--muted)}
.us-stage{margin:10px 12px 0;border-radius:18px;background:linear-gradient(var(--soft),var(--card));display:flex;justify-content:center}
.us-stage svg{width:100%;max-width:340px;height:auto;display:block}
.us-el{opacity:0;transition:opacity .35s}.us-el.on{opacity:1}
.on .us-drop{animation:usDrop 1.2s ease-in infinite}.on .us-bub{animation:usBub 1.6s ease-in-out infinite}
.on .us-circle{animation:usCircle 2.4s linear infinite;transform-box:view-box;transform-origin:var(--ox) var(--oy)}
.on .us-sweep{animation:usSweep 1.8s ease-in-out infinite}.on .us-pop{animation:usPop .5s ease-out both}
.on .us-tap{animation:usTap .7s ease-in-out infinite}.on .us-pulse{animation:usPulse 1.4s ease-in-out infinite}
.on .us-spray{animation:usSpray 1.4s ease-out infinite}.on .us-tick{animation:usTick 4s linear infinite;transform-box:fill-box;transform-origin:50% 100%}
@keyframes usDrop{0%{transform:translateY(-30px);opacity:0}25%{opacity:1}100%{transform:translateY(20px);opacity:0}}
@keyframes usBub{0%,100%{transform:scale(.85)}50%{transform:scale(1.1)}}
@keyframes usCircle{to{transform:rotate(360deg)}}
@keyframes usSweep{0%{stroke-dashoffset:60;opacity:0}20%{opacity:1}100%{stroke-dashoffset:0;opacity:0}}
@keyframes usPop{from{transform:scale(0);opacity:0}to{transform:scale(1);opacity:1}}
@keyframes usTap{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes usPulse{0%,100%{opacity:.35}50%{opacity:.9}}
@keyframes usSpray{0%{transform:translate(0,0);opacity:0}20%{opacity:1}100%{transform:translate(var(--sx,-60px),var(--sy,10px));opacity:0}}
@keyframes usTick{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.us-stage *{animation:none!important}}
.us-cap{padding:12px 20px 4px;min-height:110px}
.us-step{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.us-cap h3{margin:2px 0 4px;font-size:19px;line-height:1.4}.us-cap p{margin:0;font-size:14.5px;line-height:1.6;color:var(--muted)}
.us-ctrl{display:flex;align-items:center;gap:10px;padding:8px 14px}
.us-btn{min-height:44px;height:44px;border-radius:22px;border:1px solid var(--line);background:var(--card);color:var(--brand);font-weight:700;padding:0 16px;flex-shrink:0}
.us-dots{display:flex;gap:4px;flex:1;justify-content:center}
.us-dot{flex:1;max-width:44px;height:44px;min-height:44px;border:0;background:none;padding:0;display:flex;align-items:center}
.us-dot i{display:block;width:100%;height:5px;border-radius:3px;background:var(--line)}.us-dot[aria-current="step"] i{background:var(--brand)}
.us-label{margin:8px 20px 0;padding:12px 14px;border-radius:14px;background:var(--bg);font-size:14px;line-height:1.6}
.us-label b{display:block;font-size:12px;color:var(--muted);margin-bottom:2px}
.us-note{font-size:12px;color:var(--muted);margin:8px 20px 0;line-height:1.6}`;

  // 얼굴 기준점 (viewBox 0 0 320 280)
  const F = {forehead: [160, 70], lc: [112, 150], rc: [208, 150], nose: [160, 140], chin: [160, 212], le: [133, 118], re: [187, 118], mouth: [160, 182]};
  const dot = (x, y, r = 7, cls = 'us-pop', delay = 0) => `<circle cx="${x}" cy="${y}" r="${r}" fill="var(--cream)" stroke="var(--line)" stroke-width="1.2" class="${cls}" style="animation-delay:${delay}s;transform-box:fill-box;transform-origin:center"/>`;
  const sweep = (d, delay = 0) => `<path d="${d}" fill="none" stroke="var(--brand)" stroke-width="3" stroke-linecap="round" stroke-dasharray="60" class="us-sweep" style="animation-delay:${delay}s" marker-end="url(#usArrow)"/>`;
  const finger = (x, y, cls = 'us-tap', delay = 0) => `<g class="${cls}" style="animation-delay:${delay}s"><ellipse cx="${x}" cy="${y + 14}" rx="9" ry="16" fill="var(--skin-d)" stroke="var(--line)" stroke-width="1.2"/><ellipse cx="${x}" cy="${y + 4}" rx="5" ry="4" fill="#fff" opacity=".55"/></g>`;
  const label = (x, y, t) => `<text x="${x}" y="${y}" text-anchor="middle" font-size="13" font-weight="700" fill="var(--text)">${t}</text>`;
  const el = (steps, inner) => `<g class="us-el" data-s="${steps}">${inner}</g>`;
  const face = (ears = false) => `
    <defs><marker id="usArrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--brand)"/></marker></defs>
    ${ears ? '<ellipse cx="78" cy="140" rx="10" ry="18" fill="var(--skin)" stroke="var(--line)"/><ellipse cx="242" cy="140" rx="10" ry="18" fill="var(--skin)" stroke="var(--line)"/>' : ''}
    <path d="M125 232 L125 268 L195 268 L195 232" fill="var(--skin)" stroke="var(--line)"/>
    <ellipse cx="160" cy="140" rx="80" ry="98" fill="var(--skin)" stroke="var(--line)" stroke-width="1.5"/>
    <path d="M80 128 C78 60 120 34 160 34 C200 34 242 60 240 128 C226 92 196 76 160 78 C124 76 94 92 80 128Z" fill="var(--hair)"/>
    <path d="M122 118 q11 7 22 0 M176 118 q11 7 22 0" fill="none" stroke="var(--hair)" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M160 128 q-5 16 -2 22 q4 2 7 0" fill="none" stroke="var(--line)" stroke-width="1.6" stroke-linecap="round"/>
    <path d="M146 182 q14 9 28 0" fill="none" stroke="#C46A5E" stroke-width="2.4" stroke-linecap="round"/>
    <ellipse cx="112" cy="160" rx="16" ry="9" fill="#F0A99A" opacity=".35"/><ellipse cx="208" cy="160" rx="16" ry="9" fill="#F0A99A" opacity=".35"/>`;
  const fiveDots = steps => el(steps, [F.forehead, F.lc, F.rc, F.nose, F.chin].map(([x, y], i) => dot(x, y, 7, 'us-pop', i * .15)).join(''));
  const spreadArrows = (steps, delay0 = 0) => el(steps, [
    sweep('M150 72 C130 66 110 66 96 76', delay0), sweep('M170 72 C190 66 210 66 224 76', delay0 + .2),
    sweep('M118 150 C104 140 96 128 92 116', delay0 + .4), sweep('M202 150 C216 140 224 128 228 116', delay0 + .6),
    sweep('M160 214 C140 220 124 214 114 204', delay0 + .8)].join(''));
  const drops = (steps, x, y, n = 3) => el(steps, [...Array(n)].map((_, i) => `<path class="us-drop" style="animation-delay:${i * .35}s" d="M${x + (i - 1) * 16} ${y} q-6 10 0 16 q6 -6 0 -16z" fill="var(--water)"/>`).join(''));
  const palm = (steps, inner = '') => el(steps, `<ellipse cx="160" cy="250" rx="58" ry="22" fill="var(--skin-d)" stroke="var(--line)"/>${inner}`);
  const clock = (steps, x, y, txt) => el(steps, `<circle cx="${x}" cy="${y}" r="26" fill="var(--card)" stroke="var(--brand)" stroke-width="3"/><line x1="${x}" y1="${y}" x2="${x}" y2="${y - 17}" stroke="var(--brand)" stroke-width="3" stroke-linecap="round" class="us-tick"/>${label(x, y + 46, txt)}`);
  const avoidZones = steps => el(steps, [F.le, F.re].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="20" fill="none" stroke="var(--warn)" stroke-width="2.5" stroke-dasharray="4 4" class="us-pulse"/>`).join('')
    + `<ellipse cx="160" cy="183" rx="26" ry="14" fill="none" stroke="var(--warn)" stroke-width="2.5" stroke-dasharray="4 4" class="us-pulse"/>` + label(160, 262, '눈가·입가는 피해요'));
  const sunBadge = steps => el(steps, `<g class="us-pulse"><circle cx="262" cy="52" r="16" fill="var(--sun)"/>${[...Array(8)].map((_, i) => { const a = i * Math.PI / 4; return `<line x1="${262 + Math.cos(a) * 21}" y1="${52 + Math.sin(a) * 21}" x2="${262 + Math.cos(a) * 27}" y2="${52 + Math.sin(a) * 27}" stroke="var(--sun)" stroke-width="3" stroke-linecap="round"/>`; }).join('')}</g>` + label(262, 100, '아침 선크림'));
  const week = (steps, on) => el(steps, `<g transform="translate(62 236)">${'월화수목금토일'.split('').map((d, i) => `<g transform="translate(${i * 30} 0)"><circle cx="13" cy="12" r="12" fill="${on.includes(i) ? 'var(--brand)' : 'var(--card)'}" stroke="var(--brand)"/><text x="13" y="16" text-anchor="middle" font-size="11" font-weight="700" fill="${on.includes(i) ? '#fff' : 'var(--brand)'}">${d}</text></g>`).join('')}</g>`);

  // 종류별 단계: [제목, 설명, 그림 조각(이 단계 번호에서 보임)]
  const KINDS = {
    cleanser: {name: '세안제', steps: [
      ['미지근한 물로 얼굴을 적셔요', '뜨거운 물은 피부를 건조하게 할 수 있어요.'], ['거품을 충분히 내요', '손바닥에서 쫀쫀한 거품을 만들어요.'],
      ['원을 그리며 30초~1분', '문지르지 말고 거품으로 부드럽게 굴려요.'], ['미지근한 물로 깨끗이 헹궈요', '헤어라인·턱 아래도 꼼꼼히 헹궈요.']],
      art: () => drops('1 4', 160, 40, 3) + palm('2', [130, 150, 170, 190].map((x, i) => `<circle cx="${x}" cy="244" r="${10 + (i % 2) * 4}" fill="var(--foam)" stroke="#BCD3EA" class="us-bub" style="animation-delay:${i * .2}s;transform-box:fill-box;transform-origin:center"/>`).join(''))
        + el('3', [F.lc, F.rc, F.forehead, F.chin].map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="15" fill="var(--foam)" stroke="#BCD3EA" class="us-bub" style="animation-delay:${i * .25}s;transform-box:fill-box;transform-origin:center"/>`).join('')
          + `<g class="us-circle" style="--ox:112px;--oy:150px">${finger(112, 128, '')}</g>`)},
    toner: {name: '토너', steps: [
      ['손바닥이나 화장솜에 덜어요', '500원 동전 크기면 충분해요.'], ['안에서 바깥으로 쓸어요', '화장솜이라면 피부결을 따라 가볍게 닦아요.'],
      ['손바닥으로 톡톡 두드려요', '흡수될 때까지 가볍게 두드려요.']],
      art: () => palm('1', `<ellipse cx="160" cy="246" rx="18" ry="7" fill="var(--water)" opacity=".6" class="us-pulse"/>`) + drops('1', 160, 200, 1)
        + spreadArrows('2') + el('3', finger(112, 128) + finger(208, 128, 'us-tap', .35))},
    serum: {name: '세럼·앰플', steps: [
      ['2~3방울을 덜어요', '손바닥이나 손등에 덜어요.'], ['다섯 군데에 나눠 찍어요', '이마·양 볼·코·턱에 나눠요.'],
      ['안에서 바깥으로 펴 발라요', '세게 문지르지 말고 가볍게 펴요.'], ['손바닥으로 감싸 흡수시켜요', '따뜻한 손바닥으로 지그시 눌러 줘요.']],
      art: () => palm('1', '') + drops('1', 160, 200, 3) + fiveDots('2 3') + spreadArrows('3', .4)
        + el('4', `<ellipse cx="96" cy="150" rx="26" ry="48" fill="var(--skin-d)" stroke="var(--line)" class="us-pulse"/><ellipse cx="224" cy="150" rx="26" ry="48" fill="var(--skin-d)" stroke="var(--line)" class="us-pulse"/>`)},
    cream: {name: '크림·로션', steps: [
      ['콩알만큼 덜어요', '건조한 날엔 조금 더 써도 좋아요.'], ['다섯 군데에 나눠 찍어요', '이마·양 볼·코·턱에 나눠요.'],
      ['결 따라 바깥으로 펴 발라요', '아래에서 위로, 안에서 바깥으로요.'], ['건조한 곳은 한 번 더', '볼이나 입가처럼 당기는 곳에 얇게 덧발라요.']],
      art: () => palm('1', `<circle cx="160" cy="246" r="9" fill="var(--cream)" stroke="var(--line)" class="us-pop"/>`) + fiveDots('2 3') + spreadArrows('3', .4)
        + el('4', [F.lc, F.rc].map(([x, y]) => `<ellipse cx="${x}" cy="${y + 8}" rx="24" ry="16" fill="var(--cream)" opacity=".7" class="us-pulse"/>`).join(''))},
    sunscreen: {name: '선크림', steps: [
      ['손가락 두 마디만큼 덜어요', '얼굴 전체에 바를 양이에요. 생각보다 많이 필요해요.'], ['얼굴 전체에 꼼꼼히', '귀와 목까지 빠짐없이 펴 발라요.'],
      ['외출 15분 전에 발라요', '피부에 자리 잡을 시간이 필요해요.'], ['2~3시간마다 덧발라요', '땀이나 물에 닦였다면 바로 다시 발라요.']],
      ears: true,
      art: () => el('1', `<g transform="translate(118 196)"><rect x="0" y="0" width="22" height="70" rx="11" fill="var(--skin-d)" stroke="var(--line)"/><rect x="28" y="6" width="22" height="64" rx="11" fill="var(--skin-d)" stroke="var(--line)"/><rect x="3" y="4" width="16" height="40" rx="8" fill="var(--cream)" class="us-pulse"/><rect x="31" y="10" width="16" height="36" rx="8" fill="var(--cream)" class="us-pulse"/></g>` + label(220, 236, '두 마디'))
        + el('2', [F.forehead, F.lc, F.rc, F.nose, F.chin, [78, 140], [242, 140], [160, 252]].map(([x, y], i) => dot(x, y, 7, 'us-pop', i * .12)).join(''))
        + clock('3', 262, 58, '15분 전') + el('4', `<path d="M248 46 a22 22 0 1 1 -6 28" fill="none" stroke="var(--brand)" stroke-width="3.5" stroke-linecap="round" marker-end="url(#usArrow)" class="us-pulse"/>` + label(262, 104, '2~3시간마다'))},
    eye: {name: '아이크림', steps: [
      ['쌀알만큼, 약지에 덜어요', '힘이 가장 약한 넷째 손가락이 좋아요.'], ['눈 아래 뼈를 따라 톡톡', '눈에 너무 가깝지 않게 뼈 위를 따라가요.'],
      ['문지르지 말고 두드려 흡수', '눈가 피부는 얇아서 살살 다뤄요.']],
      art: () => el('1', finger(160, 214) + `<circle cx="160" cy="218" r="4" fill="var(--cream)" stroke="var(--line)"/>`)
        + el('2 3', [[118, 132], [133, 136], [148, 132], [172, 132], [187, 136], [202, 132]].map(([x, y], i) => dot(x, y, 4, 'us-pop', i * .15)).join(''))
        + el('3', finger(133, 116) + finger(187, 116, 'us-tap', .35))},
    mask: {name: '마스크팩', steps: [
      ['세안하고 토너 다음에 붙여요', '눈·입 구멍을 맞춰 얼굴에 밀착시켜요.'], ['10~20분만 두어요', '마르기 전에 떼야 수분을 뺏기지 않아요.'],
      ['남은 에센스는 두드려 흡수', '떼어낸 뒤 손바닥으로 톡톡 두드려요.']],
      art: () => el('1 2', `<path d="M86 120 C86 64 120 52 160 52 C200 52 234 64 234 120 C234 190 200 232 160 232 C120 232 86 190 86 120Z" fill="#FFFFFF" opacity=".78" stroke="#D9E6F0" class="us-pop" style="transform-box:fill-box;transform-origin:center"/><ellipse cx="133" cy="118" rx="14" ry="7" fill="var(--skin)"/><ellipse cx="187" cy="118" rx="14" ry="7" fill="var(--skin)"/><ellipse cx="160" cy="182" rx="18" ry="8" fill="var(--skin)"/>`)
        + clock('2', 262, 58, '10~20분') + el('3', finger(112, 128) + finger(208, 128, 'us-tap', .35))},
    exfoliant: {name: '각질 제거(AHA·BHA)', steps: [
      ['저녁에, 세안 후 마른 피부에', '물기가 있으면 더 따가울 수 있어요.'], ['눈가·입가는 피해서 얇게', 'T존이나 각질이 많은 곳 위주로 발라요.'],
      ['주 1~3회만 써요', '매일 쓰면 피부 보호막이 약해질 수 있어요.'], ['다음 날 아침 선크림은 꼭', '각질 제거 후엔 햇빛에 예민해져요.']],
      art: () => el('1', `<g class="us-pulse"><circle cx="262" cy="56" r="16" fill="#8E9BC4"/><circle cx="270" cy="50" r="14" fill="var(--soft)"/></g>` + label(262, 100, '저녁'))
        + avoidZones('2') + el('2', [F.forehead, F.nose, F.chin].map(([x, y], i) => dot(x, y, 6, 'us-pop', i * .15)).join('')) + week('3', [1, 4]) + sunBadge('4')},
    retinol: {name: '레티놀', steps: [
      ['밤에만, 완두콩만큼', '빛에 약한 성분이라 저녁 루틴에 써요.'], ['눈가·입가는 피해서 얇게', '건조한 피부라면 보습제를 먼저 바르고 덧발라도 좋아요.'],
      ['처음엔 주 2~3회부터', '따끔거림이 없으면 조금씩 횟수를 늘려요.'], ['아침엔 선크림을 꼭', '레티놀을 쓰는 동안은 자외선 차단이 특히 중요해요.']],
      art: () => el('1', `<g class="us-pulse"><circle cx="262" cy="56" r="16" fill="#8E9BC4"/><circle cx="270" cy="50" r="14" fill="var(--soft)"/></g>` + label(262, 100, '밤') + `<circle cx="160" cy="246" r="7" fill="#F7D9A8" stroke="var(--line)" class="us-pop"/>`)
        + avoidZones('2') + el('2', [F.forehead, F.lc, F.rc, F.chin].map(([x, y], i) => dot(x, y, 5, 'us-pop', i * .15)).join('')) + week('3', [0, 3, 5]) + sunBadge('4')},
    mist: {name: '미스트', steps: [
      ['얼굴에서 20~30cm 떨어져서', '너무 가까우면 한곳에 몰려요.'], ['눈을 감고 2~3번 뿌려요', '얼굴 전체에 고르게 뿌려요.'],
      ['가볍게 두드려 흡수시켜요', '그대로 마르게 두면 오히려 건조해질 수 있어요.']],
      art: () => el('1 2', `<rect x="262" y="96" width="30" height="62" rx="8" fill="var(--card)" stroke="var(--brand)" stroke-width="2"/><rect x="270" y="84" width="14" height="14" rx="3" fill="var(--brand)"/>` + label(250, 182, '20~30cm'))
        + el('2', [...Array(8)].map((_, i) => `<circle cx="258" cy="${100 + (i % 4) * 8}" r="3" fill="var(--water)" class="us-spray" style="animation-delay:${i * .15}s;--sx:${-70 - (i % 3) * 18}px;--sy:${(i % 4 - 1.5) * 14}px"/>`).join(''))
        + el('3', finger(112, 128) + finger(208, 128, 'us-tap', .35))},
  };

  // 제품 이름(과 기능 설명)으로 종류 찾기 — 앞에 있을수록 우선
  const RULES = [
    ['mask', ['마스크', '시트팩', '팩', 'mask']], ['eye', ['아이크림', '아이 크림', '아이세럼', '아이 세럼', '아이밤', 'eye']],
    ['sunscreen', ['선크림', '선스크린', '선블록', '썬크림', '선젤', '선로션', '선스틱', '선쿠션', 'spf', '자외선']],
    ['cleanser', ['클렌징', '클렌저', '폼', '워시', '세안', '비누', '젤클렌']], ['retinol', ['레티놀', '레티날', '레티노']],
    ['exfoliant', ['필링', '각질', 'aha', 'bha', 'pha', '스크럽', '고마쥬']], ['mist', ['미스트']],
    ['toner', ['토너', '스킨', '패드', '토닉']], ['serum', ['세럼', '앰플', '에센스', '부스터', '오일']],
    ['cream', ['크림', '로션', '에멀전', '에멀젼', '밤', '젤', '플루이드']],
  ];
  function kindOf(name = '', extra = ''){
    const t = (name + ' ' + extra).toLowerCase();
    for (const [k, words] of RULES) if (words.some(w => t.includes(w))) return k;
    return 'cream';
  }

  const h = (tag, props = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) { if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); }
    for (const c of kids.flat()) if (c != null && c !== '') e.append(c);
    return e;
  };
  let timer = 0, overlay = null;
  function close(){ clearInterval(timer); if (overlay) overlay.remove(); overlay = null; document.body.style.overflow = ''; }
  function open({name = '', brand = '', usage = '', category = '', functions = ''} = {}){
    if (!document.getElementById('us-style')) document.head.append(h('style', {id: 'us-style'}, CSS));
    close();
    const kind = KINDS[category] ? category : kindOf(name, functions), K = KINDS[kind];
    const svg = h('div', {class: 'us-stage'}); svg.innerHTML = `<svg viewBox="0 0 320 280" role="img" aria-label="${K.name} 바르는 방법 그림">${face(!!K.ears)}${K.art()}</svg>`;
    const step = h('div', {class: 'us-step'}), title = h('h3', {}), text = h('p', {});
    const cap = h('div', {class: 'us-cap', 'aria-live': 'polite'}, step, title, text);
    let i = 0, playing = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    const dots = K.steps.map((_, k) => h('button', {type: 'button', class: 'us-dot', 'aria-label': `${k + 1}단계`, onclick: () => { i = k; show(); restart(); }}, h('i')));
    const play = h('button', {type: 'button', class: 'us-btn', onclick: () => { playing = !playing; play.textContent = playing ? '멈춤' : '재생'; restart(); }}, playing ? '멈춤' : '재생');
    function show(){
      step.textContent = `${i + 1} / ${K.steps.length} · ${K.name}`; title.textContent = K.steps[i][0]; text.textContent = K.steps[i][1];
      svg.querySelectorAll('.us-el').forEach(g => g.classList.toggle('on', g.dataset.s.split(' ').includes(String(i + 1))));
      dots.forEach((d, k) => d.setAttribute('aria-current', k === i ? 'step' : 'false'));
    }
    function restart(){ clearInterval(timer); if (playing) timer = setInterval(() => { i = (i + 1) % K.steps.length; show(); }, 3600); }
    const sheet = h('div', {class: 'us-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': '사용법'},
      h('div', {class: 'rx-grip', style: 'width:40px;height:5px;border-radius:3px;background:var(--line);margin:0 auto 6px'}),
      h('div', {class: 'us-head'}, h('h2', {}, `${K.name} 이렇게 발라요`), h('button', {type: 'button', class: 'us-x', 'aria-label': '닫기', onclick: close}, '×')),
      name ? h('p', {class: 'us-prod'}, [brand, name].filter(Boolean).join(' · ')) : '',
      svg, cap, h('div', {class: 'us-ctrl'}, play, h('div', {class: 'us-dots'}, dots)),
      usage ? h('div', {class: 'us-label'}, h('b', {}, '제품에 적힌 사용법 (식약처 신고 내용)'), usage) : '',
      h('p', {class: 'us-note'}, '일반적인 사용 순서 안내예요. 제품마다 다를 수 있으니 포장에 적힌 사용법을 먼저 따라 주세요. 붉어지거나 따가우면 사용을 멈춰 주세요.'));
    overlay = h('div', {class: 'rx-overlay', style: 'position:fixed;inset:0;z-index:20;background:rgba(40,32,28,.42);display:flex;align-items:flex-end;justify-content:center',
      onclick: e => { if (e.target === overlay) close(); }}, sheet);
    overlay.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
    document.body.append(overlay); document.body.style.overflow = 'hidden';
    show(); restart();
    sheet.querySelector('.us-x').focus();
  }
  const root = typeof RUTI !== 'undefined' ? RUTI : (window.RUTI = window.RUTI || {});
  root.usage = {open, close, kindOf, KINDS};
})();
