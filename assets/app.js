/* 放置江湖 · 高手榜 —— 纯静态，无依赖 */
(function () {
  'use strict';

  var DATA_URL = './data/gaoshoubang.json';
  var state = {
    rows: [],
    q: '',
    school: '',
    sortKey: 'rank',
    sortDir: 'asc',
    hasPrev: false,
    me: new URLSearchParams(location.search).get('me') || ''
  };

  var el = {
    tbody: document.getElementById('tbody'),
    q: document.getElementById('q'),
    clear: document.getElementById('clear'),
    chips: document.getElementById('chips'),
    updated: document.getElementById('updated'),
    count: document.getElementById('count'),
    empty: document.getElementById('empty'),
    tbl: document.getElementById('tbl')
  };

  /* ---------- 工具 ---------- */

  function fmtBig(n) {
    if (n === null || n === undefined || n === '') return '—';
    n = Number(n);
    if (!isFinite(n)) return '—';
    var a = Math.abs(n);
    if (a >= 1e8) return (n / 1e8).toFixed(2) + '亿';
    if (a >= 1e4) return (n / 1e4).toFixed(1) + '万';
    return String(Math.round(n));
  }

  function fmtInt(n) {
    if (n === null || n === undefined || n === '') return '—';
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function relTime(ts) {
    if (!ts) return '';
    var d = Math.floor(Date.now() / 1000 - ts);
    if (d < 60) return '刚刚更新';
    if (d < 3600) return Math.floor(d / 60) + ' 分钟前更新';
    if (d < 86400) return Math.floor(d / 3600) + ' 小时前更新';
    return Math.floor(d / 86400) + ' 天前更新';
  }

  // 「2026-11-10」→ 今天 / 昨天 / 3 天前 / 11-01
  function agoLabel(date) {
    if (!date) return '';
    var parts = String(date).split('-');
    if (parts.length !== 3) return date;
    var then = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var days = Math.round((today - then) / 86400000);
    if (days <= 0) return '今天';
    if (days === 1) return '昨天';
    if (days < 30) return days + ' 天前';
    return parts[1] + '-' + parts[2];
  }

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  /* ---------- 渲染 ---------- */

  function matches(r) {
    if (state.school && r.menpai !== state.school) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase();
    return (
      (r.name || '').toLowerCase().indexOf(q) >= 0 ||
      String(r.userid || '').indexOf(q) >= 0 ||
      (r.menpai || '').toLowerCase().indexOf(q) >= 0
    );
  }

  function sorted(list) {
    var k = state.sortKey, dir = state.sortDir === 'asc' ? 1 : -1;
    var out = list.slice();
    out.sort(function (a, b) {
      var x = a[k], y = b[k];
      if (k === 'name' || k === 'menpai') {
        return String(x || '').localeCompare(String(y || ''), 'zh') * dir;
      }
      if (x === null || x === undefined) x = -Infinity;
      if (y === null || y === undefined) y = -Infinity;
      if (x === y) return a.rank - b.rank;
      return (x - y) * dir;
    });
    return out;
  }

  function render() {
    var list = sorted(state.rows.filter(matches));
    el.tbody.textContent = '';
    el.empty.hidden = list.length > 0;

    var frag = document.createDocumentFragment();
    list.forEach(function (r) {
      var tr = document.createElement('tr');
      if (state.me && String(r.userid) === String(state.me)) tr.className = 'me';

      // 名次
      var tdRank = h('td', 'c-rank');
      var rk = h('span', 'rank' + (r.rank <= 3 ? ' r' + r.rank : ''), String(r.rank));
      tdRank.appendChild(rk);
      if (state.hasPrev && r.delta !== null && r.delta !== undefined && r.delta !== 0) {
        tdRank.appendChild(h('span', 'delta ' + (r.delta > 0 ? 'up' : 'down'),
          (r.delta > 0 ? '▲' : '▼') + Math.abs(r.delta)));
      } else if (state.hasPrev && r.delta === null) {
        tdRank.appendChild(h('span', 'delta new', 'NEW'));
      }
      tr.appendChild(tdRank);

      // 昵称
      var tdName = h('td', 'c-name');
      var wrap = h('div', 'name');
      var nm = h('span', 'nm');
      var btn = h('button', 'nm-btn');
      btn.type = 'button';
      btn.setAttribute('aria-label', '查看 ' + (r.name || '该玩家') + ' 的详细信息');
      btn.appendChild(h('span', null, r.name || '—'));
      btn.appendChild(h('span', 'arw', '›'));
      btn.addEventListener('click', function () { openProfile(r); });
      nm.appendChild(btn);
      if (state.me && String(r.userid) === String(state.me)) nm.appendChild(h('span', 'badge-me', '我'));
      if (r.menpai) nm.appendChild(h('span', 'school-inline', r.menpai));
      wrap.appendChild(nm);
      wrap.appendChild(h('span', 'uid', '#' + r.userid));
      tdName.appendChild(wrap);
      tr.appendChild(tdName);

      // 门派
      var tdS = h('td', 'c-school');
      tdS.appendChild(h('span', 'school', r.menpai || '—'));
      tr.appendChild(tdS);

      // 等级
      tr.appendChild(h('td', 'c-lv num', r.lv != null ? String(r.lv) : '—'));

      // 经验
      tr.appendChild(h('td', 'c-exp num', fmtBig(r.exp)));

      // 福缘
      tr.appendChild(h('td', 'c-luck num hide-sm', r.fuyuan != null ? String(r.fuyuan) : '—'));

      // 容貌
      tr.appendChild(h('td', 'c-looks num hide-md', fmtInt(r.looks)));

      // 年龄
      tr.appendChild(h('td', 'c-age num hide-md', r.age != null ? r.age + ' 岁' : '—'));

      frag.appendChild(tr);
    });
    el.tbody.appendChild(frag);

    el.count.textContent = list.length + ' / ' + state.rows.length + ' 人';

    Array.prototype.forEach.call(el.tbl.querySelectorAll('th[data-key]'), function (th) {
      if (th.dataset.key === state.sortKey) {
        th.setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
      } else {
        th.removeAttribute('aria-sort');
      }
    });
  }

  /* ---------- 门派筛选 ---------- */

  function buildChips() {
    var cnt = {};
    state.rows.forEach(function (r) {
      var s = r.menpai || '未知';
      cnt[s] = (cnt[s] || 0) + 1;
    });
    var top = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; }).slice(0, 8);

    el.chips.textContent = '';
    var all = h('button', 'chip', '全部');
    all.type = 'button';
    all.setAttribute('aria-pressed', 'true');
    all.addEventListener('click', function () { selectSchool(''); });
    el.chips.appendChild(all);

    top.forEach(function (s) {
      var b = h('button', 'chip', s + ' ' + cnt[s]);
      b.type = 'button';
      b.dataset.school = s;
      b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', function () { selectSchool(s); });
      el.chips.appendChild(b);
    });
  }

  function selectSchool(s) {
    state.school = s;
    Array.prototype.forEach.call(el.chips.children, function (c) {
      var on = s ? c.dataset.school === s : !c.dataset.school;
      c.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    render();
  }

  /* ---------- 事件 ---------- */

  el.q.addEventListener('input', function () {
    state.q = el.q.value.trim();
    el.clear.hidden = !state.q;
    render();
  });

  el.clear.addEventListener('click', function () {
    el.q.value = '';
    state.q = '';
    el.clear.hidden = true;
    el.q.focus();
    render();
  });

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

  /* ---------- 玩家详情弹窗 ---------- */

  var pf = document.getElementById('pf');
  var pfBody = document.getElementById('pf-body');
  var pfName = document.getElementById('pf-name');
  var pfSub = document.getElementById('pf-sub');
  var pfClose = document.getElementById('pf-close');

  function cell(dt, dd) {
    var d = h('dl', 'pf-cell');
    d.appendChild(h('dt', null, dt));
    d.appendChild(h('dd', null, dd === null || dd === undefined || dd === '' ? '—' : String(dd)));
    return d;
  }

  function section(title) {
    var s = h('section', 'pf-sec');
    s.appendChild(h('h3', null, title));
    return s;
  }

  function renderProfile(p, row) {
    pfBody.textContent = '';

    // 概览
    var grid = h('div', 'pf-grid');
    grid.appendChild(cell('等级', p.lv));
    grid.appendChild(cell('门派', p.menpai));
    grid.appendChild(cell('性别', p.sex));
    grid.appendChild(cell('年龄', p.age != null ? p.age + ' 岁' : null));
    grid.appendChild(cell('容貌', fmtInt(p.looks)));
    grid.appendChild(cell('福缘', p.fuyuan));
    grid.appendChild(cell('传承', p.inheritCount != null ? p.inheritCount + ' 次' : null));
    grid.appendChild(cell('武学造诣', p.kongfu != null ? Number(p.kongfu).toFixed(2) : null));
    grid.appendChild(cell('经验', fmtBig(p.exp)));
    var qiTxt = null;
    if (p.qi != null) {
      qiTxt = fmtBig(p.qi);
      if (p.qiMax != null && Math.abs(p.qiMax - p.qi) > 1) qiTxt += '/' + fmtBig(p.qiMax);
    }
    grid.appendChild(cell('气血', qiTxt));
    grid.appendChild(cell('加力', p.jiaLi));
    grid.appendChild(cell('正气', fmtBig(p.zhengqi)));
    pfBody.appendChild(grid);

    // 准备位
    var prepKeys = Object.keys(p.prepared || {});
    if (prepKeys.length) {
      var s1 = section('准备位 ' + prepKeys.length + ' 个');
      var tags = h('div', 'pf-tags');
      prepKeys.forEach(function (k) {
        var t = h('span', 'pf-tag key');
        t.appendChild(h('span', null, k));
        t.appendChild(h('b', null, p.prepared[k]));
        tags.appendChild(t);
      });
      s1.appendChild(tags);
      pfBody.appendChild(s1);
    }

    // 近期新增武学（30 天内）
    var news = p.newSkills || [];
    if (news.length) {
      var s0 = section('近期新增 ' + news.length + ' 门');
      var nt = h('div', 'pf-tags');
      news.forEach(function (e) {
        var t = h('span', 'pf-tag new');
        t.appendChild(h('b', null, e.n));
        t.appendChild(h('span', null, agoLabel(e.date)));
        nt.appendChild(t);
      });
      s0.appendChild(nt);
      pfBody.appendChild(s0);
    }

    // 武学
    var list = p.skills || [];
    if (list.length) {
      var s2 = section('武学 ' + list.length + ' 门');
      s2.appendChild(skillList(list, 12));
      pfBody.appendChild(s2);
    }

    // 装备
    if ((p.equips || []).length) {
      var s3 = section('装备 ' + p.equips.length + ' 件');
      var et = h('div', 'pf-tags');
      p.equips.forEach(function (e) {
        var unknown = e.known === false;
        var t = h('span', 'pf-tag' + (unknown ? ' unknown' : ''));
        t.appendChild(h('span', null, e.slot));
        var b = h('b', null, unknown ? '未知' : e.n);
        if (unknown && e.raw) b.title = '原始 id：' + e.raw;
        t.appendChild(b);
        et.appendChild(t);
      });
      s3.appendChild(et);
      pfBody.appendChild(s3);
    }
  }

  function skillList(list, limit) {
    var wrap = document.createElement('div');
    var shown = list.slice(0, limit);
    var query = '';

    // 搜索框
    var box = h('div', 'pf-search');
    var input = document.createElement('input');
    input.type = 'search';
    input.className = 'pf-search-input';
    input.placeholder = '搜索武学名称';
    input.setAttribute('aria-label', '搜索该玩家的武学');
    input.setAttribute('enterkeyhint', 'search');
    input.autocomplete = 'off';
    box.appendChild(input);

    var count = h('span', 'pf-count');
    count.setAttribute('role', 'status');
    count.setAttribute('aria-live', 'polite');
    box.appendChild(count);
    wrap.appendChild(box);

    // 列表容器（只重绘这里，保证输入框不丢焦点）
    var host = document.createElement('div');
    wrap.appendChild(host);

    function renderList(rows, truncated) {
      host.textContent = '';
      var ul = h('ul', 'pf-list');
      rows.forEach(function (s) {
        var li = document.createElement('li');
        li.appendChild(h('span', null, s.n));
        li.appendChild(h('span', 'lv', s.lv + ' 级'));
        ul.appendChild(li);
      });
      host.appendChild(ul);

      if (truncated) {
        var b = h('button', 'pf-more', '展开全部 ' + list.length + ' 门');
        b.type = 'button';
        b.addEventListener('click', function () {
          shown = list.slice();
          paint();
        });
        host.appendChild(b);
      }
    }

    function paint() {
      var q = query.trim().toLowerCase();

      if (q) {
        var hit = list.filter(function (s) {
          return (s.n || '').toLowerCase().indexOf(q) >= 0 ||
                 (s.id || '').toLowerCase().indexOf(q) >= 0;
        });
        count.textContent = hit.length ? '匹配 ' + hit.length + ' 门' : '';
        if (!hit.length) {
          host.textContent = '';
          host.appendChild(h('p', 'pf-none', '没有匹配「' + query.trim() + '」的武学'));
          return;
        }
        renderList(hit, false);
        return;
      }

      count.textContent = '共 ' + list.length + ' 门';
      renderList(shown, shown.length < list.length);
    }

    input.addEventListener('input', function () {
      query = input.value;
      paint();
    });

    paint();
    return wrap;
  }

  function openProfile(row) {
    pfName.textContent = row.name || '—';
    pfSub.textContent = '第 ' + row.rank + ' 名 · ' + (row.menpai || '—') + ' · UID ' + row.userid;
    pfBody.textContent = '';
    pfBody.appendChild(h('p', 'pf-loading', '正在读取档案…'));

    if (typeof pf.showModal === 'function') {
      if (!pf.open) pf.showModal();
    } else {
      pf.setAttribute('open', '');
    }

    var q = '?uid=' + encodeURIComponent(row.userid) + (state.me ? '&me=' + encodeURIComponent(state.me) : '');
    history.replaceState(null, '', location.pathname + q);

    fetch('./data/profiles/' + row.userid + '.json', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (p) { renderProfile(p, row); })
      .catch(function (e) {
        pfBody.textContent = '';
        pfBody.appendChild(h('p', 'pf-err', '读取失败：' + e.message + '。该玩家可能未抓到详情，或详情文件还没生成。'));
      });
  }

  function closeProfile() {
    if (typeof pf.close === 'function') pf.close();
    else pf.removeAttribute('open');
    var q = state.me ? '?me=' + encodeURIComponent(state.me) : '';
    history.replaceState(null, '', location.pathname + q);
  }

  pfClose.addEventListener('click', closeProfile);

  // 点遮罩关闭（点内容区不关）
  pf.addEventListener('click', function (e) {
    if (e.target === pf) closeProfile();
  });

  // Esc 关闭时也清掉地址里的 uid（原生 dialog 的 cancel 行为）
  pf.addEventListener('close', function () {
    if (new URLSearchParams(location.search).get('uid')) {
      var q = state.me ? '?me=' + encodeURIComponent(state.me) : '';
      history.replaceState(null, '', location.pathname + q);
    }
  });

  /* ---------- 启动 ---------- */

  fetch(DATA_URL, { cache: 'no-cache' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      state.rows = (d.rows || []).slice();
      state.hasPrev = !!d.hasPrev;
      state.rows.forEach(function (r) { r.rank = r.rank || 0; });
      el.updated.textContent = relTime(d.updatedTs) || ('更新于 ' + (d.updatedAt || '未知'));
      el.updated.title = '数据时间：' + (d.updatedAt || '未知');
      buildChips();
      render();

      // 支持 ?uid=123 直接打开某人档案
      var uidParam = new URLSearchParams(location.search).get('uid');
      if (uidParam) {
        var target = null;
        for (var i = 0; i < state.rows.length; i++) {
          if (String(state.rows[i].userid) === uidParam) { target = state.rows[i]; break; }
        }
        if (target) openProfile(target);
      }
    })
    .catch(function (e) {
      el.updated.textContent = '数据加载失败';
      el.count.hidden = true;
      el.empty.hidden = false;
      el.empty.textContent = '数据读取失败（' + e.message + '）。若是本地打开，请用本地服务器访问，不要直接双击 html。';
    });
})();
