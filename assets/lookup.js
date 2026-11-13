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
    srv: document.getElementById('srv'),
    mode: document.getElementById('mode'),
    out: document.getElementById('out'),
    who: document.getElementById('who'),
    sub: document.getElementById('sub'),
    body: document.getElementById('body'),
    meta: document.getElementById('meta'),
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
      // 苍松 5 转老玩家（8 万普查里筛出来的，多数不在榜上）——榜单已有的不覆盖
      var zhuan = (res[0] && res[0].zhuan5) || [];
      zhuan.forEach(function (it) {
        if (!it || it.length < 2 || it[0] == null) return;
        var zk = String(it[0]);
        if (map[zk]) return;
        map[zk] = { u: it[0], n: String(it[1] || ''), s: 'taptap', sn: '苍松迎客', lv: null, a: [] };
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
        choose(item.p);
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
        if (x.s) setServer(x.s);
        openIssue(x.uid, currentServer() || x.s);
      });
      el.recent.appendChild(b);
    });
  }

  /* ---------- 提交 Issue ---------- */

  function titleFor(uid, server) {
    return '[QUERY] ' + uid + (server ? ' @' + server : '');
  }

  function issueUrl(uid, server) {
    var title = titleFor(uid, server);
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

  function currentServer() {
    return el.srv ? String(el.srv.value || '') : '';
  }

  function setServer(key) {
    if (!el.srv || !key) return false;
    var before = el.srv.value;
    el.srv.value = key;
    if (el.srv.value === key) return true;
    el.srv.value = before;      // 选项里没有这个 key，回退
    return false;
  }

  function openIssue(uid, server, name) {
    if (!server) {
      setState('请选分区', 'warn');
      notice('提交前请先选择角色所在的分区——自动匹配已停用，选错会查不到。');
      return;
    }
    if (el.mode) el.mode.textContent = '';
    pushRecent(uid, name || '', server);
    setState('等待提交', 'warn');

    var url = issueUrl(uid, server);
    // 注意：带 'noopener' 时 window.open 永远返回 null，不能用返回值判断是否被拦截
    var w = null;
    try { w = window.open(url, '_blank'); } catch (e) { w = null; }
    if (w) { try { w.opener = null; } catch (e) { } }

    // 无论有没有弹出成功，都留一个可点的入口，避免被拦截时卡住
    if (el.mode) {
      var a = document.createElement('a');
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = '没打开？点这里进入提交页 ›';
      a.style.color = 'var(--accent)';
      el.mode.appendChild(a);
    }

    savePending({
      uid: String(uid),
      server: server,
      title: titleFor(uid, server),
      at: Date.now(),
      issue: 0
    });
    startPolling('已打开 GitHub 页面：点右下角绿色「Create」提交，本页会自动显示结果（约 45–60 秒），不用去评论区。');
  }

  /* ---------- 自动回显：轮询公开 Issue 取结果 ---------- */

  var PEND_KEY = 'fzjh_lookup_pending';
  var API = 'https://api.github.com/repos/' + REPO;
  var POLL_MS = 5000;
  var POLL_MAX = 40;          // 约 3 分钟
  var WAIT_CREATE_MS = 90000; // 90 秒还没出现新 Issue，说明可能没点 Create
  var pollTimer = null;
  var pollLeft = 0;

  function savePending(p) {
    try { localStorage.setItem(PEND_KEY, JSON.stringify(p)); } catch (e) { }
  }

  function readPending() {
    try { return JSON.parse(localStorage.getItem(PEND_KEY) || 'null'); } catch (e) { return null; }
  }

  function clearPending() {
    try { localStorage.removeItem(PEND_KEY); } catch (e) { }
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function startPolling(msg) {
    stopPolling();
    pollLeft = POLL_MAX;
    setState('等待结果', 'warn');
    notice(msg || '正在等待结果…（约 45–60 秒，本页会自动显示，不用去评论区）');
    tick();
    pollTimer = setInterval(tick, POLL_MS);
  }

  function tick() {
    var p = readPending();
    if (!p) { stopPolling(); return; }
    if (pollLeft-- <= 0) {
      stopPolling();
      setState('等待超时', 'warn');
      notice('还没等到结果。可能是没在 GitHub 上点「Create」，也可能接口正忙——去那条 Issue 看看评论。');
      return;
    }

    // 90 秒还没出现新 Issue，多半是没点 Create，不再空耗接口额度
    if (!p.issue && p.at && Date.now() - p.at > WAIT_CREATE_MS) {
      stopPolling();
      setState('未检测到提交', 'warn');
      notice('90 秒内没检测到新 Issue——可能没在 GitHub 点「Create」。点上面的链接重试，或刷新本页继续等。');
      return;
    }

    var found = p.issue
      ? Promise.resolve({ number: p.issue })
      : findIssue(p).then(function (it) {
          if (it) { p.issue = it.number; savePending(p); }
          return it;
        });
    found.then(function (it) {
      if (!it) return null;
      return fetchJson(API + '/issues/' + it.number + '/comments').then(function (cs) {
        if (!cs || !cs.length) return null;
        var m = String(cs[cs.length - 1].body || '').match(/<!--FZJHJSON (\{[\s\S]*?\})-->/);
        return m ? { meta: JSON.parse(m[1]), number: it.number, total: cs.length } : null;
      });
    }).then(function (res) {
      if (!res) return;
      stopPolling();
      clearPending();
      renderMeta(res.meta, res.number);
      setState('已返回');
      notice('');
    }).catch(function () { /* 网络抖动就等下一轮 */ });
  }

  function findIssue(p) {
    var url = API + '/issues?state=all&sort=created&direction=desc&per_page=30';
    return fetchJson(url).then(function (list) {
      if (!Array.isArray(list)) return null;
      var since = (p.at || 0) - 120000;      // 允许 2 分钟时钟偏差
      for (var i = 0; i < list.length; i++) {
        var it = list[i];
        if (it.pull_request) continue;
        if ((it.title || '') !== p.title) continue;
        if (new Date(it.created_at).getTime() < since) continue;
        return it;
      }
      return null;
    });
  }

  function fmtBig(n) {
    if (n == null || n === '') return '—';
    n = Number(n);
    if (!isFinite(n)) return '—';
    var a = Math.abs(n);
    if (a >= 1e8) return (n / 1e8).toFixed(2) + '亿';
    if (a >= 1e4) return (n / 1e4).toFixed(1) + '万';
    return String(Math.round(n));
  }

  function summaryGrid(m) {
    var grid = document.createElement('div');
    grid.className = 'pf-grid';
    [['等级', m.lv], ['门派', m.m || m.menpai], ['经验', fmtBig(m.exp)], ['福缘', m.fy != null ? m.fy : m.fuyuan],
     ['武学造诣', m.k != null ? Number(m.k).toFixed(2) : (m.kongfu != null ? Number(m.kongfu).toFixed(2) : null)],
     ['传承', (m.ic != null ? m.ic : m.inheritCount) != null ? (m.ic != null ? m.ic : m.inheritCount) + ' 次' : null],
     ['武学', m.sk != null ? m.sk + ' 门' : (m.skills ? m.skills.length + ' 门' : null)],
     ['装备', m.eq != null ? m.eq + ' 件' : (m.equips ? m.equips.length + ' 件' : null)]].forEach(function (kv) {
      var cell = document.createElement('dl');   // dt/dd 必须放在 dl 里才合法
      cell.className = 'pf-cell';
      var dt = document.createElement('dt');
      dt.textContent = kv[0];
      var dd = document.createElement('dd');
      dd.textContent = (kv[1] === null || kv[1] === undefined || kv[1] === '') ? '—' : String(kv[1]);
      cell.appendChild(dt);
      cell.appendChild(dd);
      grid.appendChild(cell);
    });
    return grid;
  }

  function renderMeta(m, issueNo) {
    if (!el.out) return;
    var isFull = Array.isArray(m.skills);
    el.out.hidden = false;
    el.who.textContent = m.name || m.n || ('UID ' + m.uid);

    var sub = [];
    if (m.serverName || m.sn) sub.push(m.serverName || m.sn);
    sub.push('UID ' + m.uid);
    if (m.rank || m.r) sub.push('第 ' + (m.rank || m.r) + ' 名');
    el.sub.textContent = sub.join(' · ');

    if (el.body) {
      el.body.textContent = '';
      if (isFull && window.FZJH && typeof window.FZJH.renderProfile === 'function') {
        window.FZJH.renderProfile(el.body, m);      // 完整档案：与高手榜弹窗同一套渲染
      } else {
        el.body.appendChild(summaryGrid(m));        // 旧评论只有摘要时兜底
      }
    }

    var bits = [];
    if (m.stale) bits.push('榜单快照（非实时）');
    if (m.fetchedAt || m.at) bits.push('数据时间 ' + (m.fetchedAt || m.at));
    if (m.ms) bits.push('耗时 ' + (m.ms / 1000).toFixed(1) + ' 秒');

    el.meta.textContent = '';
    if (bits.length) el.meta.appendChild(document.createTextNode(bits.join(' · ') + ' · '));
    var a = document.createElement('a');
    a.href = 'https://github.com/' + REPO + '/issues/' + issueNo;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = '在 GitHub 查看 Issue #' + issueNo + ' ›';
    a.style.color = 'var(--accent)';
    el.meta.appendChild(a);
  }

  function choose(p) {
    el.q.value = p.n || String(p.u);
    hideSuggest();
    // 昵称命中时用索引里的分区，选不到就沿用当前下拉
    var sv = (p.s && setServer(p.s)) ? p.s : currentServer();
    openIssue(p.u, sv, p.n);
  }

  function submit() {
    var raw = el.q.value.trim();
    if (!raw) { el.q.focus(); return; }

    if (/^\d{5,12}$/.test(raw)) { openIssue(raw, currentServer()); return; }

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

  var savedPending = readPending();
  if (savedPending && Date.now() - (savedPending.at || 0) < 10 * 60 * 1000) {
    startPolling();                 // 上次提交还没看到结果，继续等
  } else if (savedPending) {
    clearPending();
  }
})();
