/* 玩家查询页：把 UID 拼成 GitHub Issue，由 Actions 实时查询并回帖
 * GitHub 没有匿名写入口，所以「提交」这一步必须登录 GitHub。 */
(function () {
  'use strict';

  var REPO = 'fzpaihang/lanlandeku';
  var RECENT_KEY = 'fzjh_lookup_recent';
  var RECENT_MAX = 5;

  var el = {
    uid: document.getElementById('uid'),
    go: document.getElementById('go'),
    state: document.getElementById('state'),
    notice: document.getElementById('notice'),
    recent: document.getElementById('recent'),
    tips: document.getElementById('tips')
  };

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function notice(msg) {
    if (!el.notice) return;
    if (!msg) { el.notice.hidden = true; el.notice.textContent = ''; return; }
    el.notice.textContent = msg;
    el.notice.hidden = false;
  }

  function setState(text, kind) {
    if (!el.state) return;
    el.state.textContent = text;
    el.state.className = 'pill' + (kind === 'warn' ? '' : ' ghost');
  }

  function issueUrl(uid) {
    var title = '[QUERY] ' + uid;
    var body = [
      '由网页提交的实时查询，**请勿修改标题**（机器人靠标题识别 UID）。',
      '',
      '- UID：' + uid,
      '- 分区：自动',
      ''
    ].join('\n');
    return 'https://github.com/' + REPO + '/issues/new?title=' +
      encodeURIComponent(title) + '&body=' + encodeURIComponent(body);
  }

  /* ---------- 最近提交 ---------- */

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

  function pushRecent(uid) {
    var list = readRecent().filter(function (x) { return String(x.uid) !== uid; });
    list.unshift({ uid: uid, at: Date.now() });
    writeRecent(list);
    renderRecent();
  }

  function renderRecent() {
    if (!el.recent) return;
    var list = readRecent();
    el.recent.textContent = '';
    if (!list.length) {
      if (el.tips) el.tips.hidden = true;
      return;
    }
    if (el.tips) el.tips.hidden = false;
    list.forEach(function (x) {
      var b = h('button', 'lk-chip', 'UID ' + x.uid);
      b.type = 'button';
      b.addEventListener('click', function () {
        el.uid.value = x.uid;
        openIssue(x.uid);
      });
      el.recent.appendChild(b);
    });
  }

  /* ---------- 提交 ---------- */

  function openIssue(uid) {
    pushRecent(uid);
    setState('等待提交', 'warn');
    notice('已打开 GitHub 提交页：点「Submit new issue」后约 30–90 秒出结果，结果会作为评论出现在该 Issue 里。');
    var w = window.open(issueUrl(uid), '_blank', 'noopener');
    if (!w) notice('弹窗被拦截了，请允许弹窗后重试，或手动打开：' + issueUrl(uid));
  }

  function submit() {
    var raw = el.uid.value.replace(/\D/g, '');
    el.uid.value = raw;
    if (!/^[0-9]{5,12}$/.test(raw)) {
      setState('UID 格式不对', 'warn');
      notice('UID 应该是 5–12 位纯数字。');
      el.uid.focus();
      return;
    }
    notice('');
    openIssue(raw);
  }

  el.go.addEventListener('click', submit);
  el.uid.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
  });
  el.uid.addEventListener('input', function () {
    var v = el.uid.value.replace(/\D/g, '');
    if (v !== el.uid.value) el.uid.value = v;
  });

  renderRecent();
})();
