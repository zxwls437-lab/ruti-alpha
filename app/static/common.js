// 공통: 토큰 저장, API 호출, 안전한 DOM 생성
const RUTI = {
  get token(){ try { return localStorage.getItem('ruti_token') || ''; } catch { return ''; } },
  set token(v){
    try { v ? localStorage.setItem('ruti_token', v) : localStorage.removeItem('ruti_token'); } catch {}
    RUTI.native({type: 'auth'});  // 앱 안이면 다른 탭도 로그인 상태를 새로고침
  },
  // 안드로이드/iOS 앱(RUTI 앱의 WebView) 안에서 열렸는지
  get inApp(){ return !!window.ReactNativeWebView || document.documentElement.classList.contains('ruti-native') || /RUTIApp\//.test(navigator.userAgent); },
  native(msg){ try { if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(msg)); } catch {} },
  async api(path, opts = {}){
    const headers = {'Content-Type': 'application/json'};
    if (RUTI.token) headers.Authorization = 'Bearer ' + RUTI.token;
    const res = await fetch(path, {...opts, headers: {...headers, ...(opts.headers || {})},
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body)});
    let data = null; try { data = await res.json(); } catch {}
    if (!res.ok) {
      if (res.status === 401) RUTI.token = '';
      let msg = data && data.detail;
      if (Array.isArray(msg)) msg = msg.map(d => (d.msg || '').replace(/^Value error, /, '')).join(' / ');
      const err = new Error(msg || ('요청 실패 (' + res.status + ')')); err.status = res.status; throw err;
    }
    return data;
  },
  el(tag, props = {}, ...children){
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (k.startsWith('aria-') || k.startsWith('data-')) e.setAttribute(k, v); else e[k] = v;
    }
    for (const c of children.flat()) if (c != null) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return e;
  },
  CONSENTS: [
    ['age14', '[필수] 만 14세 이상이에요'], ['terms', '[필수] 이용약관에 동의해요'], ['privacy', '[필수] 개인정보 수집·이용에 동의해요'],
    ['sensitive', '[필수] 피부 상태 등 민감정보 처리에 동의해요'], ['marketing', '[선택] 새 기능·혜택 알림을 받을게요'],
  ],
  consentBoxes(kinds){
    const DOCS = {terms: '/terms', privacy: '/privacy', sensitive: '/privacy#p2'};
    return RUTI.CONSENTS.filter(([k]) => !kinds || kinds.includes(k)).map(([k, label]) =>
      RUTI.el('label', {class: 'check'}, RUTI.el('input', {type: 'checkbox', name: 'c_' + k}),
        RUTI.el('span', {}, label, DOCS[k] ? RUTI.el('a', {href: DOCS[k], target: '_blank', rel: 'noopener', style: 'margin-left:6px;font-size:13px'}, '보기') : null)));
  },
  readConsents(root){
    const out = {};
    for (const [k] of RUTI.CONSENTS) { const box = root.querySelector(`[name="c_${k}"]`); if (box) out[k] = box.checked; }
    return out;
  },
  // 로그인/회원가입 폼 연결. onReady(user)는 로그인 성공 시 호출.
  // 회원가입 버튼을 처음 누르면 이름·닉네임·동의 칸이 펼쳐지고, 한 번 더 누르면 가입한다.
  bindAuth(form, onReady){
    const err = form.querySelector('.error');
    const signupBtn = form.querySelector('[data-signup]');
    const extra = RUTI.el('div', {class: 'stack hidden'},
      RUTI.el('input', {name: 'name', placeholder: '이름 (RUTI가 불러드릴 이름)', maxLength: 30, autocomplete: 'name'}),
      RUTI.el('input', {name: 'nickname', placeholder: '닉네임 (선택, 비우면 자동으로 만들어요)', maxLength: 20}),
      RUTI.el('label', {class: 'check'}, RUTI.el('input', {type: 'checkbox', name: 'c_all', onchange: e => {
        for (const box of extra.querySelectorAll('input[type=checkbox]')) box.checked = e.target.checked;
      }}), RUTI.el('b', {}, '전체 동의')),
      ...RUTI.consentBoxes());
    signupBtn.closest('.row').before(extra);
    const done = user => {
      form.reset(); extra.classList.add('hidden'); signupBtn.textContent = '회원가입';
      if (user && user.needs_consent && user.needs_consent.length) form.classList.add('hidden');
      RUTI.afterLogin(user, onReady);
    };
    form.addEventListener('submit', async e => {
      e.preventDefault(); err.textContent = '';
      try {
        const r = await RUTI.api('/auth/login', {method: 'POST', body: {username: form.username.value.trim(), password: form.password.value}});
        RUTI.token = r.token; done(r.user);
      } catch (e2) { err.textContent = e2.message; }
    });
    signupBtn.addEventListener('click', async () => {
      err.textContent = '';
      if (extra.classList.contains('hidden')) {
        extra.classList.remove('hidden'); signupBtn.textContent = '가입하기'; form.name.focus(); return;
      }
      const body = {username: form.username.value.trim(), password: form.password.value, name: form.name.value.trim(),
                    nickname: form.nickname.value.trim() || null, consents: RUTI.readConsents(extra)};
      try { const r = await RUTI.api('/auth/signup', {method: 'POST', body}); RUTI.token = r.token; done(r.user); }
      catch (e2) { err.textContent = e2.message; }
    });
  },
  // 동의 기록이 없는(또는 철회한) 필수 항목이 있으면 동의 창을 먼저 띄운다.
  afterLogin(user, onReady){
    const missing = (user && user.needs_consent) || [];
    // 관리자 화면에서는 운영자 계정에 동의 창을 띄우지 않는다 (상담·분석 화면에서는 띄움)
    if (!missing.length || (user.is_admin && location.pathname === '/admin')) return onReady(user);
    const err = RUTI.el('div', {class: 'error'});
    const card = RUTI.el('form', {class: 'card stack', style: 'max-width:420px;margin:0'},
      RUTI.el('h2', {}, '동의가 필요해요'),
      RUTI.el('p', {class: 'muted'}, 'RUTI를 계속 이용하려면 아래 필수 항목에 동의해 주세요.'),
      ...RUTI.consentBoxes(missing), err,
      RUTI.el('div', {class: 'row'}, RUTI.el('button', {type: 'submit'}, '동의하고 계속하기'),
        RUTI.el('button', {type: 'button', class: 'ghost', onclick: () => RUTI.logout()}, '로그아웃')));
    const overlay = RUTI.el('div', {style: 'position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;padding:16px;z-index:10'}, card);
    card.addEventListener('submit', async e => {
      e.preventDefault();
      const consents = RUTI.readConsents(card);
      if (missing.some(k => !consents[k])) { err.textContent = '필수 항목에 모두 동의해 주세요.'; return; }
      try { const r = await RUTI.api('/me/consents', {method: 'PUT', body: {consents}}); overlay.remove(); onReady({...user, needs_consent: r.needs_consent}); }
      catch (e2) { err.textContent = e2.message; }
    });
    document.body.append(overlay);
  },
  async block(target, id, after){
    if (!confirm('이 사용자를 차단할까요? 이 사람의 글·댓글·후기가 더 이상 보이지 않아요. (내 정보에서 풀 수 있어요)')) return;
    try { await RUTI.api('/blocks', {method: 'POST', body: {target, id}}); if (after) after(); } catch (e) { alert(e.message); }
  },
  async logout(){ try { await RUTI.api('/auth/logout', {method: 'POST'}); } catch {} RUTI.token = ''; location.reload(); },
};

// 앱 설치(PWA): 서비스 워커 등록 + 설치 가능할 때 '앱 설치' 버튼 표시
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  const nav = document.querySelector('.topbar') || document.querySelector('nav');
  if (!nav || document.getElementById('installApp')) return;
  const btn = RUTI.el('button', {id: 'installApp', type: 'button', style: 'padding:6px 12px;font-size:13px;background:#fff;color:var(--brand-dark)',
    onclick: async () => { e.prompt(); await e.userChoice; btn.remove(); }}, '앱 설치');
  nav.append(btn);
});

// 앱 화면: 사용자 화면(분석·커뮤니티·상담·내 정보)의 메뉴를 휴대폰 앱처럼 하단 탭으로 바꾼다.
// 관리자·개발 현황 링크는 관리자 계정에만 보인다.
(function appNav(){
  const TABS = [
    ['/scan', '분석', '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>'],
    ['/community', '커뮤니티', '<circle cx="9" cy="9" r="3.5"/><circle cx="17" cy="10" r="2.5"/><path d="M3 19c.8-3 3.2-5 6-5s5.2 2 6 5M15 15c2.5 0 4.5 1.5 5.5 4"/>'],
    ['/chat', '상담', '<path d="M4 5h16v11H9l-5 4z"/>'],
    ['/mypage', '내 정보', '<circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6"/>'],
  ];
  const nav = document.querySelector('nav');
  if (!nav || !TABS.some(([p]) => p === location.pathname)) return;
  const logout = nav.querySelector('#logout');
  const top = RUTI.el('header', {class: 'topbar'}, RUTI.el('b', {}, 'RUTI'));
  const tabs = RUTI.el('nav', {class: 'tabs'}); tabs.setAttribute('aria-label', '하단 메뉴');
  for (const [path, label, icon] of TABS) {
    const a = RUTI.el('a', {href: path, class: path === location.pathname ? 'on' : ''});
    if (path === location.pathname) a.setAttribute('aria-current', 'page');
    a.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icon}</svg>`;
    a.append(label);
    tabs.append(a);
  }
  if (logout) top.append(logout);
  nav.replaceWith(top);
  document.body.classList.add('app');
  // 앱 안에서는 진짜(네이티브) 하단 탭을 쓰므로 웹 탭은 붙이지 않는다
  if (RUTI.inApp) document.body.classList.add('in-app'); else document.body.append(tabs);
  if (RUTI.token) RUTI.api('/auth/me').then(u => {
    if (u && u.is_admin) top.insertBefore(RUTI.el('span', {class: 'adminlinks'},
      RUTI.el('a', {href: '/admin'}, '관리자'), RUTI.el('a', {href: '/'}, '개발 현황')), logout || null);
  }).catch(() => {});
})();

// ---------- 내 피부 정보: 버튼으로 고르기 ----------
// 저장되는 문장은 서버의 성분 묶음 인식(scan.SENSITIVITY_GROUPS)과 맞춰 둔다.
RUTI.skin = {
  GROUPS: [
    {title: '피부 타입', single: true, options: [['건성', '건성 피부'], ['지성', '지성 피부'], ['복합성', '복합성 피부'], ['중성', '중성 피부'], ['민감성', '민감성 피부']]},
    {title: '잘 안 맞는 성분', options: [['향료', '향료에 민감해요'], ['알코올', '알코올에 민감해요'], ['각질 제거 (AHA·BHA)', '각질 제거 성분(AHA·BHA)에 민감해요'], ['레티놀', '레티놀에 민감해요']]},
    {title: '피부 고민', options: [['건조함', '건조함이 고민이에요'], ['트러블', '트러블이 잘 나요'], ['붉어짐', '붉어짐이 고민이에요'], ['모공', '모공이 고민이에요'], ['주름', '주름이 고민이에요'], ['잡티·톤', '잡티·톤이 고민이에요']]},
    {title: '기타', options: [['임신·수유 중', '임신·수유 중이에요']]},
  ],
  get all(){ return RUTI.skin.GROUPS.flatMap(g => g.options); },
  // 저장된 문장 → 짧은 이름 (직접 적은 건 그대로)
  label(text){ const o = RUTI.skin.all.find(([, full]) => full === text); return o ? o[0] : text; },
  // 요약 칩 (화면에 '건성 · 향료' 처럼)
  chips(memories){ return memories.map(m => RUTI.el('span', {class: 'tag'}, RUTI.skin.label(m.content || m))); },
  async open(onSaved){
    const {el, api} = RUTI;
    let mems = [];
    try { mems = (await api('/memory')).memories; } catch (e) { alert(e.message); return; }
    const preset = new Set(RUTI.skin.all.map(([, full]) => full));
    const chosen = new Set(mems.filter(m => preset.has(m.content)).map(m => m.content));
    const custom = mems.filter(m => !preset.has(m.content));
    const removeCustom = new Set();
    const err = el('div', {class: 'error'});
    const sheet = el('div', {class: 'sheet', role: 'dialog'});
    sheet.setAttribute('aria-modal', 'true');
    sheet.append(el('div', {class: 'sheet-head'}, el('h2', {}, '내 피부 정보'),
      el('button', {type: 'button', class: 'sheet-x', 'aria-label': '닫기', onclick: () => close()}, '×')),
      el('p', {class: 'muted'}, '고르면 성분 분석과 상담이 내 피부에 맞춰져요.'));
    let groups = [];
    groups = RUTI.skin.GROUPS.map(g => {
      const row = el('div', {class: 'chip-row'});
      const draw = () => row.replaceChildren(...g.options.map(([short, full]) => {
        const b = el('button', {type: 'button', class: 'chip-toggle', onclick: () => {
          if (chosen.has(full)) chosen.delete(full);
          else { if (g.single) g.options.forEach(([, f]) => chosen.delete(f)); chosen.add(full); }
          groups.forEach(fn => fn());
        }}, short);
        b.setAttribute('aria-pressed', String(chosen.has(full)));
        return b;
      }));
      draw();
      sheet.append(el('h3', {}, g.title), row);
      return draw;
    });
    // 직접 적은 정보
    const customList = el('div', {class: 'chip-row'});
    const drawCustom = () => customList.replaceChildren(...custom.filter(m => !removeCustom.has(m.id)).map(m =>
      el('span', {class: 'tag'}, m.content, el('button', {type: 'button', class: 'tag-x', 'aria-label': m.content + ' 지우기', onclick: () => { removeCustom.add(m.id); drawCustom(); }}, '×'))));
    drawCustom();
    const input = el('input', {placeholder: '직접 적기 (예: 시카 성분이 잘 맞아요)', maxLength: 100});
    const added = [];
    const addBtn = el('button', {type: 'button', class: 'ghost', onclick: () => {
      const t = input.value.trim(); if (!t) return;
      added.push(t); custom.push({id: 'new' + added.length, content: t}); input.value = ''; drawCustom();
    }}, '추가');
    sheet.append(el('h3', {}, '직접 적기'), customList, el('div', {class: 'row'}, input, addBtn), err);
    const save = el('button', {type: 'button', class: 'sheet-save', onclick: async () => {
      save.disabled = true; err.textContent = '';
      try {
        for (const m of mems) if ((preset.has(m.content) && !chosen.has(m.content)) || removeCustom.has(m.id)) await api('/memory/' + m.id, {method: 'DELETE'});
        const have = new Set(mems.map(m => m.content));
        for (const t of chosen) if (!have.has(t)) await api('/memory', {method: 'POST', body: {content: t}});
        for (const [i, t] of added.entries()) if (!removeCustom.has('new' + (i + 1))) await api('/memory', {method: 'POST', body: {content: t}});
        close(); if (onSaved) onSaved();
      } catch (e) { err.textContent = e.message; save.disabled = false; }
    }}, '저장');
    sheet.append(save);
    const overlay = el('div', {class: 'sheet-overlay', onclick: e => { if (e.target === overlay) close(); }}, sheet);
    function close(){ overlay.remove(); document.body.style.overflow = ''; }
    document.body.append(overlay); document.body.style.overflow = 'hidden';
  },
  // 처음 로그인했는데 피부 정보가 없으면 한 번 물어본다
  async promptOnce(user, onSaved){
    try {
      const k = 'ruti_skin_asked_' + user.id;
      if (localStorage.getItem(k)) return;
      const {memories} = await RUTI.api('/memory');
      localStorage.setItem(k, '1');
      if (!memories.length) RUTI.skin.open(onSaved);
    } catch {}
  },
};
