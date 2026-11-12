/* 玩家查询页：输入 UID → 调腾讯云函数实时拉档案 → 复用 profile.js 渲染 */
(function () {
  'use strict';

  var FZJH = window.FZJH || {};
  var API_BASE = (window.FZJH_API_BASE || '').replace(/\/+$/, '');
  var ENDPOINT = API_BASE || '/api/query';     // 本地联调走同源 /api/query
  var RECENT_KEY = 'fzjh_lookup_recent';
  var RECENT_MAX = 3;
  var TIMEOUT_MS = 15000;

  var state = { server: 'auto', busy: false };

  var el = {
    uid: document.getElementById('uid'),
    go: document.getElementById('go'),
    mode: document.getElementById('mode'),
    state: document.getElementById('state'),
    result: document.getElementById('result'),
    tips: document.getElementById('tips'),
    recent: document.getElementById('recent'),
    notice: document.getElementById('notice')
  };

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function setState(text, kind) {
    el.state.textContent = text;
    el.state.className = 'pill' + (kind === 'warn' ? '' : kind === 'ok' ? '' : ' ghost');
  }

  function notice(msg) {
    if (!el.notice) return;
    if (!msg) { el.notice.hidden = true; el.notice.textContent = ''; return; }
    el.notice.textContent = msg;
    el.notice.hidden = false;
  }

  function busy(on) {
    state.busy = on;
    el.go.disabled = on;
    el.go.textContent = on ? '查询中…' : '查询';
  }

  /* 当前分区模式说明：自动 / 指定某区 */
  function renderMode(fz) {
    paintSwitcher();
    if (!el.mode) return;
    if (state.server === 'auto') {
      el.mode.textContent = '分区：自动（按 UID 位数先猜，猜不中再逐区试；也可点上方分区固定一个）';
    } else {
      var name = (fz && fz.name) || state.server;
      el.mode.textContent = '分区：' + name + '（点上方分区可切换）';
    }
  }

  /* 分区条高亮跟随实际模式：自动时不要假装选中了某个区 */
  function paintSwitcher() {
    var host = document.getElementById('server-switch');
    if (!host) return;
    var fake = host.querySelector('.srv.auto-mode');
    if (fake) host.removeChild(fake);
    Array.prototype.forEach.call(host.querySelectorAll('a.srv'), function (a) {
      var key = new URLSearchParams((a.getAttribute('href') || '').split('?')[1] || '').get('s');
      var on = key === state.server;
      a.classList.toggle('active', on);
      if (on) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    if (state.server === 'auto') {
      var chip = document.createElement('span');
      chip.className = 'srv active auto-mode';
      chip.textContent = '自动';
      var label = host.querySelector('.srv-label');
      if (label && label.nextSibling) host.insertBefore(chip, label.nextSibling);
      else host.appendChild(chip);
    }
  }

  /* ---------- 最近查询 ---------- */

  function readRecent() {
    try {
      var raw = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
      return Array.isArray(raw) ? raw.filter(function (x) { return x && x.uid; }).slice(0, RECENT_MAX) : [];
    } catch (e) {
      return [];
    }
  }

  function writeRecent(list) {
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX))); } catch (e) { }
  }

  function pushRecent(prof) {
    var item = {
      uid: String(prof.uid),
      name: prof.name || '',
      server: prof.server || state.server,
      serverName: prof.serverName || ''
    };
    var list = readRecent().filter(function (x) { return String(x.uid) !== item.uid; });
    list.unshift(item);
    writeRecent(list);
    renderRecent();
  }

  function renderRecent() {
    if (!el.recent) return;
    var list = readRecent();
    el.recent.textContent = '';
    if (!list.length) {
      el.tips.hidden = false;
      el.recent.appendChild(h('span', 'lk-hint', '还没有查过谁，试试榜上第一名的 UID：21079729670'));
      return;
    }
    el.tips.hidden = false;
    list.forEach(function (x) {
      var b = h('button', 'lk-chip', (x.name || 'UID ' + x.uid) + ' · ' + x.uid);
      b.type = 'button';
      b.addEventListener('click', function () {
        el.uid.value = x.uid;
        if (x.server) { state.server = x.server; renderMode({ name: x.serverName || x.server }); }
        query();
      });
      el.recent.appendChild(b);
    });
  }

  /* ---------- 渲染结果 ---------- */

  function showProfile(prof, meta) {
    el.result.hidden = false;
    el.result.textContent = '';

    var head = h('div', 'lk-head');
    head.appendChild(h('h2', null, prof.name || '—'));

    var bits = [];
    if (prof.serverName) bits.push(prof.serverName);
    bits.push(prof.rank ? ('第 ' + prof.rank + ' 名') : '未上榜');
    bits.push('UID ' + prof.uid);
    head.appendChild(h('span', 'lk-sub', bits.join(' · ')));
    head.appendChild(h('span', 'lk-tag', '实时'));
    el.result.appendChild(head);

    var body = h('div', 'lk-body');
    el.result.appendChild(body);
    if (FZJH.renderProfile) FZJH.renderProfile(body, prof);

    var foot = [];
    if (meta && meta.cached) foot.push('60 秒内查过同一个角色，直接复用上次结果');
    else if (meta && meta.elapsed) foot.push('用时 ' + (meta.elapsed / 1000).toFixed(1) + ' 秒');
    if (prof.lvEstimated) foot.push('等级由经验反算（该角色不在榜上）');
    if (foot.length) el.result.appendChild(h('p', 'lk-hint', foot.join(' · ')));
  }

  function showFail(msg) {
    el.result.hidden = false;
    el.result.textContent = '';
    var head = h('div', 'lk-head');
    head.appendChild(h('h2', null, '没查到'));
    el.result.appendChild(head);
    el.result.appendChild(h('p', 'lk-hint', msg));
  }

  /* ---------- 查询 ---------- */

  function query() {
    if (state.busy) return;

    var raw = el.uid.value.replace(/\D/g, '');
    if (raw !== el.uid.value) el.uid.value = raw;
    if (!/^[0-9]{5,12}$/.test(raw)) {
      setState('UID 格式不对', 'warn');
      el.result.hidden = true;
      notice('UID 应该是 5–12 位纯数字。');
      el.uid.focus();
      return;
    }
    notice('');

    var ctrl = null;
    var timer = null;
    var opts = { cache: 'no-store' };
    if (typeof AbortController === 'function') {
      ctrl = new AbortController();
      opts.signal = ctrl.signal;
      timer = setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);
    }

    busy(true);
    setState('查询中…', 'warn');
    el.result.hidden = true;

    var t0 = Date.now();
    fetch(ENDPOINT + '?uid=' + encodeURIComponent(raw) + '&server=' + encodeURIComponent(state.server), opts)
      .then(function (r) {
        return r.text().then(function (txt) {
          var body = null;
          try { body = JSON.parse(txt); } catch (e) { body = null; }
          if (!body) throw new Error('HTTP ' + r.status + '（返回的不是 JSON）');
          return body;
        });
      })
      .then(function (d) {
        if (timer) clearTimeout(timer);
        busy(false);
        if (d.ok && d.data) {
          var ms = d.elapsedMs || (Date.now() - t0);
          setState(d.cached ? '已完成 · 缓存' : '已完成 · ' + (ms / 1000).toFixed(1) + ' 秒', 'ok');
          showProfile(d.data, { elapsed: ms, cached: d.cached });
          pushRecent(d.data);
          return;
        }
        var msg = d.message || '查询失败';
        setState(d.code === 'NOT_FOUND' ? '没查到' : '查询失败', 'warn');
        showFail(msg);
      })
      .catch(function (e) {
        if (timer) clearTimeout(timer);
        busy(false);
        setState('查询失败', 'warn');
        var msg = (e && e.name === 'AbortError')
          ? '等了 ' + (TIMEOUT_MS / 1000) + ' 秒还没回来，接口可能被限流，过一会儿再试。'
          : '连不上查询服务（' + (e && e.message ? e.message : '网络错误') + '）。如果是刚部署，检查函数地址和跨域白名单。';
        showFail(msg);
      });
  }

  /* ---------- 启动 ---------- */

  function boot(fz) {
    // 默认自动探测：先按 UID 位数猜分区（7 位→苍松、10 位→4399、11 位→丹凤/白鹤/墨羽），
    // 猜不中再逐区试，比硬编码一个分区对新访客友好。地址带 ?s=xxx 时按指定的来。
    var pinned = new URLSearchParams(location.search).get('s');
    state.server = pinned || 'auto';
    if (!pinned) state.fallbackName = (fz && fz.name) || '';
    renderMode(fz);
    renderRecent();

    el.go.addEventListener('click', query);
    el.uid.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); query(); }
    });
    el.uid.addEventListener('input', function () {
      var v = el.uid.value.replace(/\D/g, '');
      if (v !== el.uid.value) el.uid.value = v;
    });

    var uid = new URLSearchParams(location.search).get('uid');
    if (uid) { el.uid.value = uid.replace(/\D/g, ''); query(); }
  }

  if (FZJH && FZJH.init) FZJH.init(boot);
  else boot(null);
})();
