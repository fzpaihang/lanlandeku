// 档案解析：原始 get_user_info → 前端展示结构（对齐 apk/lookup_core.py 的 parse_profile）
import { NAMES } from './names.js';

const MENPAI_CN = {
  gaibang: '丐帮', haijing: '海鲸帮', guanfu: '官府', jinqianbang: '财神帮',
  mingjiao: '明教', youming: '幽冥教', yongyelou: '永夜楼', youxia: '江湖浪人',
  huashan: '华山', tangmen: '唐门', tianshan: '虚渺宫', murong: '燕氏皇族',
  kongtong: '崆峒派', tiezhang: '伏龙山', quanzhen: '全真教', emei: '峨眉派',
  kunlun: '昆仑派', mizong: '雪山寺', gumu: '问情宫', wudu: '万灵谷',
  shaolin: '少林派', tianjingmen: '天竞门', riyueshenjiao: '拜日教',
  taohuadao: '蓬莱岛', wudang: '武当派', luoyue: '落月山庄',
  baituoshan: '鸩羽山', xingxiu: '天狼教', dali: '天龙寺',
};

const SLOT_CN = {
  quanjiao1: '拳脚一', quanjiao2: '拳脚二', neigong: '内功',
  qinggong: '轻功', zhaojia: '招架', jianfa: '剑法', daofa: '刀法',
  bianfa: '鞭法', gunfa: '棍法', shuangchi: '双持', anqi: '暗器',
  qinfa: '琴法',
};

const EQUIP_CN = {
  weapon: '武器', cloth: '衣服', pants: '下装', shoes: '鞋履',
  head: '头饰', yaozhui: '腰坠', neck: '颈饰', necklace: '颈饰',
  ring: '戒指', wrist: '护腕', hand: '护手', belt: '腰带',
  cape: '披风', mask: '面具',
};

const LV_COEF = 0.100402;

function num(x, r = 0) {
  const v = Number(x);
  if (!isFinite(v)) return null;
  return Number(v.toFixed(r));
}

function lvFromExp(exp) {
  const v = Number(exp);
  if (!isFinite(v) || v <= 0) return null;
  return Math.round(Math.pow(v / LV_COEF, 1 / 3));
}

function lvOfSkill(exp) {
  const v = Number(exp);
  if (!isFinite(v)) return 0;
  if (v < 8) return Math.trunc(v);
  const base = (v - 1) / 0.015;
  if (base <= 0) return 0;
  return Math.trunc(Math.pow(base, 1 / 3));
}

function skillName(sid, map) {
  if (map[sid]) return map[sid];
  if (String(sid).includes('selfCreatedSkill')) return '自创武学';
  return String(sid);
}

export function parseProfile(data, boardRow, uid) {
  const sk = NAMES.skills || {};
  const eq = NAMES.equips || {};
  const br = boardRow || {};

  const skills = [];
  for (const [sid, v] of Object.entries(data.skills || {})) {
    if (!v || typeof v !== 'object') continue;
    skills.push({ id: sid, n: skillName(sid, sk), lv: lvOfSkill(v.exp) });
  }
  skills.sort((a, b) => b.lv - a.lv || (a.n < b.n ? -1 : a.n > b.n ? 1 : 0));

  const prepared = {};
  for (const [slot, sid] of Object.entries(data.skillPrepare || {})) {
    if (!sid || typeof sid !== 'string') continue;
    prepared[SLOT_CN[slot] || slot] = skillName(sid, sk);
  }

  const equips = [];
  for (const [slot, v] of Object.entries(data.equips || {})) {
    if (!v || typeof v !== 'object' || !v.itemId) continue;
    equips.push({ slot: EQUIP_CN[slot] || slot, n: eq[String(v.itemId)] || '未知' });
  }

  const history = (data.inheritHistory || [])
    .filter((x) => x && typeof x === 'object')
    .map((x) => ({ n: x.inheritName || '', t: Math.trunc(Number(x.inheritTime) || 0) }))
    .sort((a, b) => a.t - b.t);

  const fam = (data.family && data.family.name) || '';
  const exp = num(data.exp, 4);
  const menpai = br.m || MENPAI_CN[fam] || '';
  const lv = br.lv || lvFromExp(exp);
  const lvEstimated = !br.lv;

  return {
    uid,
    name: data.name || '',
    sex: data.sex || '',
    age: data.age ?? null,
    looks: data.looks ?? null,
    menpai,
    menpaiCode: fam,
    lv,
    lvEstimated,
    kongfu: num(data.kongfu, 2),
    exp,
    qi: num(data.qi, 2),
    qiMax: num(data.qiMax, 2),
    jiaLi: data.jiaLi ?? null,
    zhengqi: num(data.zhengqi, 0),
    fuyuan: br.fy ?? null,
    rank: br.r ?? null,
    inheritCount: data.inheritCount ?? null,
    onBoard: !!boardRow,
    skills,
    prepared,
    equips,
    history,
  };
}
