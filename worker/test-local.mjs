// 本地协议验证：用真实账号跑一次握手 + get_user_info
import fs from 'node:fs';
import { handshake, apiPost } from './src/proto.js';

const cfgAll = JSON.parse(fs.readFileSync('../config.json', 'utf8'));
const uid = Number(process.argv[2] || 21079748850);
const key = process.argv[3] || 'taptap_3';
const s = (cfgAll.servers || []).find((x) => x.key === key);
if (!s) throw new Error('无此分区 ' + key);

const cfg = {
  uuid: s.uuid,
  account: s.account,
  channel: s.channel || key,
  hotver: s.hotver || cfgAll.hotver,
  ver: s.ver || cfgAll.ver,
  device: s.device || cfgAll.device || '',
};

const t0 = Date.now();
const keys = await handshake(cfg);
console.log('握手 OK', Object.keys(keys).join(','), 'FZJH03 len=', keys.FZJH03[0].length);
const d = await apiPost(cfg, 'get_user_info', { userid: uid, type: 0 }, keys);
console.log('errcode=', d.errcode, 'errmsg=', d.errmsg || '-', 'name=', d.data && d.data.name, '耗时', Date.now() - t0, 'ms');
console.log('样例字段:', d.data ? Object.keys(d.data).slice(0, 12).join(',') : '无');
