// 공통: 토큰 저장, API 호출, 안전한 DOM 생성
const RUTI = {
  get token(){ try { return localStorage.getItem('ruti_token') || ''; } catch { return ''; } },
  set token(v){ try { v ? localStorage.setItem('ruti_token', v) : localStorage.removeItem('ruti_token'); } catch {} },
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
      if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e[k] = v;
    }
    for (const c of children.flat()) if (c != null) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return e;
  },
  CONSENTS: [
    ['age14', '[필수] 만 14세 이상이에요'], ['terms', '[필수] 이용약관에 동의해요'], ['privacy', '[필수] 개인정보 수집·이용에 동의해요'],
    ['sensitive', '[필수] 피부 상태 등 민감정보 처리에 동의해요'], ['marketing', '[선택] 새 기능·혜택 알림을 받을게요'],
  ],
  consentBoxes(kinds){
    return RUTI.CONSENTS.filter(([k]) => !kinds || kinds.includes(k)).map(([k, label]) =>
      RUTI.el('label', {class: 'check'}, RUTI.el('input', {type: 'checkbox', name: 'c_' + k}), label));
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
    if (!missing.length) return onReady(user);
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
  async logout(){ try { await RUTI.api('/auth/logout', {method: 'POST'}); } catch {} RUTI.token = ''; location.reload(); },
};
