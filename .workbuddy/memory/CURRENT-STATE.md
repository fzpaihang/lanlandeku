# 项目当前状态（交接用）

> 这份文件代替「翻聊天记录」。**新会话先读它，再按需读具体文档**。
> 最后更新：2026-11-15 14:30（热更 v58，新增第八区「华为」）

---

## 一分钟速览

| 项 | 值 |
|---|---|
| 仓库 | `fzpaihang/lanlandeku`（唯一分支 main） |
| 正式站 | `https://fzpaihang.github.io/lanlandeku/`（Pages，源=main 根目录，30–90 秒缓存） |
| APK 热更版本 | **v64** |
| 分区数 | **8**（苍松/白鹤/丹凤/墨羽/4399/应用汇/其他服/华为） |
| 索引人数 | ~800（其他服、华为各 100 人 + APK 归档） |
| 本地工作区 | `E:/workbuddy2/fzjh-rank` |
| 临时文件 | `E:/workbuddy2/_agent_tmp` |
| token | `E:/workbuddy2/_agent_tmp/gh_token.txt` |

---

## 八个分区

| key | 名称 | channel | maxRank | UID 前缀 |
|---|---|---|---|---|
| `taptap` | 苍松迎客 | taptap | 不限（~98） | **8 位及以下** |
| `taptap_2` | 白鹤亮翅 | taptap_2 | **20** | 18 |
| `taptap_3` | 丹凤朝阳 | taptap_3 | **30** | 21 |
| `taptap_4` | 墨羽惊鸿 | taptap_4 | 不限（~99） | 22 |
| `4399` | 4399 | 4399 | 50 | 4 |
| `yyh` | 应用汇 | yyh | **20** | 6 |
| `guanfang` | 其他服 | guanfang | **50**（索引 100） | **9** |
| `huawei` | **华为** | huawei | **50**（索引 100） | **10** |

**位数优先于前缀**：`4168426`（7 位、4 开头）属于苍松，不是 4399。

未收录前缀（留档）：5 当乐 / 7 啪啪 / 10 华为 / 11 oppo / 12 vivo / 13 应用宝 / 14 小七 / 20 小米

其他服是官方合服（`payChannel=guanfang`），uid 一律 **9 开头 10 位**；华为端（包名 `com.xhtt.app.fzjh.huawei`）uid **10 开头 11 位**。两者都没混入老服号。

---

## 定时任务（`.github/workflows/refresh.yml`）

| cron (UTC) | 北京时间 | 分区 |
|---|---|---|
| `0 22 * * *` | 次日 06:00 | 苍松 |
| `55 15 * * *` | 23:55 | 白鹤 + 丹凤 |
| `0 20 * * *` | 次日 **04:00** | **应用汇** |
| `0 4 * * *` | 12:00 | 墨羽 |
| `0 10 * * *` | 18:00 | 4399 |
| `0 8 * * *` | 16:00 | 其他服 |
| `0 18 * * *` | 次日 **02:00** | **华为** |

- `timeout-minutes: 60`（八区全量约 45 分钟）
- `concurrency: fzjh-data`，`cancel-in-progress: false`
- 手动触发：`mode=probe|board|full`，`server=all|<key>`

**昵称索引不在上面这条链路里**（`lookup-index.yml`，每周一 04:00 + 手动 + **归档 push**）：
`data/lookup-index.json` 是「昵称 → uid」静态表，只有 APK 读，不参与榜单展示与经验计算。
每天重建只会跟着榜单抖动造提交，所以拆出去了。**加分区、改 `hidden.json`、补 5 转表之后必须手动跑一次**。
APK 归档新昵称（`data/extra-names.json`）会自动触发重建，不用等周一。
---

## 关键设计（改代码前必看）

### 1. 热更机制
`main.py` 启动 → 比对 `apk/update/version.json` → 下载 `code.zip` → md5 → **Ed25519 验签** → 解压到 `files/live/` → 插到 sys.path。

**版本号只升不降**。`main.py`、`names.json`、字体、图标、Java 层不在热更范围。

### 1.1 榜单兜底（v59 起，默认关闭）

实时查询失败时，如果开了开关，就用**本地缓存的榜单快照**渲染一张「非实时」结果页，
不跳网页、不打开高手榜。设计要点（用户 11-15 拍板）：

| 项 | 值 |
|---|---|
| 默认 | **关闭**，玩家自己开 |
| 开关位置 | **结果页顶栏右上角**（「榜单兜底 开/关」，和「重新查询」同一行） |
| 开关存储 | `lookup_cache.json` 的 `boardFallback` 键（`L.board_fallback_on()` / `set_board_fallback()`） |
| 数据来源 | `lookup_core.board_profile()` 读 `cache["boardCache"]`，**不发网络请求**；榜单缓存 1 天 TTL |
| 覆盖范围 | 只有上过榜的人；没上榜、缓存为空 → 仍走原来的错误卡 |
| 非实时标识 | 页面顶部「非实时 · 来自高手榜快照」+ 快照抓取时间；顶栏副标题只留 UID |

刻意**不复用** `_render()`：武学、装备、气血榜单里没有，按实时页排会是一屏「—」。
`_render_board()` 只列榜单真有的（等级/武学造诣/经验/名次/传承/分区），并隐藏「导出」按钮。

触发条件：`_done()` 里 `prof is None` 且开关开 → `L.board_profile(self._last_uid, server)` 命中就 `show_result()`。
所以限流、断网、选错分区等**任何失败**都会兜底。`self._last_uid` 在 `_begin()` 里记。

### 1.2 昵称索引的手动刷新与共享闭环（v61 起）

旧逻辑的坑：`names_index.py` 只在**进程冷启动**时检查一次，且要本地缓存 mtime 满
`CHECK_GAP=6h` 才联网（`_started` 一次性标志，无 `on_resume`）。所以加新服之后，
手机常驻后台、或缓存刚下载过，就会一直用旧索引 —— 11-15 用户手机搜不到华为昵称就是这个原因，
**不是索引没生成**（三个下载源当时都是新版）。

| 改动 | 位置 |
|---|---|
| 查询页状态条「索引 N 人 · 时间」+「刷新」按钮 | `app_ui.py::_index_card()` / `_refresh_index()` |
| `refresh_async()` 强制联网、绕过 6h | `names_index.py`（`_load_blocking(force=True)`） |
| `info()` 在后台线程未跑完时同步读缓存兜底 | `names_index.py`（避免状态条一直显示「未加载」） |
| `lookup-index.yml` 加 `push: paths: data/extra-names.json` | 有人归档新昵称就自动重建索引 |

**共享闭环**（已端到端验证 11-15 21:12）：
App 查 UID 成功 → `apk/archive_local.py` 用 PAT 写 `data/extra-names.json`
→ push 触发 `lookup-index.yml` → `build_lookup_index.py` 合并 → 所有人点「刷新」即可搜到。
实测：查华为榜首 `10045041213` → extra-names 322→323 → 工作流 `43717805794`（push，success）
→ 索引 799→800 人。

> 归档侧必须用 PAT（`GH_TOKEN_APK`）：`GITHUB_TOKEN` 产生的 push 不会触发 Actions，
> 换成默认 token 会把这条链路悄悄断掉。

### 2. 分区凭据走私有 gist
凭据不能进公开仓库（Pages 源是 main 根目录）。所以：
```
私有 gist servers.json（8 区凭据）
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

现在 `fetch.py` 写快照时会显式标 `src: "board"`（以前是不写该字段），再由
`merge_exp.py` 用档案值覆盖成 `src: "profile"`。这样「第一次抓排行榜的落后值」
即使因为档案抓失败而残留，也进不了增长基准——基准只会是档案口径的快照。

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
2. ~~`assets/lookup.js` 是死代码~~ → **已删除**（2026-11-15，499 行 / 17 KB，删除前确认零引用）
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
