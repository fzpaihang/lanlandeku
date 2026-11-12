/* 分区（服务器）解析与切换器 —— 首页和经验页共用 */
(function () {
  'use strict';

  var FZJH = window.FZJH = window.FZJH || {};
  var INDEX_URL = './data/servers/index.json';

  function params() { return new URLSearchParams(location.search); }

  /** 站内跳转要保留的参数：分区、高亮自己、要打开的档案 */
  function keepParams() {
    var q = params();
    var out = [];
    if (FZJH.key) out.push('s=' + encodeURIComponent(FZJH.key));
    ['me', 'uid'].forEach(function (k) {
      var v = q.get(k);
      if (v) out.push(k + '=' + encodeURIComponent(v));
    });
    return out;
  }

  FZJH.init = function (cb) {
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
  };

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
