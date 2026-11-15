# 项目当前状态（交接用）

> 这份文件代替「翻聊天记录」。**新会话先读它，再按需读具体文档**。
> 最后更新：2026-11-15 10:10（热更 v56）

---

## 一分钟速览

| 项 | 值 |
|---|---|
| 仓库 | `fzpaihang/lanlandeku`（唯一分支 main） |
| 正式站 | `https://fzpaihang.github.io/lanlandeku/`（Pages，源=main 根目录，30–90 秒缓存） |
| APK 热更版本 | **v56** |
| 分区数 | **6**（苍松/白鹤/丹凤/墨羽/4399/应用汇） |
| 索引人数 | ~599 |
| 本地工作区 | `E:/workbuddy2/fzjh-rank` |
| 临时文件 | `E:/workbuddy2/_agent_tmp` |
| token | `E:/workbuddy2/_agent_tmp/gh_token.txt` |

---

## 六个分区

| key | 名称 | channel | maxRank | UID 前缀 |
|---|---|---|---|---|
| `taptap` | 苍松迎客 | taptap | 不限（~98） | **8 位及以下** |
| `taptap_2` | 白鹤亮翅 | taptap_2 | **20** | 18 |
| `taptap_3` | 丹凤朝阳 | taptap_3 | **30** | 21 |
| `taptap_4` | 墨羽惊鸿 | taptap_4 | 不限（~99） | 22 |
| `4399` | 4399 | 4399 | 50 | 4 |
| `yyh` | 应用汇 | yyh | **20** | 6 |

**位数优先于前缀**：`4168426`（7 位、4 开头）属于苍松，不是 4399。

未收录前缀（留档）：5 当乐 / 7 啪啪 / 9 其他 / 10 华为 / 11 oppo / 12 vivo / 13 应用宝 / 14 小七 / 20 小米

---

## 定时任务（`.github/workflows/refresh.yml`）

| cron (UTC) | 北京时间 | 分区 |
|---|---|---|
| `0 22 * * *` | 次日 06:00 | 苍松 |
| `55 15 * * *` | 23:55 | 白鹤 + 丹凤 |
| `0 20 * * *` | 次日 **04:00** | **应用汇** |
| `0 4 * * *` | 12:00 | 墨羽 |
| `0 10 * * *` | 18:00 | 4399 |

- `timeout-minutes: 60`（六区全量约 33 分钟）
- `concurrency: fzjh-data`，`cancel-in-progress: false`
- 手动触发：`mode=probe|board|full`，`server=all|<key>`

---

## 关键设计（改代码前必看）

### 1. 热更机制
`main.py` 启动 → 比对 `apk/update/version.json` → 下载 `code.zip` → md5 → **Ed25519 验签** → 解压到 `files/live/` → 插到 sys.path。

**版本号只升不降**。`main.py`、`names.json`、字体、图标、Java 层不在热更范围。

### 2. 分区凭据走私有 gist
凭据不能进公开仓库（Pages 源是 main 根目录）。所以：
```
私有 gist servers.json（6 区凭据）
  → APK 启动用内置 gh.json token 拉
  → files/servers-remote.json（6h TTL）
  → 优先级高于 APK 内置 config.json
```
gist id：`91b6a13fa2cc94584a6647ce57b260f9`

**新增分区不必重打 APK**：改 gist + 改 CI Secret `FZJH_SERVERS` 即可。

⚠️ 拉 gist **不能用** `fetch.F.ctx`（那是游戏接口的最小 CA 包），校验 `api.github.com` 会 `CERTIFICATE_VERIFY_FAILED`。必须用 `ssl._create_unverified_context()`。

### 3. 自动识别分区
`lookup_core.server_of_uid()` 按上表前缀直接定位，**只发 1 次请求**（原来要试 2–3 个）。命中区查不到会落回轮询。

### 4. 经验快照口径
`exp-history.json` 的 `snapshots[]` **只认 `src === 'profile'`**。
`exp.js` 已加过滤：`filter(s => s.src === 'profile')`。

排行榜浮点值和档案整数值**不能混算**，否则出现假增量/负增长。

### 5. 武学等级
`lv = min(1100, ceil(((exp - 1) / 0.015) ** (1/3)))`

三处**活代码**需同步：`apk/lookup_core.py`、`scripts/fetch_profiles.py`、
`worker/src/profile.js`（未上线，仅本地）。第四处 `api/build/staging/lookup_core.py`
是**构建产物**，跑 `build_api_zip.py` 自动跟随，不要手改。

⚠️ `assets/profile.js` **不做等级换算**，只显示档案里的 `lv`（旧版本这里记错了）。
自检：`python scripts/preflight.py` 会比对两处数值，并在 staging 过期时告警。

### 6. 隐私名单
`data/hidden.json` 4 人：玲珑望月(4047491326) / 微生念(4168426) / 微生梦(6622657) / 咸味桃酥(21079748748)。
链路：榜单剔除 → 索引过滤 → 档案删除 → APK 查询前拦截。

---

## 改动后的必做步骤

| 改了什么 | 必须做什么 |
|---|---|
| 任何改动 | `python scripts/preflight.py`（语法/缓存戳/热更包/等级/names/隐私一次跑完） |
| `assets/*.js` / `style.css` | **`python scripts/stamp_assets.py`**（否则 WebView 用缓存） |
| `apk/*.py` | `python -m py_compile` → `scripts/pack_update.py "说明"` → 推 `code.zip`+`version.json` |
| `config.json`（加分区） | 更新 gist + CI Secret `FZJH_SERVERS` |
| `data/**` | 一般由 CI 自动提交 |

**发布方式**：`python scripts/publish.py "说明" 文件...`（`--check` 先预览）。
固定走 GitHub REST API（`blob → tree → commit → PATCH refs`），自动带 `base_tree`、
自动跳过无变化文件、强制 `code.zip`+`version.json` 成对、拒绝敏感文件。
**不要 `git push`**（本地 git 与远端长期分叉）。

**看本地与线上差在哪**：`python scripts/check_drift.py`（按 git blob 比对，能区分仅换行差异）。

**网络**：urllib 要 `ProxyHandler({})`；curl 访问 github.io 要 `--noproxy '*' `。

---

## 环境

| 项 | 值 |
|---|---|
| Python（跑项目脚本） | `D:\Programs\Python\Python38\python.exe`（有 Crypto/pycryptodome） |
| Python（Office 运行时） | `E:\DSHdeepseek\...\office-runtime\...\python.exe`（**没有** Crypto） |
| adb | `D:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe` |
| 模拟器 | `-s 127.0.0.1:7555`（PowerShell 里必须用数组 `@('-s','127.0.0.1:7555')`） |
| 包名 | `com.fzjh.fzjhlookup` |
| 分区凭据提取 | 对应游戏包的 `shared_prefs/extends.xml`(`fzjh_uuid`) + `Cocos2dxPrefsFile.xml`(`userid`) |
| 模拟器提权 | `adb root`（`run-as` 对非 debuggable 包无效） |

---

## 已知隐患（不改，仅记录）

1. `data/cangsong-5zhuan.json` `count=7787` 但 `players=7785`（历史删人没更新 count，不影响功能）
2. `assets/lookup.js` 是死代码（`worker/src/lookup.js` 才是活的）
3. 两份 `names.json`（`data/` 与 `apk/`）无同步机制，当前内容一致（md5 `8325e44d8a1a`）
4. ~~`merge-exp.yml` 没有 artifact 兜底~~ → **已修**（2026-11-15，与 `refresh.yml` 一致）

---

## 文档地图

| 文档 | 内容 |
|---|---|
| `docs/代码流程梳理.md` | **代码地图、重复实现、僵尸产物、待改造清单**（改动前先看） |
| `docs/APK修改操作手册.md` | APK 全部操作（热更/重打包/签名/模拟器验证） |
| `docs/网页维护操作手册.md` | 网页+数据链路，§14 是已知隐患清单 |
| `docs/UI优化-实施记录.md` | v30–v56 每次改动推理 |
| `docs/武学分类校对表.md` | 武学分组人工校对 |
| `.workbuddy/memory/2026-11-14.md`、`2026-11-15.md` | 逐日结论 |

---

## 最近完成（按版本）

| 版本 | 内容 |
|---|---|
| v46 | 蓝色水滴残影（Kivy `use_handles=False`） |
| v47 | 11 项界面/数据问题 |
| v48 | 三处视觉微调 |
| v49 | 查过的角色可搜（本机补录）+ 服务端索引合并 `extra-names`（全局共享） |
| v50 | 修标记闪退（markup `size` 必须整数） |
| v51/v52 | 武学搜索覆盖层对齐、填入文字色、展开保持位置 |
| v53 | 自动识别分区单请求 |
| v54/v55 | **应用汇接入** + 分区配置走私有 gist |
| **v56** | 网页/Worker 武学等级改 ceil + 封顶 1100 |
| 数据 | 应用汇首百昵称补录；修经验快照混口径（删 `src=None`） |
| 工具 | 2026-11-15：`preflight` / `publish` / `check_drift` / `plan_refresh`；CI 映射抽脚本、merge-exp 补 artifact、删重复 `api/index.py` |
