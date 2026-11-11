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
    count: document.getElementById('count'),
    spanInfo: document.getElementById('span-info'),
    banner: document.getElementById('banner'),
    empty: document.getElementById('empty'),
    tbl: document.getElementById('tbl')
  };

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

  function updateScrollHint() {
    var box = document.querySelector('.scroll');
    var hint = document.getElementById('scroll-hint');
    if (!box || !hint) return;
    var overflow = box.scrollWidth - box.clientWidth > 4;
    hint.setAttribute('data-show', overflow ? '1' : '0');
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

  function render() {
    var list = sorted(state.rows);
    el.tbody.textContent = '';
    el.empty.hidden = list.length > 0;

    var frag = document.createDocumentFragment();
    list.forEach(function (r) {
      var tr = document.createElement('tr');
      if (state.me && String(r.userid) === String(state.me)) tr.className = 'me';

      var tdRank = h('td', 'c-rank');
      tdRank.appendChild(h('span', 'rank' + (r.rank <= 3 ? ' r' + r.rank : ''), String(r.rank)));
      tr.appendChild(tdRank);

      var tdName = h('td', 'c-name');
      var wrap = h('div', 'name');
      var nm = h('span', 'nm');
      var a = document.createElement('a');
      a.className = 'nm-link';
      a.href = './index.html?uid=' + encodeURIComponent(r.userid) + ((window.FZJH && FZJH.key) ? '&s=' + encodeURIComponent(FZJH.key) : '');
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
      tdG.appendChild(h('span', 'grow ' + (r.grow > 0 ? 'up' : (r.grow < 0 ? 'down' : 'flat')),
        r.grow === null ? '—' : (r.grow > 0 ? '+' : '') + fmtBig(r.grow)));
      tr.appendChild(tdG);

      tr.appendChild(h('td', 'c-day num', r.perDay === null ? '—' : '+' + fmtBig(r.perDay)));
      tr.appendChild(h('td', 'c-pct num',
        r.pct === null ? '—' : (r.pct > 0 ? '+' : '') + r.pct.toFixed(2) + '%'));

      frag.appendChild(tr);
    });
    el.tbody.appendChild(frag);

    el.count.textContent = list.length + ' 人';

    updateScrollHint();

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
    var base = null, days = 0;

    if (latest) {
      var cutoff = latest.ts - WINDOW_DAYS * 86400;
      for (var i = snaps.length - 1; i >= 0; i--) {
        if (snaps[i].ts <= cutoff) { base = snaps[i]; break; }
      }
      if (!base) base = snaps[0];
      if (base.ts === latest.ts) base = null;
    }

    if (base && latest) {
      days = (latest.ts - base.ts) / 86400;
      var span = days >= 1 ? days.toFixed(1) + ' 天' : Math.max(1, Math.round(days * 24)) + ' 小时';
      el.spanInfo.textContent = base.date.slice(5) + ' ' + base.time + ' → ' + latest.date.slice(5) + ' ' + latest.time + ' · ' + span;

      // 经验不是实时值：玩家领取后才跳一次，短区间对比多半全是 0
      if (days < 0.5 && snaps.length >= 2) {
        el.banner.hidden = false;
        el.banner.textContent = '当前对比区间只有 ' + Math.max(1, Math.round(days * 24)) +
          ' 小时。游戏经验要玩家领取后才变动，短时间的差值基本是 0，属于正常现象——建议以天为单位看（攒满 1 天以上才准）。';
      }
    } else {
      el.spanInfo.textContent = '暂无对比数据';
    }

    state.rows = (board.rows || []).map(function (r) {
      var uid = String(r.userid);
      var curExp = r.exp;
      var baseExp = base && base.exp ? base.exp[uid] : undefined;
      var grow = null, perDay = null, pct = null;

      if (base && curExp != null && baseExp != null) {
        grow = curExp - baseExp;
        // 经验要玩家领取才跳，日均至少要按天算才有意义
        perDay = days >= 1 ? grow / days : null;
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

  if (window.FZJH && FZJH.init) FZJH.init(boot);
  else boot();

  window.addEventListener('resize', updateScrollHint);

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
