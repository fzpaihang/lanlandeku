/* 放置江湖 · 高手榜 —— 纯静态，无依赖 */
(function () {
  'use strict';

  function dataUrl(){ return (window.FZJH && FZJH.base ? FZJH.base : './data/servers/taptap/') + 'gaoshoubang.json'; }
  var state = {
    rows: [],
    q: '',
    school: '',
    sortKey: 'rank',
    sortDir: 'asc',
    zhuan: '',        // 转数筛选：'' = 全部；墨羽惊鸿这类混合分区才有意义
    hasPrev: false,
    chipsAll: false,   // 门派筛选是否展开全部
    me: new URLSearchParams(location.search).get('me') || ''
  };

  var el = {
    tbody: document.getElementById('tbody'),
    cards: document.getElementById('cards'),
    q: document.getElementById('q'),
    clear: document.getElementById('clear'),
    chips: document.getElementById('chips'),
    zchips: document.getElementById('zchips'),
    updated: document.getElementById('updated'),
    count: document.getElementById('count'),
    empty: document.getElementById('empty'),
    tbl: document.getElementById('tbl')
  };

  /* 窄屏走卡片列表，其余走表格；断点与 style.css 的 560px 保持一致 */
  var mqMobile = window.matchMedia('(max-width: 560px)');
  var isMobile = function () { return mqMobile.matches; };

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

  /* 时间统一按北京时间（UTC+8）展示，避免访客在别的时区看到错的时间 */
  function bjParts(ts) {
    var d = new Date((ts + 8 * 3600) * 1000);
    return {
      y: d.getUTCFullYear(),
      m: d.getUTCMonth() + 1,
      day: d.getUTCDate(),
      hh: d.getUTCHours(),
      mm: d.getUTCMinutes()
    };
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  /* 更新时间统一显示「几月几号 几点几分」，不做今天/昨天判断，
     这样任何一天的显示格式都一致：11月11日 19:28 更新 */
  function fmtUpdated(ts, fallback) {
    if (!ts) return fallback ? ('更新于 ' + fallback) : '';
    var t = bjParts(ts);
    return t.m + '月' + t.day + '日 ' + pad2(t.hh) + ':' + pad2(t.mm) + ' 更新';
  }

  /* 表格是 table-layout:fixed + width:100%，不会横向溢出，
     所以早先的「左右滑动查看更多」提示已删除（它永远不会显示）。 */

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  /* ---------- 渲染 ---------- */

  function zhuanOf(r) { return String(Number(r.inheritCount) || 0); }

  function matches(r) {
    if (state.zhuan && zhuanOf(r) !== state.zhuan) return false;
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

  /* 移动端卡片：主行 名次+侠名+转数，次行 门派·等级·经验·福缘
     刻意不放 uid（详情里有）和武学造诣（榜单不展示该字段） */
  function renderCards(list) {
    if (!el.cards) return;
    el.cards.textContent = '';
    var frag = document.createDocumentFragment();

    list.forEach(function (r) {
      var isMe = state.me && String(r.userid) === String(state.me);
      var cls = 'pcard' + (r.rank <= 3 ? ' rk' + r.rank : '') + (isMe ? ' me' : '');
      var card = h('article', cls);

      // 左列：名次 + 涨跌 / NEW
      var left = h('div', 'pc-l');
      left.appendChild(h('span', 'rank' + (r.rank <= 3 ? ' r' + r.rank : ''), String(r.rank)));
      if (state.hasPrev && r.delta !== null && r.delta !== undefined && r.delta !== 0) {
        left.appendChild(h('span', 'delta ' + (r.delta > 0 ? 'up' : 'down'),
          (r.delta > 0 ? '▲' : '▼') + Math.abs(r.delta)));
      } else if (state.hasPrev && r.delta === null) {
        left.appendChild(h('span', 'delta new', 'NEW'));
      }
      card.appendChild(left);

      var body = h('div', 'pc-body');

      // 主行：侠名 + 我 + 转数
      var top = h('div', 'pc-top');
      var btn = h('button', 'nm-btn');
      btn.type = 'button';
      btn.setAttribute('aria-label', '查看 ' + (r.name || '该玩家') + ' 的详细信息');
      btn.appendChild(h('span', null, r.name || '—'));
      btn.appendChild(h('span', 'arw', '›'));
      btn.addEventListener('click', function () { openProfile(r); });
      top.appendChild(btn);
      if (isMe) top.appendChild(h('span', 'badge-me', '我'));
      if (r.inheritCount !== null && r.inheritCount !== undefined) {
        var z = Number(r.inheritCount) || 0;
        top.appendChild(h('span', 'zhuan' + (z >= 4 ? ' hi' : ''), z + '转'));
      }
      body.appendChild(top);

      // 次行：门派 · 等级 · 经验 · 福缘
      var sub = h('div', 'pc-sub');
      if (r.menpai) sub.appendChild(h('span', 'school', r.menpai));
      if (r.lv != null) sub.appendChild(kv('等级', String(r.lv)));
      sub.appendChild(kv('经验', fmtBig(r.exp)));
      if (r.fuyuan != null) sub.appendChild(kv('福缘', String(r.fuyuan)));
      body.appendChild(sub);

      card.appendChild(body);
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

  function render() {
    var list = sorted(state.rows.filter(matches));
    el.empty.hidden = list.length > 0;
    el.count.textContent = list.length + ' / ' + state.rows.length + ' 人';
    syncSortState();

    // 窄屏：表格整体不参与渲染，直接出卡片
    if (isMobile()) {
      el.tbody.textContent = '';
      renderCards(list);
      return;
    }
    if (el.cards) el.cards.textContent = '';
    el.tbody.textContent = '';   // 表格分支必须清空，否则每次搜索都是追加而不是替换

    var frag = document.createDocumentFragment();
    list.forEach(function (r) {
      var tr = document.createElement('tr');
      var rowCls = [];
      if (state.me && String(r.userid) === String(state.me)) rowCls.push('me');
      if (r.rank <= 3) rowCls.push('rk' + r.rank);
      if (rowCls.length) tr.className = rowCls.join(' ');

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
      // 侠名下方只保留转数；uid 不展示（详情弹窗里有），避免 11 位 uid 把列撑得不整齐
      if (r.inheritCount !== null && r.inheritCount !== undefined) {
        var metaRow = h('span', 'meta-row');
        var z = Number(r.inheritCount) || 0;
        metaRow.appendChild(h('span', 'zhuan' + (z >= 4 ? ' hi' : ''), z + '转'));
        wrap.appendChild(metaRow);
      }
      tdName.appendChild(wrap);
      tr.appendChild(tdName);

      // 门派
      var tdS = h('td', 'c-school');
      tdS.appendChild(h('span', 'school', r.menpai || '—'));
      tr.appendChild(tdS);

      // 数值列
      function numCell(cls, text) {
        tr.appendChild(h('td', cls, text));
      }

      numCell('c-lv num', r.lv != null ? String(r.lv) : '—');
      numCell('c-exp num', fmtBig(r.exp));
      numCell('c-luck num', r.fuyuan != null ? String(r.fuyuan) : '—');
      numCell('c-looks num', fmtInt(r.looks));
      numCell('c-age num', r.age != null ? r.age + ' 岁' : '—');

      frag.appendChild(tr);
    });
    el.tbody.appendChild(frag);
  }

  /* 表头 aria-sort 跟随当前排序（卡片态也保持一致） */
  function syncSortState() {
    Array.prototype.forEach.call(el.tbl.querySelectorAll('th[data-key]'), function (th) {
      if (th.dataset.key === state.sortKey) {
        th.setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
      } else {
        th.removeAttribute('aria-sort');
      }
    });
  }

  /* ---------- 门派筛选 ---------- */

  var CHIP_LIMIT = 8;   // 默认只露前 8 个门派（按人数排序）

  function buildChips() {
    var cnt = {};
    state.rows.forEach(function (r) {
      var s = r.menpai || '未知';
      cnt[s] = (cnt[s] || 0) + 1;
    });
    var keys = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; });
    var total = keys.length;

    // 收起时显示几个门派：
    //   桌面 → 前 8 个；手机 → 只留「展开全部」（门派本来就不超过 8 个时直接全显示）
    var limit = isMobile() ? (total > CHIP_LIMIT ? 0 : total) : CHIP_LIMIT;
    var show = state.chipsAll ? keys : keys.slice(0, limit);
    if (!state.chipsAll && state.school && show.indexOf(state.school) < 0) {
      show = show.concat([state.school]);
    }

    el.chips.textContent = '';
    el.chips.classList.toggle('expanded', !!state.chipsAll);

    var all = h('button', 'chip', '全部');
    all.type = 'button';
    all.setAttribute('aria-pressed', state.school ? 'false' : 'true');
    all.addEventListener('click', function () { selectSchool(''); });
    el.chips.appendChild(all);

    show.forEach(function (s) {
      var b = h('button', 'chip', s + ' ' + (cnt[s] || 0));
      b.type = 'button';
      b.dataset.school = s;
      b.setAttribute('aria-pressed', state.school === s ? 'true' : 'false');
      b.addEventListener('click', function () { selectSchool(s); });
      el.chips.appendChild(b);
    });

    if (total > CHIP_LIMIT) {
      var more = h('button', 'chip chip-more',
        state.chipsAll ? '收起' : '展开全部 ' + total + ' 个门派');
      more.type = 'button';
      more.dataset.action = 'toggle-chips';
      more.setAttribute('aria-expanded', state.chipsAll ? 'true' : 'false');
      more.addEventListener('click', function () {
        state.chipsAll = !state.chipsAll;
        buildChips();
      });
      el.chips.appendChild(more);
    }
  }

  function selectSchool(s) {
    state.school = s;
    buildChips();   // 重建一次，保证选中态与「展开/收起」状态一致
    render();
  }

  /* ---------- 转数筛选 ---------- */

  // 只有该分区同时存在多个转数时才显示（例如墨羽惊鸿：2转/3转/4转并存），
  // 其余分区只有一档，显示了也只是个死按钮。
  function buildZhuanChips() {
    if (!el.zchips) return;
    var cnt = {}, keys = [];
    state.rows.forEach(function (r) {
      var z = zhuanOf(r);
      if (!cnt[z]) { cnt[z] = 0; keys.push(z); }
      cnt[z]++;
    });
    if (keys.length <= 1) {
      el.zchips.hidden = true;
      el.zchips.textContent = '';
      state.zhuan = '';
      return;
    }
    keys.sort(function (a, b) { return Number(a) - Number(b); });
    el.zchips.hidden = false;
    el.zchips.textContent = '';

    var all = h('button', 'chip', '全部转数');
    all.type = 'button';
    all.setAttribute('aria-pressed', state.zhuan ? 'false' : 'true');
    all.addEventListener('click', function () { selectZhuan(''); });
    el.zchips.appendChild(all);

    keys.forEach(function (z) {
      var b = h('button', 'chip', z + '转 ' + cnt[z]);
      b.type = 'button';
      b.setAttribute('aria-pressed', state.zhuan === z ? 'true' : 'false');
      b.addEventListener('click', function () { selectZhuan(z); });
      el.zchips.appendChild(b);
    });
  }

  function selectZhuan(z) {
    state.zhuan = z;
    buildZhuanChips();
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

  /* 档案渲染抽到 assets/profile.js：详情弹窗与独立查询页共用同一套 DOM */
  function renderProfile(p) {
    FZJH.renderProfile(pfBody, p);
  }

  // 统一的地址拼装：必须带上 s=（分区），否则分享出去的链接会在别人的机器上
  // 回落到默认分区，点开同名 uid 就是错的人或 404
  function urlFor(uid) {
    var q = [];
    if (window.FZJH && FZJH.key) q.push('s=' + encodeURIComponent(FZJH.key));
    if (state.me) q.push('me=' + encodeURIComponent(state.me));
    if (uid) q.push('uid=' + encodeURIComponent(uid));
    return location.pathname + (q.length ? '?' + q.join('&') : '');
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

    history.replaceState(null, '', urlFor(row.userid));

    var base = (window.FZJH && FZJH.base) ? FZJH.base : './data/servers/taptap/';
    fetch(base + 'profiles/' + row.userid + '.json', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (p) { renderProfile(p); })
      .catch(function (e) {
        pfBody.textContent = '';
        pfBody.appendChild(h('p', 'pf-err', '读取失败：' + e.message + '。该玩家可能未抓到详情，或详情文件还没生成。'));
      });
  }

  function closeProfile() {
    if (typeof pf.close === 'function') pf.close();
    else pf.removeAttribute('open');
    history.replaceState(null, '', urlFor(null));
  }

  pfClose.addEventListener('click', closeProfile);

  // 点遮罩关闭（点内容区不关）
  pf.addEventListener('click', function (e) {
    if (e.target === pf) closeProfile();
  });

  // Esc 关闭时也清掉地址里的 uid（原生 dialog 的 cancel 行为）
  pf.addEventListener('close', function () {
    if (new URLSearchParams(location.search).get('uid')) {
      history.replaceState(null, '', urlFor(null));
    }
  });

  /* ---------- 启动 ---------- */

  // 隐私名单（data/hidden.json）已由数据层在生成榜单 / 快照 / 档案时剔除，
  // 前端不再重复过滤，省掉一次请求和一套死分支。
  function boot() {
    loadBoard();
  }

  function loadBoard() {
    fetch(dataUrl(), { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        state.rows = (d.rows || []).slice();
        state.hasPrev = !!d.hasPrev;
        state.rows.forEach(function (r) { r.rank = r.rank || 0; });
        el.updated.textContent = fmtUpdated(d.updatedTs, d.updatedAt);
        el.updated.title = '数据时间：' + (d.updatedAt || '未知');
        buildChips();
        buildZhuanChips();
        render();

        // 跨过 560px 断点时切换「表格 / 卡片」两套渲染
        // 门派 chips 的展开策略也要跟着变（桌面露 8 个 / 手机只留展开）
        var onMQ = function () { buildChips(); buildZhuanChips(); render(); };
        if (mqMobile.addEventListener) mqMobile.addEventListener('change', onMQ);
        else if (mqMobile.addListener) mqMobile.addListener(onMQ);

        // 支持 ?uid=123 直接打开某人档案
        var uidParam = new URLSearchParams(location.search).get('uid');
        if (uidParam) {
          var target = null;
          for (var i = 0; i < state.rows.length; i++) {
            if (String(state.rows[i].userid) === uidParam) { target = state.rows[i]; break; }
          }
          if (target) openProfile(target);
          else if (window.FZJH && FZJH.notice) {
            FZJH.notice('当前分区「' + (FZJH.name || FZJH.key) + '」的排行榜里没有 UID ' + uidParam + '，换一个分区再看看。');
          }
        }
      })
      .catch(function (e) {
        el.updated.textContent = '数据加载失败';
        el.count.hidden = true;
        el.empty.hidden = false;
        el.empty.textContent = '数据读取失败（' + e.message + '）。若是本地打开，请用本地服务器访问，不要直接双击 html。';
      });
  }

  if (window.FZJH && FZJH.init) FZJH.init(boot);
  else boot();
})();
