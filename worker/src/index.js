// Cloudflare Worker 入口：GET/POST /api/query?uid=...&server=...
import { lookup, rateOk } from './lookup.js';
import { handshake } from './proto.js';

const CACHE = new Map();
const CACHE_TTL = 600;
const NOT_FOUND_TTL = 15;
const DEFAULT_SERVER = 'taptap_3';

function parseServers(env) {
  const raw = env.FZJH_SERVERS;
  if (!raw) throw new Error('缺少 FZJH_SERVERS');
  const d = JSON.parse(raw);
  const items = Array.isArray(d) ? d : d.servers || [];
  const hotver = Number(env.FZJH_HOTVER || d.hotver || 18464);
  const ver = d.ver || '2.1.02';
  const device = d.device || '';
  return items.map((s, i) => ({
    key: String(s.key || s.channel || 's' + i),
    name: s.name || s.key || '分区',
    channel: s.channel || s.key,
    uuid: s.uuid,
    account: s.account,
    hotver: Number(s.hotver || hotver),
    ver: s.ver || ver,
    device: s.device || device,
  }));
}

function allowedOrigin(origin, env) {
  const list = String(env.FZJH_ORIGIN || 'https://fzpaihang.github.io')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (!origin) return list[0];
  if (list.includes(origin)) return origin;
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return origin;
  return list[0];
}

function cors(origin, env) {
  return {
    'Access-Control-Allow-Origin': allowedOrigin(origin, env),
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

function json(body, status, origin, env) {
  return new Response(JSON.stringify(body), {
    status,
    headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8' }, cors(origin, env)),
  });
}

async function readQuery(request) {
  const url = new URL(request.url);
  const q = Object.fromEntries(url.searchParams);
  if (request.method === 'POST') {
    try {
      const txt = await request.text();
      if (txt) Object.assign(q, JSON.parse(txt));
    } catch (e) {
      /* 非法 JSON 忽略，按无参数处理 */
    }
  }
  return q;
}

export default {
  async fetch(request, env) {
    const t0 = Date.now();
    const origin = request.headers.get('Origin') || '';
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors(origin, env) });

    let q;
    try {
      q = await readQuery(request);
    } catch (e) {
      return json({ ok: false, code: 'BAD_REQUEST', message: '参数解析失败' }, 400, origin, env);
    }

    if (String(q.diag || '') === '1') {
      const out = { ok: true, runtime: 'workers', colo: request.cf?.colo || '', country: request.cf?.country || '', steps: [] };
      try {
        const servers = parseServers(env);
        const s = servers[0];
        const t = Date.now();
        const keys = await handshake({ uuid: s.uuid, account: s.account, channel: s.channel, hotver: s.hotver, ver: s.ver, device: s.device });
        out.steps.push({ name: 'handshake', ok: true, ms: Date.now() - t, keys: Object.keys(keys).join(',') });
      } catch (e) {
        out.steps.push({ name: 'handshake', ok: false, error: String(e).slice(0, 200) });
      }
      out.ms = Date.now() - t0;
      return json(out, 200, origin, env);
    }

    const uidRaw = String(q.uid || '').trim();
    const server = String(q.server || DEFAULT_SERVER).trim() || DEFAULT_SERVER;
    if (!uidRaw) {
      return json({
        ok: true, service: 'fzjh-lookup',
        message: 'GET /api/query?uid=21079748850&server=taptap_3，或 POST {"uid":"...","server":"..."}',
      }, 200, origin, env);
    }
    if (!/^\d{5,12}$/.test(uidRaw)) {
      return json({ ok: false, code: 'BAD_UID', message: 'UID 应该是 5–12 位纯数字' }, 400, origin, env);
    }
    const uid = Number(uidRaw);

    let servers;
    try {
      servers = parseServers(env);
    } catch (e) {
      return json({ ok: false, code: 'CONFIG', message: '服务端配置缺失：' + e.message }, 500, origin, env);
    }
    if (server !== 'auto' && !servers.some((s) => s.key === server)) {
      return json({
        ok: false, code: 'BAD_SERVER', message: '未知分区：' + server,
        servers: servers.map((s) => ({ key: s.key, name: s.name })),
      }, 400, origin, env);
    }

    const ck = uid + '|' + server;
    const hit = CACHE.get(ck);
    if (hit && Date.now() / 1000 - hit.ts < (hit.body.code === 'NOT_FOUND' ? NOT_FOUND_TTL : CACHE_TTL)) {
      return json(Object.assign({}, hit.body, { cached: true }), hit.status, origin, env);
    }

    if (!rateOk()) {
      return json({ ok: false, code: 'BUSY', message: '查询太频繁了，请等 30 秒再试。' }, 429, origin, env);
    }

    const hotver = servers[0].hotver;
    let r;
    try {
      r = await lookup(uid, server, servers, hotver);
    } catch (e) {
      return json({ ok: false, code: 'ERROR', message: '查询异常：' + String(e).slice(0, 160) }, 500, origin, env);
    }

    if (r.prof) {
      const body = { ok: true, data: r.prof, elapsedMs: Date.now() - t0 };
      CACHE.set(ck, { ts: Date.now() / 1000, status: 200, body });
      return json(body, 200, origin, env);
    }

    if (r.code === 'BUSY') {
      const body = { ok: false, code: 'BUSY', message: '游戏接口正在限流，请等 30 秒后再试。' };
      return json(body, 429, origin, env);
    }
    const body = server === 'auto'
      ? { ok: false, code: 'NOT_FOUND', message: '自动模式猜的 2 个分区都没查到，请指定分区再试。' }
      : { ok: false, code: 'NOT_FOUND', message: '在「' + (servers.find((s) => s.key === server)?.name || server) + '」没查到这个 UID，分区选对了吗？' };
    CACHE.set(ck, { ts: Date.now() / 1000, status: 404, body });
    return json(body, 404, origin, env);
  },
};
