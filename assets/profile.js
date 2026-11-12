/* 玩家档案渲染 —— 高手榜详情弹窗 与 独立查询页 共用
 *
 * 用法： FZJH.renderProfile(hostElement, profileObject)
 * profile 结构 = 抓取脚本 parse_profile() 的产物（历史档案 JSON 与实时接口返回同构）
 */
(function () {
  'use strict';

  var FZJH = window.FZJH = window.FZJH || {};

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
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

  function fmtInt(n) {
    if (n === null || n === undefined || n === '') return '—';
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /* 时间统一按北京时间（UTC+8），避免海外访客看到错月份 */
  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function bjParts(ts) {
    var d = new Date((ts + 8 * 3600) * 1000);
    return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, day: d.getUTCDate() };
  }

  function fmtYM(ts) {
    if (!ts) return '';
    var d = bjParts(ts);
    return String(d.y).slice(2) + '-' + pad2(d.m);
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

  function skillList(list, limit) {
    var wrap = document.createElement('div');
    var shown = list.slice(0, limit);
    var query = '';

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

  function renderProfile(host, p) {
    host.textContent = '';

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
    host.appendChild(grid);

    // 传承历程（曾用名）
    var hist = p.history || [];
    if (hist.length) {
      var sH = section('传承历程 · ' + hist.length + ' 转');
      var chain = h('div', 'pf-chain');

      var origin = h('span', 'pf-life origin');
      origin.appendChild(h('b', null, hist[0].p || '初代'));
      chain.appendChild(origin);

      hist.forEach(function (x, i) {
        chain.appendChild(h('span', 'pf-arrow', '→'));
        var life = h('span', 'pf-life' + (i === hist.length - 1 ? ' cur' : ''));
        life.appendChild(h('b', null, x.n || '—'));
        if (x.t) life.appendChild(h('span', 'when', fmtYM(x.t)));
        chain.appendChild(life);
      });

      sH.appendChild(chain);
      host.appendChild(sH);
    }

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
      host.appendChild(s1);
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
      host.appendChild(s0);
    }

    // 武学
    var list = p.skills || [];
    if (list.length) {
      var s2 = section('武学 ' + list.length + ' 门');
      s2.appendChild(skillList(list, 12));
      host.appendChild(s2);
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
      host.appendChild(s3);
    }
  }

  FZJH.renderProfile = renderProfile;
})();
