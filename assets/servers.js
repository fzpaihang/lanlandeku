/* 分区（服务器）解析与切换器 —— 首页和经验页共用 */
(function () {
  'use strict';

  var FZJH = window.FZJH = window.FZJH || {};
  var INDEX_URL = './data/servers/index.json';
  var SHADOW_URL = './data/shadow.json';

  /* 影子榜口令的 sha256：仓库里只放哈希，明文不进代码 */
  var SHADOW_HASH = '601260b1695f7625078effee02d36dd9e8aebe4c4d688fd61f8ef77ac53f8db5';

  function params() { return new URLSearchParams(location.search); }

  /** v 是不是影子榜口令（只比哈希，不做任何明文判断） */
  FZJH.isShadowParam = function (v) {
    return String(v || '').toLowerCase() === SHADOW_HASH;
  };

  /** 站内跳转要保留的参数：分区、高亮自己、要打开的档案、影子口令 */
  function keepParams() {
    var q = params();
    var out = [];
    if (FZJH.key) out.push('s=' + encodeURIComponent(FZJH.key));
    ['me', 'uid', 'k'].forEach(function (k) {
      var v = q.get(k);
      if (v) out.push(k + '=' + encodeURIComponent(v));
    });
    return out;
  }

  /* ---------- 影子榜（口令命中才生效，其他访客完全无感） ---------- */

  // me=<uid> 是既有的「高亮我自己」；me=<口令hash> 或 k=<口令hash> 才是影子模式。
  // k 是给 APK 用的：APK 已经占用了 me=<uid>，口令只能另带一个参数。
  FZJH.shadowKey = '';
  FZJH.shadowMode = false;
  FZJH.shadow = null;

  /** 行拷贝：mergeShadow 不改入参，得先复制一层 */
  function copyRow(r) {
    var o = {};
    for (var k in r) {
      if (Object.prototype.hasOwnProperty.call(r, k)) o[k] = r[k];
    }
    return o;
  }

  /** 影子行的原始名次（升序）；非法值直接丢掉，坏数据不能把整张榜单带偏 */
  function shadowRanks(entry) {
    var rows = (entry && entry.rows) || [];
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var v = Number(rows[i] && rows[i].rank);
      if (isFinite(v) && v > 0) out.push(v);
    }
    out.sort(function (a, b) { return a - b; });
    return out;
  }

  /** 剔除榜单第 k 名的原始名次：每被一个影子行挤过就后移一位 */
  function origRank(k, sranks) {
    var orig = k;
    for (var i = 0; i < sranks.length; i++) {
      if (sranks[i] <= orig) orig++;
    }
    return orig;
  }

  /**
   * 把影子行按原始名次插回公开榜单，并重排 1..N。
   * 纯函数：不碰 DOM、不碰 fetch，app.js 与 exp.js 共用，也方便单测。
   * rows        公开榜单行（rank 是剔除后重排过的连续名次）
   * shadowEntry {rows:[影子行...]}，null/undefined 时返回等价副本
   */
  FZJH.mergeShadow = function (rows, shadowEntry) {
    var out = [];
    var i, o;
    var pub = (rows || []).slice();
    var sranks = shadowRanks(shadowEntry);

    // 没有影子行：只复制，不改任何字段（公开页面表现必须一字不差）
    if (!sranks.length) {
      for (i = 0; i < pub.length; i++) out.push(copyRow(pub[i]));
      return out;
    }

    for (i = 0; i < pub.length; i++) {
      o = copyRow(pub[i]);
      var rk0 = Number(o.rank) || 0;
      o.rank = origRank(rk0, sranks);
      // 涨跌箭头不能直接用 merge 后的名次减旧名次：那一减会把「影子行插回来」
      // 造成的整体后移也算成跌（13-15=-2 这类假箭头）。
      // delta 是「上一轮 → 这一轮」的真实位移，两轮都剔除了同一批人，所以位移本身
      // 不受插入影响（origPrev-origRank === prevRank-rank），必须原样保留；
      // 只有展示用的 prevRank 要跟着新名次平移，保持 prevRank-rank === delta。
      var pv = o.prevRank;
      if (typeof pv === 'number' && isFinite(pv)) {
        o.delta = pv - rk0;
        o.prevRank = o.rank + o.delta;
      } else {
        o.prevRank = null;
        o.delta = null;
      }
      out.push(o);
    }

    var srows = (shadowEntry && shadowEntry.rows) || [];
    for (i = 0; i < srows.length; i++) {
      o = copyRow(srows[i]);
      o.rank = Number(o.rank) || 0;
      o._shadow = true;
      // 影子行在公开口径里没有可比的历史名次：宁可没有箭头，也不出假箭头
      o.prevRank = null;
      o.delta = null;
      out.push(o);
    }

    out.sort(function (a, b) {
      if (a.rank === b.rank) return (a._shadow ? 1 : 0) - (b._shadow ? 1 : 0);
      return a.rank - b.rank;
    });
    for (i = 0; i < out.length; i++) out[i].rank = i + 1;
    return out;
  };

  FZJH.init = function (cb) {
    var q = params();
    var meV = q.get('me') || '';
    var kV = q.get('k') || '';
    FZJH.shadowKey = FZJH.isShadowParam(meV) ? meV : (FZJH.isShadowParam(kV) ? kV : '');

    // 口令命中才去取影子数据；取不到（首份还没产出 / 404）就静默降级，
    // 公开页面的表现不能受任何影响
    if (!FZJH.shadowKey) { loadServers(cb); return; }
    fetch(SHADOW_URL, { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        FZJH.shadow = d || null;
        FZJH.shadowMode = !!(d && d.servers);
      })
      .catch(function () {
        FZJH.shadow = null;
        FZJH.shadowMode = false;
      })
      .then(function () { loadServers(cb); });
  };

  /** 影子模式下：当前分区没有影子行、但别的分区有，就自动切过去（用户可能从别的区进站） */
  function shadowServer(cur, list) {
    var servers = (FZJH.shadow && FZJH.shadow.servers) || null;
    if (!FZJH.shadowMode || !servers) return cur;
    if (servers[cur.key] && ((servers[cur.key].rows) || []).length) return cur;
    var hit = null;
    for (var k in servers) {
      if (!Object.prototype.hasOwnProperty.call(servers, k)) continue;
      if (servers[k] && ((servers[k].rows) || []).length) { hit = k; break; }
    }
    if (!hit) return cur;
    for (var i = 0; i < list.length; i++) {
      if (list[i].key === hit) return list[i];
    }
    return cur;
  }

  function loadServers(cb) {
    var want = params().get('s') || FZJH.lastServer();

    fetch(INDEX_URL, { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .catch(function (e) {
        // 不能静默回退：分区错了整页数据都是别人的区，必须让人看见
        FZJH.listError = '分区列表读取失败（' + e.message + '），当前按默认分区显示，数据可能不是你要看的区。';
        return { servers: [] };
      })
      .then(function (d) {
        var list = (d && d.servers) || [];
        if (!list.length) {
          if (!FZJH.listError) FZJH.listError = '分区列表为空，当前按默认分区显示，数据可能不是你要看的区。';
          list = [{ key: 'taptap', name: '默认分区', default: true }];
        }

        var cur = null;
        if (want) {
          for (var i = 0; i < list.length; i++) {
            if (list[i].key === want) { cur = list[i]; break; }
          }
        }
        if (!cur) cur = list.filter(function (x) { return x.default; })[0] || list[0];
        cur = shadowServer(cur, list);

        FZJH.servers = list;
        FZJH.key = cur.key;
        FZJH.name = cur.name || cur.key;
        FZJH.base = './data/servers/' + encodeURIComponent(cur.key) + '/';

        try { localStorage.setItem('fzjh_server', cur.key); } catch (e) { }

        FZJH.renderSwitcher();
        FZJH.syncLinks();
        if (FZJH.listError) FZJH.notice(FZJH.listError);
        cb(FZJH);
      });
  }

  /** 页面顶部的提示条（各页共用 #notice），msg 为空则收起 */
  FZJH.notice = function (msg) {
    var n = document.getElementById('notice');
    if (!n) return;
    if (!msg) { n.hidden = true; n.textContent = ''; return; }
    n.textContent = msg;
    n.hidden = false;
  };

  // 站内跳转（高手榜 ⇄ 经验变化）不能把分区丢掉，否则换人打开就是另一个区
  FZJH.syncLinks = function () {
    if (!FZJH.key) return;
    var extra = keepParams().join('&');
    Array.prototype.forEach.call(document.querySelectorAll('a.navbtn'), function (a) {
      var href = a.getAttribute('href') || '';
      if (href.indexOf('?') >= 0 || !extra) return;   // 已带参数则不重复拼
      a.setAttribute('href', href + '?' + extra);
    });
  };

  FZJH.renderSwitcher = function () {
    var host = document.getElementById('server-switch');
    if (!host) return;
    var list = FZJH.servers || [];
    if (list.length < 2) { host.hidden = true; return; }

    host.hidden = false;
    host.textContent = '';

    var label = document.createElement('span');
    label.className = 'srv-label';
    label.textContent = '分区';
    host.appendChild(label);

    // 切区时把 me / uid 一起带上：否则切完高亮和已打开的档案都会丢
    var tail = keepParams().filter(function (x) { return x.indexOf('s=') !== 0; });
    var suffix = tail.length ? '&' + tail.join('&') : '';

    list.forEach(function (s) {
      var a = document.createElement('a');
      a.className = 'srv' + (s.key === FZJH.key ? ' active' : '');
      a.href = '?s=' + encodeURIComponent(s.key) + suffix;
      a.textContent = s.name || s.key;
      if (s.key === FZJH.key) a.setAttribute('aria-current', 'page');
      a.addEventListener('click', function () {
        try { localStorage.setItem('fzjh_server', s.key); } catch (e) { }
      });
      host.appendChild(a);
    });
  };

  // 记得上次看的分区（没有 ?s= 时生效）
  FZJH.lastServer = function () {
    try { return localStorage.getItem('fzjh_server'); } catch (e) { return null; }
  };
})();
