/* 分区（服务器）解析与切换器 —— 首页和经验页共用 */
(function () {
  'use strict';

  var FZJH = window.FZJH = window.FZJH || {};
  var INDEX_URL = './data/servers/index.json';

  FZJH.init = function (cb) {
    var params = new URLSearchParams(location.search);
    var want = params.get('s') || FZJH.lastServer();

    fetch(INDEX_URL, { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : { servers: [] }; })
      .catch(function () { return { servers: [] }; })
      .then(function (d) {
        var list = (d && d.servers) || [];
        if (!list.length) {
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
        cb(FZJH);
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

    list.forEach(function (s) {
      var a = document.createElement('a');
      a.className = 'srv' + (s.key === FZJH.key ? ' active' : '');
      a.href = '?s=' + encodeURIComponent(s.key);
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
