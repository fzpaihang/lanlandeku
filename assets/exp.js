/* 放置江湖 · 经验变化（复用 style.css） */
(function () {
  'use strict';

  function base() { return (window.FZJH && FZJH.base) ? FZJH.base : './data/servers/taptap/'; }
  function boardUrl() { return base() + 'gaoshoubang.json'; }
  function histUrl() { return base() + 'exp-history.json'; }
  var WINDOW_DAYS = 3;

  var state = { rows: [], sortKey: 'grow', sortDir: 'desc', me: new URLSearchParams(location.search).get('me') || '' };

  var el = {
    tbody: document.getElementById('tbody'),
    cards: document.getElementById('cards'),
    count: document.getElementById('count'),
    spanInfo: document.getElementById('span-info'),
    banner: document.getElementById('banner'),
    empty: document.getElementById('empty'),
    tbl: document.getElementById('tbl'),
    sortbar: document.getElementById('sortbar')
  };

  var mqMobile = window.matchMedia('(max-width: 560px)');
  var isMobile = function () { return mqMobile.matches; };

  // 跳回高手榜并直接打开档案：分区和高亮（me）都不能丢
  function linkFor(uid) {
    var q = ['uid=' + encodeURIComponent(uid)];
    if (window.FZJH && FZJH.key) q.push('s=' + encodeURIComponent(FZJH.key));
    if (state.me) q.push('me=' + encodeURIComponent(state.me));
    return './index.html?' + q.join('&');
  }

  function fmtBig(n) {
    if (n === null || n === undefined || n === '') return '—';
    n = Number(n);
    if (!isFinite(n)) return '—';
    var a = Math.abs(n);
    if (a >= 1e8) return (n / 1e8).toFixed(2) + '亿';
    if (a >= 1e4) return (n / 1e4).toFixed(1) + '万';
    return String(Math.round(n));
  }

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  /* 经验差值统一先取整再判断符号：
     历史快照是榜单浮点值、新快照是档案整数，相减会留 0.x 尾数，
     直接用原始值判断符号就会出现「+0」「-0.00%」这类假变化。 */
  function growText(g) {
    if (g === null) return '—';
    var v = Math.round(g);
    if (v === 0) return '0';
    return (v > 0 ? '+' : '') + fmtBig(v);
  }

  function growCls(g) {
    if (g === null) return 'flat';
    var v = Math.round(g);
    return v > 0 ? 'up' : (v < 0 ? 'down' : 'flat');
  }

  function pctText(p) {
    if (p === null) return '—';
    var v = Number(p.toFixed(2));
    if (v === 0) return '0.00%';
    return (v > 0 ? '+' : '') + v.toFixed(2) + '%';
  }

  function dayText(p) {
    if (p === null) return '—';
    var v = Math.round(p);
    if (v === 0) return '0';
    return (v > 0 ? '+' : '') + fmtBig(v);
  }

  function sorted(list) {
    var k = state.sortKey, dir = state.sortDir === 'asc' ? 1 : -1;
    return list.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      if (k === 'name' || k === 'menpai') return String(x || '').localeCompare(String(y || ''), 'zh') * dir;
      if (x === null || x === undefined) x = -Infinity;
      if (y === null || y === undefined) y = -Infinity;
      if (x === y) return a.rank - b.rank;
      return (x - y) * dir;
    });
  }

  /* 移动端卡片：主行 名次+侠名+门派，次行 经验·日均，右侧 区间增长+增幅 */
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
      var a = document.createElement('a');
      a.className = 'nm-link';
      a.href = linkFor(r.userid);
      a.textContent = r.name || '—';
      top.appendChild(a);
      if (isMe) top.appendChild(h('span', 'badge-me', '我'));
      if (r.menpai) top.appendChild(h('span', 'school', r.menpai));
      body.appendChild(top);

      var sub = h('div', 'pc-sub');
      sub.appendChild(kv('经验', fmtBig(r.expN)));
      if (r.perDay !== null) sub.appendChild(kv('日均', '+' + fmtBig(r.perDay)));
      body.appendChild(sub);

      card.appendChild(body);

      // 右侧：区间增长为主，增幅为辅
      var right = h('div', 'pc-r');
      right.appendChild(h('span', 'grow ' + growCls(r.grow), growText(r.grow)));
      right.appendChild(h('span', 'pc-pct', pctText(r.pct)));
      card.appendChild(right);

      frag.appendChild(card);
    });

    el.cards.appendChild(frag);
  }

  function kv(label, value) {
    var s = h('span', 'pc-kv');
    s.appendChild(document.createTextNode(label + ' '));
    s.appendChild(h('b', null, value));
    return s;
  }

  /* 移动端没有表头，排序只能靠这条胶囊；桌面用表头，CSS 里把这条隐藏掉 */
  function syncSortButtons() {
    if (!el.sortbar) return;
    Array.prototype.forEach.call(el.sortbar.querySelectorAll('[data-sort]'), function (b) {
      b.setAttribute('aria-pressed', b.dataset.sort === state.sortKey ? 'true' : 'false');
    });
  }

  function bindSortbar() {
    if (!el.sortbar) return;
    Array.prototype.forEach.call(el.sortbar.querySelectorAll('[data-sort]'), function (b) {
      b.addEventListener('click', function () {
        var k = b.dataset.sort;
        if (state.sortKey === k) {
          state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          state.sortKey = k;
          // 名次越小越靠前，数值类默认从高到低
          state.sortDir = (k === 'rank') ? 'asc' : 'desc';
        }
        syncSortButtons();
        render();
      });
    });
  }

  function render() {
    var list = sorted(state.rows);
    el.empty.hidden = list.length > 0;
    el.count.textContent = list.length + ' 人';
    syncSortState();
    syncSortButtons();

    if (isMobile()) {
      el.tbody.textContent = '';
      renderCards(list);
      return;
    }
    if (el.cards) el.cards.textContent = '';
    el.tbody.textContent = '';   // 表格分支必须清空，否则每次排序都是追加而不是替换

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
      var a = document.createElement('a');
      a.className = 'nm-link';
      a.href = linkFor(r.userid);
      a.textContent = r.name || '—';
      nm.appendChild(a);
      if (state.me && String(r.userid) === String(state.me)) nm.appendChild(h('span', 'badge-me', '我'));
      if (r.menpai) nm.appendChild(h('span', 'school-inline', r.menpai));
      wrap.appendChild(nm);
      tdName.appendChild(wrap);
      tr.appendChild(tdName);

      var tdS = h('td', 'c-school');
      tdS.appendChild(h('span', 'school', r.menpai || '—'));
      tr.appendChild(tdS);

      tr.appendChild(h('td', 'c-exp num', fmtBig(r.expN)));

      var tdG = h('td', 'c-grow num');
      tdG.appendChild(h('span', 'grow ' + growCls(r.grow), growText(r.grow)));
      tr.appendChild(tdG);

      tr.appendChild(h('td', 'c-day num', dayText(r.perDay)));
      tr.appendChild(h('td', 'c-pct num', pctText(r.pct)));

      frag.appendChild(tr);
    });
    el.tbody.appendChild(frag);
  }

  /* 表头 aria-sort 跟随排序；移动端只渲染卡片，但表头状态也要同步 */
  function syncSortState() {
    Array.prototype.forEach.call(el.tbl.querySelectorAll('th[data-key]'), function (th) {
      if (th.dataset.key === state.sortKey) {
        th.setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
      } else {
        th.removeAttribute('aria-sort');
      }
    });
  }

  function fail(msg) {
    el.spanInfo.textContent = '读取失败';
    el.empty.hidden = false;
    el.empty.textContent = msg;
    el.count.hidden = true;
  }

  function boot() {
    Promise.all([
      fetch(boardUrl(), { cache: 'no-cache' }).then(function (r) {
        if (!r.ok) throw new Error('榜单 HTTP ' + r.status);
        return r.json();
      }),
      fetch(histUrl(), { cache: 'no-cache' }).then(function (r) {
        if (!r.ok) throw new Error('快照 HTTP ' + r.status);
        return r.json();
      })
    ]).then(function (res) {
      var board = res[0], hist = res[1];
      var snaps = (hist.snapshots || []).slice().sort(function (a, b) { return a.ts - b.ts; });

      if (snaps.length < 2) {
        el.banner.hidden = false;
        el.banner.textContent = '目前只记录了 1 次快照（' + (snaps[0] ? snaps[0].date + ' ' + snaps[0].time : '—') +
          '）。经验要玩家领取后才变动，不是实时数值，攒到第二天再来这里看才有意义。';
      }

      var latest = snaps[snaps.length - 1] || null;
      var baseSnap = null, days = 0;

      // 取 3 天前最近的那条快照当基准；不够 3 天就退回最早一条
      if (latest) {
        var cutoff = latest.ts - WINDOW_DAYS * 86400;
        for (var i = snaps.length - 1; i >= 0; i--) {
          if (snaps[i].ts <= cutoff) { baseSnap = snaps[i]; break; }
        }
        if (!baseSnap) baseSnap = snaps[0];
        if (baseSnap.ts === latest.ts) baseSnap = null;
      }

      if (baseSnap && latest) {
        days = (latest.ts - baseSnap.ts) / 86400;
        var span = days >= 1 ? days.toFixed(1) + ' 天' : Math.max(1, Math.round(days * 24)) + ' 小时';
        el.spanInfo.textContent = baseSnap.date.slice(5) + ' ' + baseSnap.time + ' → ' +
          latest.date.slice(5) + ' ' + latest.time + ' · ' + span;

        // 经验不是实时值：玩家领取后才跳一次，短区间对比多半全是 0
        if (days < WINDOW_DAYS && snaps.length >= 2) {
          el.banner.hidden = false;
          el.banner.textContent = '当前对比区间只有 ' + span + '，累计不足 ' + WINDOW_DAYS +
            ' 天，日均暂不显示。经验要玩家领取后才变动，短区间看不出趋势——攒满 ' + WINDOW_DAYS +
            ' 天后会自动出现日均（区间增长 ÷ ' + WINDOW_DAYS + '）。';
        }
      } else {
        el.spanInfo.textContent = '暂无对比数据';
      }

      state.rows = (board.rows || []).map(function (r) {
        var uid = String(r.userid);
        var curExp = r.exp;
        var baseExp = baseSnap && baseSnap.exp ? baseSnap.exp[uid] : undefined;
        var grow = null, perDay = null, pct = null;

        if (baseSnap && curExp != null && baseExp != null) {
          grow = Math.round(curExp - baseExp);
          // 日均按固定 3 天窗口归一（区间增长 ÷ 3）；不足 3 天不显示，避免短区间线性外推夸大
          perDay = days >= WINDOW_DAYS ? grow / WINDOW_DAYS : null;
          pct = baseExp > 0 ? (grow / baseExp) * 100 : null;
        }

        return {
          userid: r.userid, rank: r.rank, name: r.name, menpai: r.menpai,
          expN: curExp == null ? null : Math.round(curExp),
          grow: grow, perDay: perDay, pct: pct
        };
      });

      render();
    }).catch(function (e) {
      fail('读取失败：' + e.message);
    });
  }

  bindSortbar();

  if (window.FZJH && FZJH.init) FZJH.init(boot);
  else boot();

  // 跨过 560px 断点时切换「表格 / 卡片」两套渲染
  var onMQ = function () { render(); };
  if (mqMobile.addEventListener) mqMobile.addEventListener('change', onMQ);
  else if (mqMobile.addListener) mqMobile.addListener(onMQ);

  Array.prototype.forEach.call(document.querySelectorAll('th[data-key]'), function (th) {
    th.addEventListener('click', function () {
      var k = th.dataset.key;
      if (state.sortKey === k) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortKey = k;
        state.sortDir = (k === 'name' || k === 'menpai' || k === 'rank') ? 'asc' : 'desc';
      }
      render();
    });
  });
})();
