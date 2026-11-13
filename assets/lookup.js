/* 玩家查询页：昵称/UID → 拼成 GitHub Issue，由 Actions 实时查询并回帖
 * 昵称索引来自 data/lookup-index.json（榜单）+ data/extra-names.json（历次查询归档）。
 * GitHub 没有匿名写入口，所以「提交」这一步必须登录 GitHub。 */
(function () {
  'use strict';

  var REPO = 'fzpaihang/lanlandeku';
  var RECENT_KEY = 'fzjh_lookup_recent';
  var RECENT_MAX = 5;

  var el = {
    q: document.getElementById('q'),
    go: document.getElementById('go'),
    state: document.getElementById('state'),
    notice: document.getElementById('notice'),
    suggest: document.getElementById('suggest'),
    mode: document.getElementById('mode'),
    tips: document.getElementById('tips'),
    recent: document.getElementById('recent')
  };
  if (!el.q || !el.go) return;

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function notice(msg) {
    if (!el.notice) return;
    if (!msg) { el.notice.hidden = true; el.notice.textContent = ''; return; }
    el.notice.textContent = msg;
    el.notice.hidden = false;
  }

  function setState(text, kind) {
    if (!el.state) return;
    el.state.textContent = text;
    el.state.className = 'pill' + (kind === 'warn' ? '' : ' ghost');
  }

  function fetchJson(url) {
    return fetch(url, { credentials: 'omit' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  /* ---------- 昵称索引 ---------- */

  var NAMES = null;

  function loadNames() {
    if (NAMES) return Promise.resolve(NAMES);
    var jobs = ['./data/lookup-index.json', './data/extra-names.json'].map(function (u) {
      return fetchJson(u).then(function (v) { return v; }, function () { return null; });
    });
    return Promise.all(jobs).then(function (res) {
      var map = {};
      var base = (res[0] && res[0].players) || [];
      var extra = (res[1] && res[1].items) || [];
      base.forEach(function (p) {
        if (!p || p.u == null) return;
        map[String(p.u)] = { u: p.u, n: p.n, s: p.s, sn: p.sn, lv: p.lv, a: [] };
      });
      extra.forEach(function (p) {
        if (!p || p.u == null) return;
        var k = String(p.u);
        var cur = map[k];
        if (cur) {
          cur.n = p.n || cur.n;
          cur.s = p.s || cur.s;
          cur.sn = p.sn || cur.sn;
          cur.lv = p.lv || cur.lv;
          cur.a = p.a || [];
        } else {
          map[k] = { u: p.u, n: p.n, s: p.s, sn: p.sn, lv: p.lv, a: p.a || [] };
        }
      });
      NAMES = Object.keys(map).map(function (k) { return map[k]; });
      return NAMES;
    }, function () { NAMES = []; return NAMES; });
  }

  function search(text) {
    var k = String(text || '').trim().toLowerCase();
    if (!k) return [];
    var out = [];
    (NAMES || []).forEach(function (p) {
      var names = [p.n].concat(p.a || []);
      var best = 9;
      for (var i = 0; i < names.length; i++) {
        var n = String(names[i] || '').toLowerCase();
        if (!n) continue;
        if (n === k) { best = 0; break; }
        if (n.indexOf(k) === 0) { if (best > 1) best = 1; }
        else if (n.indexOf(k) > 0) { if (best > 2) best = 2; }
      }
      if (best < 9) out.push({ p: p, s: best });
    });
    out.sort(function (a, b) { return a.s - b.s || (b.p.lv || 0) - (a.p.lv || 0); });
    return out.slice(0, 8);
  }

  function hideSuggest() {
    if (!el.suggest) return;
    el.suggest.hidden = true;
    el.suggest.textContent = '';
    el.q.setAttribute('aria-expanded', 'false');
  }

  function renderSuggest(list) {
    if (!el.suggest) return;
    el.suggest.textContent = '';
    if (!list.length) return hideSuggest();
    list.forEach(function (item) {
      var b = h('button');
      b.type = 'button';
      b.setAttribute('role', 'option');
      b.appendChild(h('span', 's-n', item.p.n));
      var tail = item.p.sn || item.p.s || '';
      if (item.p.lv) tail += ' · lv' + item.p.lv;
      b.appendChild(h('span', 's-m', tail));
      b.addEventListener('click', function () {
        el.q.value = item.p.n;
        hideSuggest();
        openIssue(item.p.u, item.p.s);
      });
      el.suggest.appendChild(b);
    });
    el.suggest.hidden = false;
    el.q.setAttribute('aria-expanded', 'true');
  }

  /* ---------- 最近提交 ---------- */

  function readRecent() {
    try {
      var raw = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
      return Array.isArray(raw) ? raw.filter(function (x) { return x && x.uid; }).slice(0, RECENT_MAX) : [];
    } catch (e) {
      return [];
    }
  }

  function pushRecent(uid, name, server) {
    var list = readRecent().filter(function (x) { return String(x.uid) !== String(uid); });
    list.unshift({ uid: String(uid), name: name || '', s: server || '' });
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX))); } catch (e) { }
    renderRecent();
  }

  function renderRecent() {
    if (!el.recent) return;
    var list = readRecent();
    el.recent.textContent = '';
    if (el.tips) el.tips.hidden = !list.length;
    list.forEach(function (x) {
      var label = x.name ? (x.name + ' · ' + x.uid) : ('UID ' + x.uid);
      var b = h('button', 'lk-chip', label);
      b.type = 'button';
      b.addEventListener('click', function () {
        el.q.value = x.uid;
        openIssue(x.uid, x.s);
      });
      el.recent.appendChild(b);
    });
  }

  /* ---------- 提交 Issue ---------- */

  function issueUrl(uid, server) {
    var title = '[QUERY] ' + uid + (server ? ' @' + server : '');
    var body = [
      '由网页提交的实时查询，**请勿修改标题**（机器人靠标题识别 UID 和分区）。',
      '',
      '- UID：' + uid,
      '- 分区：' + (server || '自动（按 UID 位数猜 2 个区）'),
      '',
      '提交后约 30–90 秒会有一条评论返回档案，同时该角色的 UID 与昵称会被收录进昵称索引。'
    ].join('\n');
    return 'https://github.com/' + REPO + '/issues/new?title=' +
      encodeURIComponent(title) + '&body=' + encodeURIComponent(body);
  }

  function openIssue(uid, server) {
    if (el.mode) el.mode.textContent = '';
    pushRecent(uid, '', server);
    setState('等待提交', 'warn');
    notice('已打开 GitHub 页面：点「Submit new issue」后约 30–90 秒出结果，结果会作为评论出现。');
    var w = window.open(issueUrl(uid, server), '_blank', 'noopener');
    if (!w) notice('弹窗被拦截了，请允许弹窗后重试。');
  }

  function choose(p) {
    el.q.value = p.n || String(p.u);
    hideSuggest();
    pushRecent(p.u, p.n, p.s);
    openIssue(p.u, p.s);
  }

  function submit() {
    var raw = el.q.value.trim();
    if (!raw) { el.q.focus(); return; }

    if (/^\d{5,12}$/.test(raw)) { openIssue(raw, ''); return; }

    if (!NAMES) {
      loadNames().then(function () { submit(); });
      return;
    }

    var list = search(raw);
    if (!list.length) {
      setState('没有匹配', 'warn');
      notice('没有匹配的昵称「' + raw + '」。榜外玩家请直接输入 UID（5–12 位数字）。');
      return;
    }
    var exact = list.filter(function (x) {
      return String(x.p.n || '').toLowerCase() === raw.toLowerCase();
    });
    if (list.length === 1) { choose(list[0].p); return; }
    if (exact.length === 1) { choose(exact[0].p); return; }

    renderSuggest(list);
    setState('选择角色', 'warn');
    notice('有 ' + list.length + ' 个相近的角色，点一个继续。');
  }

  /* ---------- 事件 ---------- */

  el.go.addEventListener('click', submit);

  el.q.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); submit(); return; }
    if (e.key === 'Escape') { hideSuggest(); return; }
    if (e.key === 'ArrowDown' && el.suggest && !el.suggest.hidden) {
      e.preventDefault();
      var first = el.suggest.querySelector('button');
      if (first) first.focus();
    }
  });

  var inputTimer = null;
  el.q.addEventListener('input', function () {
    if (inputTimer) clearTimeout(inputTimer);
    var v = el.q.value.trim();
    if (!v || /^\d+$/.test(v)) { hideSuggest(); return; }
    inputTimer = setTimeout(function () {
      if (!NAMES) return;
      renderSuggest(search(v));
    }, 120);
  });

  document.addEventListener('click', function (e) {
    if (el.suggest && !el.suggest.hidden &&
        !el.suggest.contains(e.target) && e.target !== el.q) {
      hideSuggest();
    }
  });

  /* ---------- 启动 ---------- */

  loadNames().then(function (list) {
    if (!list.length) notice('昵称索引没加载出来，暂时只能用 UID 查询。');
    var q = new URLSearchParams(location.search).get('uid');
    if (q && /^\d{5,12}$/.test(q)) el.q.value = q;
  });
  renderRecent();
})();
