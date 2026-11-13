// 把仓库里的榜单快照和 names.json 打包成 Worker 可 import 的模块
// 输出：src/boards.js（补排名/福缘/门派）+ src/names.js（武学/装备中文名）
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve('..');
const DATA = path.join(ROOT, 'data', 'servers');
const OUT = path.resolve('src');

const boards = {};
for (const key of fs.readdirSync(DATA)) {
  const p = path.join(DATA, key, 'gaoshoubang.json');
  if (!fs.existsSync(p)) continue;
  const rows = JSON.parse(fs.readFileSync(p, 'utf8')).rows || [];
  boards[key] = rows.map((r) => ({
    u: r.userid,
    n: r.name || '',
    lv: r.lv ?? null,
    m: r.menpai || '',
    r: r.rank ?? null,
    fy: r.fuyuan ?? null,
  }));
}

fs.writeFileSync(
  path.join(OUT, 'boards.js'),
  'export const BOARDS = ' + JSON.stringify(boards) + ';\n',
  'utf8'
);

const names = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'names.json'), 'utf8'));
fs.writeFileSync(
  path.join(OUT, 'names.js'),
  'export const NAMES = ' + JSON.stringify(names) + ';\n',
  'utf8'
);

const total = Object.values(boards).reduce((a, b) => a + b.length, 0);
console.log(
  'boards: %d 区 %d 人 %.1fKB | names %.1fKB',
  Object.keys(boards).length,
  total,
  fs.statSync(path.join(OUT, 'boards.js')).size / 1024,
  fs.statSync(path.join(OUT, 'names.js')).size / 1024
);
