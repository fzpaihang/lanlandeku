/* 放置江湖 · 名人堂（按江湖阅历，boardType=4）—— 独立页面，不依赖 app.js */
(function () {
  'use strict';

  function base() { return (window.FZJH && FZJH.base) ? FZJH.base : './data/servers/taptap/'; }
  function dataUrl() { return base() + 'hall.json'; }

  var state = {
    rows: [],
    // 默认按游戏原始名次（榜单顺序才权威，前端绝不自己按阅历重排）
    sortKey: 'rank',
    sortDir: 'asc',
    me: new URLSearchParams(location.search).get('me') || ''
  };

  var el = {
    tbody: document.getElementById('tbody'),
    cards: document.getElementById('cards'),
    updated: document.getElementById('updated'),
    count: document.getElementById('count'),
    empty: document.getElementById('empty'),
    tbl: document.getElementById('tbl'),
    sortbar: document.getElementById('sortbar'),
    notice: document.getElementById('notice')
  };

  /* 窄屏走卡片列表，断点与 style.css 的 560px 保持一致 */
  var mqMobile = window.matchMedia('(max-width: 560px)');
  var isMobile = function () { return mqMobile.matches; };

  /* ---------- 工具 ---------- */

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  /* 千分位：阅历是 7~8 位整数，读起来太长 */
  function fmtInt(n) {
    if (n === null || n === undefined || n === '') return '—';
    n = Number(n);
    if (!isFinite(n)) return '—';
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /* 阅历在游戏里是浮点（如 2639341.0875）：先四舍五入取整，再加千分位 */
  function fmtYueli(n) {
    if (n === null || n === undefined || n === '') return '—';
    var v = Number(n);
    if (!isFinite(v)) return '—';
    return fmtInt(Math.round(v));
  }

  function kv(label, value) {
    var s = h('span', 'pc-kv');
    s.appendChild(document.createTextNode(label + ' '));
    s.appendChild(h('b', null, value));
    return s;
  }

  /* ---------- 排序 ---------- */

  var ASC_KEYS = { rank: 1, name: 1, menpai: 1 };

  function sorted(list) {
    var k = state.sortKey, dir = state.sortDir === 'asc' ? 1 : -1;
    return list.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      if (k === 'name' || k === 'menpai') return String(x || '').localeCompare(String(y || ''), 'zh') * dir;
      if (x === null || x === undefined) x = -Infinity;
      if (y === null || y === undefined) y = -Infinity;
      if (x === y) return a.rank - b.rank;   // 同值时按原始名次兜底
      return (x - y) * dir;
    });
  }

  function syncSortButtons() {
    if (!el.sortbar) return;
    Array.prototype.forEach.call(el.sortbar.querySelectorAll('[data-sort]'), function (b) {
      b.setAttribute('aria-pressed', b.dataset.sort === state.sortKey ? 'true' : 'false');
    });
  }

  function syncSortState() {
    if (!el.tbl || !el.tbl.querySelectorAll) return;
    Array.prototype.forEach.call(el.tbl.querySelectorAll('th[data-key]'), function (th) {
      if (th.dataset.key === state.sortKey) {
        th.setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
      } else {
        th.removeAttribute('aria-sort');
      }
    });
  }

  function pickSort(k) {
    if (state.sortKey === k) {
      state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      state.sortKey = k;
      // 名次越小越靠前，等级 / 阅历从高到低
      state.sortDir = ASC_KEYS[k] ? 'asc' : 'desc';
    }
    syncSortButtons();
    render();
  }

  function bindSortbar() {
    if (!el.sortbar) return;
    Array.prototype.forEach.call(el.sortbar.querySelectorAll('[data-sort]'), function (b) {
      b.addEventListener('click', function () { pickSort(b.dataset.sort); });
    });
    if (el.tbl && el.tbl.querySelectorAll) {
      Array.prototype.forEach.call(el.tbl.querySelectorAll('th[data-key]'), function (th) {
        th.addEventListener('click', function () { pickSort(th.dataset.key); });
      });
    }
  }

  /* ---------- 渲染 ---------- */

  /* 移动端卡片：名次 + 昵称 + 门派，次行等级 / 阅历 */
  function renderCards(list) {
    if (!el.cards) return;
    el.cards.textContent = '';
    var frag = document.createDocumentFragment();

    list.forEach(function (r) {
      var isMe = state.me && String(r.userid) === String(state.me);
      var card = h('article', 'pcard' + (r.rank <= 3 ? ' rk' + r.rank : '') + (isMe ? ' me' : ''));

      var left = h('div', 'pc-l');
      left.appendChild(h('span', 'rank' + (r.rank <= 3 ? ' r' + r.rank : ''), String(r.rank)));
      card.appendChild(left);

      var body = h('div', 'pc-body');
      var top = h('div', 'pc-top');
      var btn = h('button', 'nm-btn');
      btn.type = 'button';
      btn.setAttribute('aria-label', '查看 ' + (r.name || '该玩家') + ' 的档案');
      btn.appendChild(h('span', null, r.name || '—'));
      btn.appendChild(h('span', 'arw', '›'));
      btn.addEventListener('click', function (e) {
        if (e && e.stopPropagation) e.stopPropagation();
        openProfile(r);
      });
      top.appendChild(btn);
      if (isMe) top.appendChild(h('span', 'badge-me', '我'));
      if (r.menpai) top.appendChild(h('span', 'school', r.menpai));
      body.appendChild(top);

      var sub = h('div', 'pc-sub');
      if (r.lv != null && r.lv !== '') sub.appendChild(kv('等级', String(r.lv)));
      sub.appendChild(kv('江湖阅历', fmtYueli(r.yueli)));
      body.appendChild(sub);

      card.appendChild(body);
      card.addEventListener('click', function () { openProfile(r); });
      frag.appendChild(card);
    });

    el.cards.appendChild(frag);
  }

  function render() {
    var list = sorted(state.rows);
    if (el.empty) {
      el.empty.hidden = list.length > 0;
      if (!list.length) el.empty.textContent = '暂无名人堂数据。';
    }
    if (el.count) el.count.textContent = list.length + ' 人';
    syncSortState();
    syncSortButtons();

    if (isMobile()) {
      el.tbody.textContent = '';
      renderCards(list);
      return;
    }
    if (el.cards) el.cards.textContent = '';
    el.tbody.textContent = '';   // 表格分支必须清空，否则排序是追加而不是替换

    var frag = document.createDocumentFragment();
    list.forEach(function (r) {
      var tr = document.createElement('tr');
      var rowCls = [];
      if (state.me && String(r.userid) === String(state.me)) rowCls.push('me');
      if (r.rank <= 3) rowCls.push('rk' + r.rank);
      if (rowCls.length) tr.className = rowCls.join(' ');

      var tdRank = h('td', 'c-rank');
      tdRank.appendChild(h('span', 'rank' + (r.rank <= 3 ? ' r' + r.rank : ''), String(r.rank)));
      tr.appendChild(tdRank);

      var tdName = h('td', 'c-name');
      var wrap = h('div', 'name');
      var nm = h('span', 'nm');
      var btn = h('button', 'nm-btn');
      btn.type = 'button';
      btn.setAttribute('aria-label', '查看 ' + (r.name || '该玩家') + ' 的档案');
      btn.appendChild(h('span', null, r.name || '—'));
      btn.appendChild(h('span', 'arw', '›'));
      btn.addEventListener('click', function (e) {
        if (e && e.stopPropagation) e.stopPropagation();
        openProfile(r);
      });
      nm.appendChild(btn);
      if (state.me && String(r.userid) === String(state.me)) nm.appendChild(h('span', 'badge-me', '我'));
      if (r.menpai) nm.appendChild(h('span', 'school-inline', r.menpai));
      wrap.appendChild(nm);
      tdName.appendChild(wrap);
      tr.appendChild(tdName);

      tr.appendChild(h('td', 'c-school', r.menpai || '—'));
      tr.appendChild(h('td', 'c-lv num', (r.lv != null && r.lv !== '') ? String(r.lv) : '—'));
      tr.appendChild(h('td', 'c-yueli num', fmtYueli(r.yueli)));

      tr.addEventListener('click', function () { openProfile(r); });
      frag.appendChild(tr);
    });
    el.tbody.appendChild(frag);
  }

  /* ---------- 档案弹窗（精简自 assets/app.js 的 openProfile） ---------- */

  var pf = document.getElementById('pf');
  var pfBody = document.getElementById('pf-body');
  var pfName = document.getElementById('pf-name');
  var pfSub = document.getElementById('pf-sub');
  var pfClose = document.getElementById('pf-close');

  function urlFor(uid) {
    var q = [];
    if (window.FZJH && FZJH.key) q.push('s=' + encodeURIComponent(FZJH.key));
    if (state.me) q.push('me=' + encodeURIComponent(state.me));
    if (uid) q.push('uid=' + encodeURIComponent(uid));
    return location.pathname + (q.length ? '?' + q.join('&') : '');
  }

  // 档案会话缓存：同一次浏览里反复点同一个玩家不再重复下载（单份约 16 KB）
  var PF_CACHE = Object.create(null);
  var PF_SEQ = 0;   // 连点两个人时用来丢弃上一个迟到的渲染回调

  // 经验快照按分区缓存，失败静默跳过，不能把档案一起打挂
  var EXP_CACHE = Object.create(null);
  var EXP_PENDING = Object.create(null);

  function loadSnapshots(b, uid, done) {
    var url = b + 'exp-history.json';
    var hit = EXP_CACHE[url];
    if (hit) { done(hit); return; }
    if (EXP_PENDING[url]) { EXP_PENDING[url].push(done); return; }
    EXP_PENDING[url] = [done];
    var finish = function (snaps) {
      EXP_CACHE[url] = snaps;
      var q = EXP_PENDING[url] || [];
      delete EXP_PENDING[url];
      q.forEach(function (fn) { fn(snaps); });
    };
    fetch(url, { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) { finish((d && d.snapshots) || []); })
      .catch(function () { finish([]); });
  }

  function openProfile(row) {
    if (!pf || !pfBody) return;
    var uid = String(row.userid);
    var seq = ++PF_SEQ;
    pfName.textContent = row.name || '—';
    pfSub.textContent = '第 ' + row.rank + ' 名 · ' + (row.menpai || '—') + ' · UID ' + row.userid;
    pfBody.textContent = '';
    pfBody.appendChild(h('p', 'pf-loading', '正在读取档案…'));

    if (typeof pf.showModal === 'function') {
      if (!pf.open) pf.showModal();
    } else {
      pf.setAttribute('open', '');
    }

    if (history && history.replaceState) history.replaceState(null, '', urlFor(row.userid));

    var b = base();
    var cacheKey = b + 'profiles/' + row.userid + '.json';

    var snaps = null;
    var rendered = false;

    var mountSnaps = function () {
      if (!rendered || !snaps || seq !== PF_SEQ) return;
      if (window.FZJH && FZJH.appendSnapshots) FZJH.appendSnapshots(pfBody, snaps, uid);
    };

    loadSnapshots(b, uid, function (list) {
      snaps = list;
      mountSnaps();
    });

    var showProfile = function (p) {
      if (seq !== PF_SEQ) return;
      if (window.FZJH && FZJH.renderProfile) FZJH.renderProfile(pfBody, p);
      rendered = true;
      mountSnaps();
    };

    var hit = PF_CACHE[cacheKey];
    if (hit) { showProfile(hit); return; }
    fetch(cacheKey, { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (p) {
        PF_CACHE[cacheKey] = p;
        showProfile(p);
      })
      .catch(function (e) {
        if (seq !== PF_SEQ) return;
        pfBody.textContent = '';
        pfBody.appendChild(h('p', 'pf-err', '读取失败：' + e.message + '。该玩家可能未抓到详情，或详情文件还没生成。'));
      });
  }

  function closeProfile() {
    if (!pf) return;
    if (typeof pf.close === 'function') pf.close();
    else pf.removeAttribute('open');
    if (history && history.replaceState) history.replaceState(null, '', urlFor(null));
  }

  if (pfClose) pfClose.addEventListener('click', closeProfile);

  // 点遮罩关闭（点内容区不关）
  if (pf) {
    pf.addEventListener('click', function (e) { if (e.target === pf) closeProfile(); });
    pf.addEventListener('close', function () {
      if (new URLSearchParams(location.search).get('uid') && history && history.replaceState) {
        history.replaceState(null, '', urlFor(null));
      }
    });
  }

  /* ---------- 启动 ---------- */

  function fail(msg) {
    if (el.updated) el.updated.textContent = '数据加载失败';
    if (el.count) el.count.hidden = true;
    if (el.empty) {
      el.empty.hidden = false;
      el.empty.textContent = msg;
    }
  }

  function boot() {
    state.me = (window.FZJH && FZJH.shadowMode) ? '' : (state.me || '');
    fetch(dataUrl(), { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('榜单 HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        state.rows = (d.rows || []).slice();
        // 名次缺失就按行序补，避免出现「NaN」
        state.rows.forEach(function (r, i) { if (!r.rank) r.rank = i + 1; });
        if (el.updated) {
          el.updated.textContent = d.updatedAt || '更新时间未知';
          el.updated.title = '数据时间：' + (d.updatedAt || '未知');
        }
        render();

        // 支持 ?uid=123 直接打开某人档案
        var uidParam = new URLSearchParams(location.search).get('uid');
        if (uidParam) {
          for (var i = 0; i < state.rows.length; i++) {
            if (String(state.rows[i].userid) === uidParam) { openProfile(state.rows[i]); break; }
          }
        }
      })
      .catch(function (e) { fail('读取失败：' + e.message); });
  }

  bindSortbar();

  if (window.FZJH && FZJH.init) FZJH.init(boot);
  else boot();

  // 跨过 560px 断点时切换「表格 / 卡片」两套渲染
  var onMQ = function () { render(); };
  if (mqMobile.addEventListener) mqMobile.addEventListener('change', onMQ);
  else if (mqMobile.addListener) mqMobile.addListener(onMQ);
})();
