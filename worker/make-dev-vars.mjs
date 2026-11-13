// 从仓库 config.json 生成 .dev.vars（本地调试用，绝不提交）
import fs from 'node:fs';

const cfg = JSON.parse(fs.readFileSync('../config.json', 'utf8'));
const lines = [
  'FZJH_SERVERS=' + JSON.stringify(cfg.servers),
  'FZJH_HOTVER=' + cfg.hotver,
  'FZJH_ORIGIN=https://fzpaihang.github.io,http://localhost:8000,http://127.0.0.1:8000',
];
fs.writeFileSync('.dev.vars', lines.join('\n') + '\n', 'utf8');
console.log('已生成 .dev.vars（%d 个分区）', cfg.servers.length);
