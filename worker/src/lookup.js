// 查询编排：会话密钥复用 + 单区/自动探测 + 限流退避
import { handshake, apiPost } from './proto.js';
import { parseProfile } from './profile.js';
import { BOARDS } from './boards.js';

const KEYS = new Map(); // key -> { ts, keys }
const KEYS_TTL = 180;
const RATE = { window: 0, count: 0 };
const RATE_LIMIT = 30;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function rateOk() {
  const win = Math.floor(Date.now() / 60000);
  if (RATE.window !== win) {
    RATE.window = win;
    RATE.count = 0;
  }
  if (RATE.count >= RATE_LIMIT) return false;
  RATE.count++;
  return true;
}

function bjTime() {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate()) +
    ' ' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds())
  );
}

function withTimeout(promise, ms, label) {
  let timer;
  const guard = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(label + ' timeout')), ms);
  });
  return Promise.race([promise, guard]).finally(() => clearTimeout(timer));
}

function srvCfg(srv, hotver) {
  return {
    uuid: srv.uuid,
    account: srv.account,
    channel: srv.channel || srv.key,
    hotver,
    ver: srv.ver || '2.1.02',
    device: srv.device || '',
  };
}

async function tryOne(srv, uid, hotver) {
  const cfg = srvCfg(srv, hotver);
  const k = srv.key;
  try {
    const rec = KEYS.get(k);
    let keys = rec && Date.now() / 1000 - rec.ts < KEYS_TTL ? rec.keys : null;
    if (!keys) {
      keys = await withTimeout(handshake(cfg), 6000, 'handshake');
      KEYS.set(k, { ts: Date.now() / 1000, keys });
    }
    const d = await withTimeout(
      apiPost(cfg, 'get_user_info', { userid: uid, type: 0 }, keys),
      6000,
      'query'
    );
    const data = d.data;
    const ec = d.errcode;
    if (ec === 0 && data && typeof data === 'object' && data.name) return { data, ec: 0 };
    if (ec === 20616) KEYS.delete(k);
    return { data: null, ec };
  } catch (e) {
    KEYS.delete(k);
    return { data: null, ec: -1 };
  }
}

function finish(uid, srv, data) {
  const row = (BOARDS[srv.key] || []).find((r) => String(r.u) === String(uid));
  const prof = parseProfile(data, row, uid);
  prof.server = srv.key;
  prof.serverName = srv.name;
  prof.source = 'live';
  prof.fetchedAt = bjTime();
  return prof;
}

export function orderServers(servers, uid) {
  const s = String(uid);
  let guess = [];
  if (s.length === 7) guess = ['taptap'];
  else if (s.length === 10) guess = ['4399'];
  else if (s.length === 11) guess = ['taptap_3', 'taptap_2', 'taptap_4'];
  const keys = [...guess];
  for (const x of servers) if (!keys.includes(x.key)) keys.push(x.key);
  const by = Object.fromEntries(servers.map((x) => [x.key, x]));
  return keys.map((k) => by[k]).filter(Boolean);
}

export async function lookup(uid, server, servers, hotver) {
  if (server !== 'auto') {
    const srv = servers.find((s) => s.key === server);
    if (!srv) return { code: 'BAD_SERVER' };
    const prof = await single(uid, srv, hotver);
    if (prof) return { prof };
    return { code: lastLimited ? 'BUSY' : 'NOT_FOUND' };
  }

  const order = orderServers(servers, uid).slice(0, 2);
  for (let i = 0; i < order.length; i++) {
    const prof = await single(uid, order[i], hotver);
    if (prof) return { prof };
    if (i < order.length - 1) await sleep(400);
  }
  return { code: lastLimited ? 'BUSY' : 'NOT_FOUND' };
}

let lastLimited = false;

async function single(uid, srv, hotver) {
  lastLimited = false;
  for (let attempt = 0; attempt < 2; attempt++) {
    const { data, ec } = await tryOne(srv, uid, hotver);
    if (data) return finish(uid, srv, data);
    if (ec === 0) return null; // 服务端明确回「没有这个角色」
    if (ec === 20616 || ec === -1) {
      lastLimited = true;
      if (attempt === 0) {
        await sleep(1500);
        continue;
      }
    }
    break;
  }
  return null;
}
