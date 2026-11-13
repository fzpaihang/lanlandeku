// 游戏接口协议层：握手 + 加解密 + 签名
// 逐行对齐 apk/fetch.py，唯一差别是 AES 走 aes-js（无填充）而不是 Python 的 aes_pure。
import aesjs from 'aes-js';
import md5 from 'js-md5';

export const DOMAIN = 'https://android.fzjh.xiaohoutiaotiao.com';
const SALT = 'ed24bd36b1a87f60bebaca65538a590c';
const K02 = 'cbIhHHuYQIJ1JkwlLupIvNIvdQDfNxSF';
const IV02 = 'PcIQIZifRalhZ88n';
const TAG = 0x30; // '0'

const enc = new TextEncoder();
const dec = new TextDecoder('utf-8');

export function hexToBytes(hex) {
  const n = hex.length >> 1;
  const out = new Uint8Array(n);
  for (let i = 0; i < n; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

export function bytesToHex(bytes) {
  let s = '';
  for (const b of bytes) s += (b < 16 ? '0' : '') + b.toString(16);
  return s;
}

function firstByte(s) {
  const c = s.charCodeAt(0);
  return c > 127 ? c - 256 : c;
}

function makeNouce() {
  const out = [];
  while (out.length < 6) {
    const c = 65 + Math.floor(Math.random() * 58); // 65~122
    if ((c > 90 && c < 97) || c === 101) continue; // 排除 [ \ ] ^ _ ` 和 e
    out.push(String.fromCharCode(c));
  }
  return out.join('');
}

export function makeSig(nouce, tStr) {
  const parts = [nouce, tStr, SALT];
  parts.sort((a, b) => firstByte(a) - firstByte(b));
  return md5(parts.join(''));
}

// 时间戳字符串：Python 的 "%.14g" % float(t)
function nowStr() {
  return (Date.now() / 1000).toPrecision(14);
}

export function buildHeaders(cfg, tStr) {
  const nouce = makeNouce();
  return {
    uuid: cfg.uuid,
    userid: String(cfg.account),
    sig: makeSig(nouce, tStr),
    time: tStr,
    nouce,
    device: cfg.device || '',
    ver: cfg.ver || '2.1.02',
    hotver: String(cfg.hotver),
    platform: 'android',
    timezone: '8',
    channel: cfg.channel || 'taptap',
    package: '',
    age: '-2',
    pkname: 'com.xhtt.app.fzjh',
    pksig: '',
  };
}

function aesCbc(keyStr, ivStr, data, doDecrypt) {
  const key = enc.encode(keyStr);
  const iv = ivStr ? enc.encode(ivStr) : new Uint8Array(16);
  const op = new aesjs.ModeOfOperation.cbc(key, iv);
  return doDecrypt ? op.decrypt(data) : op.encrypt(data);
}

// 响应 = hex 文本；解码后前 6 字节是 "JHHU02"/"FZJH03" 标签，其余是密文
function decryptBody(raw, keyStr, ivStr) {
  const body = raw.subarray(6);
  const len = body.length - (body.length % 16);
  return aesCbc(keyStr, ivStr, body.subarray(0, len), true);
}

async function readHex(res) {
  return dec.decode(new Uint8Array(await res.arrayBuffer())).trim();
}

export async function handshake(cfg) {
  const tStr = nowStr();
  const res = await fetch(DOMAIN + '/api/service/exchange_publickey', {
    method: 'POST',
    headers: buildHeaders(cfg, tStr),
    body: '',
  });
  if (!res.ok) throw new Error('握手 HTTP ' + res.status);
  const plain = dec
    .decode(decryptBody(hexToBytes(await readHex(res)), K02, IV02))
    .replace(/\x00+$/, '');
  const a = plain.indexOf('"data":"');
  if (a < 0) throw new Error('握手失败: ' + plain.slice(0, 200));
  const s = plain.slice(a + 8);
  const arr = JSON.parse(s.slice(0, s.lastIndexOf('"')).replace(/\\"/g, '"'));
  const keys = {};
  for (const e of arr) keys[e.h] = [e.k || '', e.i || ''];
  return keys;
}

export async function apiPost(cfg, path, body, keys) {
  const [k, iv] = keys['FZJH03'];
  const plain = enc.encode(JSON.stringify(body));
  const pad = 16 - (plain.length % 16);
  const buf = new Uint8Array(plain.length + pad);
  buf.set(plain);
  buf.fill(TAG, plain.length);

  const ct = aesCbc(k, iv, buf, false);
  const tag = enc.encode('FZJH03');
  const data = new Uint8Array(tag.length + ct.length);
  data.set(tag);
  data.set(ct, tag.length);

  const tStr = nowStr();
  const res = await fetch(DOMAIN + '/api/v5/' + path, {
    method: 'POST',
    headers: Object.assign(buildHeaders(cfg, tStr), { 'Content-Type': 'application/json' }),
    body: bytesToHex(data),
  });
  if (!res.ok) throw new Error('接口 HTTP ' + res.status);

  let txt = dec.decode(decryptBody(hexToBytes(await readHex(res)), k, iv));
  txt = txt.replace(/\x00+$/, '').replace(/0+$/, '').replace(/\x00+$/, '');
  const a = txt.indexOf('{');
  const z = txt.lastIndexOf('}');
  return JSON.parse(a >= 0 && z > a ? txt.slice(a, z + 1) : txt);
}
