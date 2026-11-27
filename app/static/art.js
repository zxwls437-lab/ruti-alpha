// RUTI 그림: 제품 그림(사진이 없을 때 종류별로 그린 용기)과 홈 화면 일러스트.
// 모든 그림은 RUTI가 직접 그린 SVG라서 저작권 걱정이 없다.
(function (root) {
  const NS = 'http://www.w3.org/2000/svg';
  const RULES = [
    ['sunscreen', ['선크림', '선스크린', '선블록', '썬크림', '선젤', '선로션', '선스틱', '선밀크', '선세럼', '선쿠션', 'spf', '자외선']],
    ['cleanser', ['클렌저', '클렌징', '폼', '세안', '워시', '비누']],
    ['mask', ['마스크', '팩', '패치', '시트']],
    ['mist', ['미스트', '스프레이']],
    ['eye', ['아이크림', '아이세럼', '아이 크림']],
    ['serum', ['세럼', '앰플', '에센스', '부스터', '오일']],
    ['toner', ['토너', '스킨', '패드', '토닉']],
    ['lotion', ['로션', '에멀전', '에멀젼', '플루이드', '밀크']],
    ['cream', ['크림', '밤', '젤']],
  ];
  const kindOf = (name = '', extra = '') => {
    const t = (name + ' ' + extra).toLowerCase();
    for (const [k, words] of RULES) if (words.some(w => t.includes(w))) return k;
    return 'cream';
  };
  // 이름마다 정해진 파스텔 색 (같은 제품은 항상 같은 색)
  const PALETTE = [['#F6D6C8', '#E9A98E'], ['#D7E8DF', '#8DBBA9'], ['#E3DDF3', '#A99BD6'], ['#FBE9C6', '#E7B95C'],
                   ['#D9E7F5', '#86AEDB'], ['#F7D9E3', '#E39AB3'], ['#E5EEDC', '#A9C48C'], ['#F2E2D2', '#C9A27E']];
  const hash = s => { let x = 7; for (const c of s) x = (x * 31 + c.charCodeAt(0)) >>> 0; return x; };
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const short = (name) => {
    const first = (name || '').split(/\s+/)[0] || '';
    return first.length > 7 ? first.slice(0, 6) + '…' : first;
  };

  // 용기 모양 (viewBox 0 0 120 140). l = 라벨 영역 [x, y, w, h]
  const SHAPES = {
    cream: (c, d) => ({body: `<ellipse cx="60" cy="122" rx="40" ry="6" fill="#000" opacity=".08"/>
      <rect x="22" y="62" width="76" height="58" rx="14" fill="${c}"/><rect x="18" y="44" width="84" height="24" rx="9" fill="${d}"/>
      <rect x="24" y="48" width="30" height="5" rx="2.5" fill="#fff" opacity=".45"/>`, l: [30, 76, 60, 30]}),
    lotion: (c, d) => ({body: `<ellipse cx="60" cy="126" rx="28" ry="5" fill="#000" opacity=".08"/>
      <rect x="34" y="46" width="52" height="78" rx="14" fill="${c}"/><rect x="50" y="30" width="20" height="18" rx="4" fill="${d}"/>
      <rect x="56" y="14" width="8" height="18" rx="3" fill="${d}"/><path d="M60 16h22v7H66" fill="none" stroke="${d}" stroke-width="7" stroke-linecap="round"/>`, l: [40, 66, 40, 40]}),
    toner: (c, d) => ({body: `<ellipse cx="60" cy="126" rx="26" ry="5" fill="#000" opacity=".08"/>
      <rect x="36" y="38" width="48" height="86" rx="10" fill="${c}"/><rect x="44" y="18" width="32" height="22" rx="6" fill="${d}"/>
      <rect x="40" y="44" width="8" height="70" rx="4" fill="#fff" opacity=".35"/>`, l: [42, 62, 36, 44]}),
    serum: (c, d) => ({body: `<ellipse cx="60" cy="126" rx="24" ry="5" fill="#000" opacity=".08"/>
      <rect x="38" y="56" width="44" height="68" rx="10" fill="${c}"/><rect x="48" y="40" width="24" height="18" rx="4" fill="${d}"/>
      <path d="M52 40c0-14 4-26 8-26s8 12 8 26z" fill="${d}"/><rect x="42" y="60" width="7" height="56" rx="3.5" fill="#fff" opacity=".35"/>`, l: [44, 74, 32, 36]}),
    sunscreen: (c, d) => ({body: `<ellipse cx="60" cy="128" rx="26" ry="5" fill="#000" opacity=".08"/>
      <path d="M34 20h52l-6 84H40z" fill="${c}"/><rect x="42" y="102" width="36" height="24" rx="5" fill="${d}"/>
      <rect x="34" y="16" width="52" height="8" rx="2" fill="${d}"/><rect x="40" y="28" width="6" height="66" rx="3" fill="#fff" opacity=".35"/>`, l: [42, 40, 36, 40]}),
    cleanser: (c, d) => ({body: `<ellipse cx="60" cy="128" rx="26" ry="5" fill="#000" opacity=".08"/>
      <path d="M32 16h56l-8 88H40z" fill="${c}"/><rect x="44" y="102" width="32" height="24" rx="12" fill="${d}"/>
      <circle cx="78" cy="30" r="6" fill="#fff" opacity=".6"/><circle cx="86" cy="20" r="4" fill="#fff" opacity=".5"/>`, l: [40, 38, 40, 40]}),
    eye: (c, d) => ({body: `<ellipse cx="60" cy="128" rx="20" ry="4" fill="#000" opacity=".08"/>
      <path d="M44 22h32l-4 82H48z" fill="${c}"/><path d="M50 104h20v14a10 10 0 0 1-20 0z" fill="${d}"/>
      <rect x="44" y="18" width="32" height="7" rx="2" fill="${d}"/>`, l: [47, 42, 26, 40]}),
    mask: (c, d) => ({body: `<ellipse cx="60" cy="126" rx="38" ry="5" fill="#000" opacity=".08"/>
      <path d="M24 20h72v100H24z" fill="${c}"/><path d="M24 20h72v10H24zM24 110h72v10H24z" fill="${d}" opacity=".7"/>
      <path d="M30 26l6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6" fill="none" stroke="#fff" stroke-width="2" opacity=".6"/>`, l: [32, 48, 56, 44]}),
    mist: (c, d) => ({body: `<ellipse cx="60" cy="126" rx="24" ry="5" fill="#000" opacity=".08"/>
      <rect x="38" y="46" width="44" height="78" rx="12" fill="${c}"/><rect x="50" y="30" width="20" height="18" rx="4" fill="${d}"/>
      <rect x="47" y="20" width="26" height="12" rx="4" fill="${d}"/><circle cx="84" cy="18" r="3" fill="${d}" opacity=".5"/><circle cx="92" cy="12" r="2.5" fill="${d}" opacity=".4"/>`, l: [44, 66, 32, 40]}),
  };

  function productSVG(p, {size = 88} = {}) {
    const name = p.name || '';
    const kind = kindOf(name, p.functions || p.category || '');
    const [c, d] = PALETTE[hash(name + (p.brand || '')) % PALETTE.length];
    const {body, l} = (SHAPES[kind] || SHAPES.cream)(c, d);
    const spf = /SPF\s?50/i.test((p.functions || '') + name);
    const label = esc(short(name));
    return `<svg viewBox="0 0 120 140" width="${size}" height="${size * 140 / 120}" role="img" aria-label="${esc(name)} 그림">
      ${body}<rect x="${l[0]}" y="${l[1]}" width="${l[2]}" height="${l[3]}" rx="5" fill="#fff" opacity=".9"/>
      <text x="${l[0] + l[2] / 2}" y="${l[1] + l[3] / 2 - 2}" text-anchor="middle" font-size="${Math.min(10, l[2] / Math.max(3, label.length) * 1.5).toFixed(1)}" font-weight="800" fill="${d}">${label}</text>
      <rect x="${l[0] + l[2] / 2 - 9}" y="${l[1] + l[3] / 2 + 5}" width="18" height="2.5" rx="1.2" fill="${d}" opacity=".5"/>
      ${spf ? `<g><circle cx="94" cy="32" r="15" fill="#fff" stroke="${d}" stroke-width="2"/><text x="94" y="30" text-anchor="middle" font-size="7.5" font-weight="800" fill="${d}">SPF</text><text x="94" y="39" text-anchor="middle" font-size="8" font-weight="800" fill="${d}">50+</text></g>` : ''}
    </svg>`;
  }

  // 진짜 사진이 있으면 사진, 없거나 못 불러오면 그림
  function product(p, opts = {}) {
    const box = document.createElement('div');
    box.className = 'p-art';
    const art = () => { box.innerHTML = productSVG(p, opts); };
    if (p.image) {
      const img = document.createElement('img');
      img.src = p.image; img.alt = p.name || ''; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
      img.onerror = art; box.append(img);
    } else art();
    return box;
  }

  // 홈 화면 일러스트: 아침·낮·저녁마다 다른 하늘과 RUTI 물방울 친구
  function hero(hour = new Date().getHours()) {
    const t = hour < 11 ? 'am' : hour < 18 ? 'day' : 'pm';
    const sky = {am: ['#FFE9D6', '#FCD3C1'], day: ['#E2F2EA', '#CDE6DA'], pm: ['#2E2A4A', '#46406B']}[t];
    const ink = t === 'pm' ? '#F4EEDF' : '#3A3330';
    const orb = t === 'pm'
      ? `<g class="h-float2"><circle cx="300" cy="40" r="18" fill="#F6E7B5"/><circle cx="308" cy="34" r="16" fill="${sky[0]}"/></g>
         <g fill="#F6E7B5"><circle class="h-twinkle" cx="40" cy="30" r="2"/><circle class="h-twinkle d2" cx="250" cy="22" r="1.6"/><circle class="h-twinkle d3" cx="200" cy="60" r="1.4"/><circle class="h-twinkle" cx="90" cy="64" r="1.5"/></g>`
      : `<g class="h-spin" style="transform-origin:300px 40px"><circle cx="300" cy="40" r="16" fill="${t === 'am' ? '#FFC36B' : '#FFD98A'}"/>
         ${[0, 45, 90, 135, 180, 225, 270, 315].map(a => `<rect x="298.5" y="14" width="3" height="7" rx="1.5" fill="#FFC36B" transform="rotate(${a} 300 40)"/>`).join('')}</g>`;
    const face = t === 'pm'
      ? `<path d="M168 92q5 4 10 0M190 92q5 4 10 0" stroke="#3A3330" stroke-width="2.4" fill="none" stroke-linecap="round"/>`
      : `<circle cx="173" cy="91" r="3.2" fill="#3A3330"/><circle cx="195" cy="91" r="3.2" fill="#3A3330"/>`;
    const gid = 'hg' + t + Math.random().toString(36).slice(2, 7);
    const svg = `<svg viewBox="0 0 360 150" class="hero-svg" role="img" aria-label="RUTI 물방울 친구 그림">
      <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient></defs>
      <rect width="360" height="150" rx="22" fill="url(#${gid})"/>${orb}
      <g opacity=".55" fill="#fff"><circle class="h-bubble" cx="70" cy="120" r="7"/><circle class="h-bubble d2" cx="110" cy="128" r="4.5"/><circle class="h-bubble d3" cx="250" cy="124" r="6"/><circle class="h-bubble d2" cx="285" cy="130" r="3.5"/></g>
      <rect x="40" y="128" width="280" height="10" rx="5" fill="#000" opacity=".06"/>
      <g class="h-float">
        <path d="M184 44c18 22 30 38 30 54a30 30 0 0 1-60 0c0-16 12-32 30-54z" fill="#9CCBB8"/>
        <path d="M172 70c-6 9-9 17-9 25" stroke="#fff" stroke-width="4" stroke-linecap="round" opacity=".6" fill="none"/>
        ${face}<ellipse cx="166" cy="102" rx="5" ry="3" fill="#F2A7A0" opacity=".7"/><ellipse cx="202" cy="102" rx="5" ry="3" fill="#F2A7A0" opacity=".7"/>
        <path d="M178 104q6 6 12 0" stroke="#3A3330" stroke-width="2.4" fill="none" stroke-linecap="round"/>
      </g>
      <g transform="translate(60 76) scale(.38)">${SHAPES.toner('#F7D9E3', '#E39AB3').body}</g>
      <g transform="translate(232 82) scale(.34)">${SHAPES.cream('#FBE9C6', '#E7B95C').body}</g>
      <g transform="translate(268 70) scale(.38)">${(t === 'pm' ? SHAPES.serum : SHAPES.sunscreen)('#D9E7F5', '#86AEDB').body}</g>
      <text x="22" y="34" font-size="13" font-weight="800" fill="${ink}" opacity=".85">${{am: '좋은 아침이에요 ☀️', day: '오늘도 촉촉하게 💧', pm: '오늘도 수고했어요 🌙'}[t]}</text>
    </svg>`;
    const wrap = document.createElement('div');
    wrap.className = 'hero-art'; wrap.innerHTML = svg;
    return wrap;
  }

  const CSS = `.p-art{flex:0 0 auto;display:flex;align-items:center;justify-content:center;border-radius:16px;background:var(--soft,#EAF2EE);overflow:hidden}
.p-art img{width:100%;height:100%;object-fit:cover}
.hero-art{margin:4px 0 14px}.hero-svg{width:100%;height:auto;display:block}
@keyframes hFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
@keyframes hBubble{0%{transform:translateY(0);opacity:0}20%{opacity:.9}100%{transform:translateY(-70px);opacity:0}}
@keyframes hSpin{to{transform:rotate(360deg)}}@keyframes hTw{0%,100%{opacity:.3}50%{opacity:1}}
.h-float{animation:hFloat 3.2s ease-in-out infinite}.h-float2{animation:hFloat 4.5s ease-in-out infinite}
.h-bubble{animation:hBubble 4.2s ease-in infinite}.h-bubble.d2{animation-delay:1.4s}.h-bubble.d3{animation-delay:2.6s}
.h-spin{animation:hSpin 24s linear infinite}.h-twinkle{animation:hTw 2.4s ease-in-out infinite}.h-twinkle.d2{animation-delay:.8s}.h-twinkle.d3{animation-delay:1.6s}
@media (prefers-reduced-motion:reduce){.h-float,.h-float2,.h-bubble,.h-spin,.h-twinkle{animation:none}}`;
  if (!document.getElementById('art-style')) {
    const st = document.createElement('style'); st.id = 'art-style'; st.textContent = CSS; document.head.append(st);
  }
  const R = root.RUTI || root;
  R.art = {product, productSVG, hero, kindOf};
})(typeof RUTI !== 'undefined' ? {RUTI} : window);
