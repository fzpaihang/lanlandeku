# 项目当前状态（交接用）

> 这份文件代替「翻聊天记录」。**新会话先读它，再按需读具体文档**。
> 最后更新：2026-11-19 16:12（**数据链路：索引每轮重建 + 掉榜数据保留**——①`refresh.yml` 在 merge_exp 之后新增「重建昵称索引」step（`if: schedule || inputs.mode == 'full'`），新上榜的人当轮就能按昵称搜到，不再等周一；②`scripts/fetch_profiles.py` 新增 `prune_profiles()`（`KEEP_DAYS = 30`），掉榜档案保留 30 天、超期才删，回归后仍可查；③`scripts/merge_exp.py` 快照 exp_map 追加「继承掉榜」段（`prev_map` 里本轮不在榜、且档案仍在的 uid 原值带入，`carried` 计数），回归后 3 天基准不再缺值；④本地重建索引 956→**957**，并补回墨羽惊鸿 5 个掉榜者档案 + 最新快照 exp。提交 `f6afa3e9aee4`。上一条 15:50（**热更 v81：APK 收藏功能**——结果页底栏「收藏/已收藏」、查询页「我的收藏」卡（最多 50 人，点行填入、点「移除」删除），只存 uid/name/server/serverName/at 四字段到 `lookup_cache.json` 的 `favorites`，隐私名单拦截；**修经验快照污染**——`scripts/merge_exp.py:129` 的 `prev_map` 原来取 `snaps[-1]`，而 `scripts/fetch.py` 会先写一条 `src="board"` 的本轮榜单快照，导致未刷新者被回填成榜单旧值（taptap_4 11-18 12:50 那条 100 人里 65 人被污染、30 人经验倒退、11-21 当天 61 人增幅合计虚高 +1889 万），改成倒序取第一条 `src` 为 None 或 `profile` 的快照，并把那 65 个值里可从 11-17 快照回填的 61 个修正（另 4 个是 11-18 新进榜者，保留首个榜单值）；顺带清掉 5 个已下线但磁盘残留的墨羽惊鸿孤儿档案。包 = 202,552 B / md5 `f3b38d8fed4c…`，提交 `279e2360735d`。上一条 12:52（网页文案：`lookup.html` 下载按钮包体 22.6→**23.6 MB**，与 release 资产 24,728,132 字节实际一致；提交 `5bed56da9b02`。上一条 11:05：校准：索引人数 955→**956**，与 `data/lookup-index.json` 实际 count 对齐；数据已对齐远端 `8f72d82`，清掉 4 个下榜残留档案。上一条 11-18 18:40，热更 v80：多昵称索引 `aliases`（改名后旧名照样搜得到）、昵称候选上限 8→20、iOS 三区榜单/档案/快照只跑前 50（索引 1104→956）。上一条 v79：榜单等级 `lv` 改为按实时经验反算（原始榜单值存 `lvBoard`），并去掉手动的「等级」排序——等级由经验唯一决定。另有 v78：人物等级反算改用游戏原式 `exp = 0.1×(lv+4)³`，按整数区间回代——11 区 715 条榜单样本 100% 命中、最大偏差 0 级，preflight 第 6 项因此从「99.0%」收紧到「<99% 即 FAIL」）

---

## 一分钟速览

| 项 | 值 |
|---|---|
| 仓库 | `fzpaihang/lanlandeku`（唯一分支 main） |
| 正式站 | `https://fzpaihang.github.io/lanlandeku/`（Pages，源=main 根目录，30–90 秒缓存） |
| APK 热更版本 | **v81** |
| 分区数 | **11**（苍松/白鹤/丹凤/墨羽/4399/应用汇/其他服/华为/**老马识途**/**野马分鬃**/**仙人指路**） |
| 索引人数 | **957**（iOS 三区自 v80 起各 50；每轮抓取后自动重建） |
| 本地工作区 | `E:/workbuddy2/fzjh-rank` |
| 临时文件 | `E:/workbuddy2/_agent_tmp` |
| token | `E:/workbuddy2/_agent_tmp/gh_token.txt` |

---

## 十一个分区

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
| `ios1` | **老马识途**（iOS 一区） | ios | **50** | **30** |
| `ios2` | **野马分鬃**（iOS 二区） | **fzjh** | **50** | **8** |
| `ios3` | **仙人指路**（iOS 三区） | **fzjh3** | **50** | **19**（11 位） |

**位数优先于前缀**：`4168426`（7 位、4 开头）属于苍松，不是 4399。

未收录前缀（留档）：5 当乐 / 7 啪啪 / 11 oppo / 12 vivo / 13 应用宝 / 14 小七 / 20 小米

其他服是官方合服（`payChannel=guanfang`），uid 一律 **9 开头 10 位**；华为端（包名 `com.xhtt.app.fzjh.huawei`）uid **10 开头 11 位**。两者都没混入老服号。

### iOS 分区（v69 起）

iOS 与安卓不是同一个域名，靠 **三件套一起配**才能握手，缺一个都 500：

| 配置项 | 值 | 写在哪 |
|---|---|---|
| `domain` | `https://ios.fzjh.xiaohoutiaotiao.com` | `config.json` 该分区条目 / gist |
| `platform` | `ios` | 同上 |
| `channel` | **每个区不一样**：老马识途 `ios` / 野马分鬃 `fzjh` / 仙人指路 `fzjh3`；填错就 500 | 同上 |

- 代码侧：`scripts/fetch.py` 的 `DOMAIN_IOS` + `domain_of(cfg)`；`platform != "android"` 时不发 `pkname`/`pksig` 两个头。`apk/fetch.py` 同款。
- **`switch_partition/1|2|5` 切不了数据**：返回 `errcode 0` 但榜单仍是同一批人，一个凭据只固定绑一个区。
- iOS 三个区号段互不重叠：**老马识途 3 开头 10 位 / 野马分鬃 8 开头 10 位 / 仙人指路 19 开头 11 位**，三个都已在 `UID_PREFIX_SERVER`。
- iOS 门派比安卓多（老马识途 28 个 / 野马分鬃 26 个 / 仙人指路 25 个）。老马识途榜首 罪惘生 4292 级 79.34 亿，高于安卓全八区榜首；野马分鬃榜首 天气预报（丐帮）3955 级 62.24 亿；仙人指路（新区）榜首 西索（虚渺宫）3462 级 41.65 亿。

---

## 定时任务（`.github/workflows/refresh.yml`）

| cron (UTC) | 北京时间 | 分区 |
|---|---|---|
| `0 22 * * *` | 次日 06:00 | 苍松 |
| `55 15 * * *` | 23:55 | 白鹤 + 丹凤 |
| `0 20 * * *` | 次日 **04:00** | **应用汇 + 老马识途** |
| `0 4 * * *` | 12:00 | 墨羽 |
| `0 10 * * *` | 18:00 | 4399 |
| `0 8 * * *` | 16:00 | 其他服 |
| `0 18 * * *` | 次日 **02:00** | **华为** |
| `0 0 * * *` | 当日 **08:00** | **野马分鬃**（iOS 二区） |

- `timeout-minutes: 60`（十一区全量约 60 分钟）
- `concurrency: fzjh-data`，`cancel-in-progress: false`
- 手动触发：`mode=probe|board|full`，`server=all|<key>`

**昵称索引有三条重建入口**（`data/lookup-index.json` 是「昵称 → uid」静态表，只有 APK 读，不参与榜单展示与经验计算）：

1. **主力路径**：`refresh.yml` 每轮抓完后自动重建（step「重建昵称索引」，`if: schedule || inputs.mode == 'full'`），新上榜的人当轮就能按昵称搜到。
2. `lookup-index.yml` 事件驱动：APK 归档新昵称（`data/extra-names.json`）push 后自动重建。
3. `lookup-index.yml` 每周一 04:00 兜底 + 手动触发。

**加分区、改 `hidden.json`、补 5 转表之后仍必须手动跑一次**。
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
| 查询页状态条「手动刷新昵称索引 · 时间」+「刷新」按钮（v65 起不显示人数） | `app_ui.py::_index_card()` / `_refresh_index()` |
| `refresh_async()` 强制联网、绕过 6h | `names_index.py`（`_load_blocking(force=True)`） |
| `info()` 在后台线程未跑完时同步读缓存兜底 | `names_index.py`（避免状态条一直显示「未加载」） |
| `lookup-index.yml` 加 `push: paths: data/extra-names.json` | 有人归档新昵称就自动重建索引 |

**共享闭环**（已端到端验证 11-15 21:12）：
App 查 UID 成功 → `apk/archive_local.py` 用 PAT 写 `data/extra-names.json`
→ push 触发 `lookup-index.yml` → `build_lookup_index.py` 合并 → 所有人点「刷新」即可搜到。
实测：查华为榜首 `10045041213` → extra-names 322→323 → 工作流 `43717805794`（push，success）
→ 索引 799→800 人。

**多昵称索引（v80 起）**：`data/extra-names.json` 每条可带 `a`（旧昵称数组，最多 3 个）。
`scripts/build_lookup_index.py` 把 `a` 汇总成索引顶层 **`aliases`**
（`[[uid, 旧昵称, server, serverName, lv], ...]`），`apk/names_index.py` 的 `_parse_aliases()` 读它、
`_search_rows()` 把「当前名 ∪ 历史名」一起搜。改名后旧名照样能搜到同一个 UID。
首个实例：`22039038872` 原名「无名氏」→ 索引成 **陆云**，`a = ["无名氏", "段潇"]`。
**改完必须重建索引并发布 `data/lookup-index.json`**，设备端还要删 `files/lookup-index.json` 再重启（6h 缓存）。

索引只收**当前榜 + `index-extra.json` + `extra-names`**，不收掉榜者——掉榜的人从索引里消失是按名次搜不到，但档案和快照仍保留（见 §4.1），改回榜后新一轮重建会重新收进来。

昵称候选上限：`apk/app_ui.py` 两处 `NI.search(..., 20)`（v80 由 8 提高；索引里「无名氏」有 10 个）。

> 归档侧必须用 PAT（`GH_TOKEN_APK`）：`GITHUB_TOKEN` 产生的 push 不会触发 Actions，
> 换成默认 token 会把这条链路悄悄断掉。

### 1.3 传承历程的 0 转（v66 / v67）

`inheritHistory` 每一条是一次**传承事件**：`parentName` = 上一世，`inheritName` = 这一世。
5 条 = 5 次传承，链条上应有 **6 个名字**（0 转初代 + 1~5 转）。

- `parse_profile()` 必须同时保留 `p`（`parentName`），否则 APK 会比网页少一世（v65 以前的 bug）。
- `_timeline_card()` 链首补编号 `0` 的一行，日期列留空（初代没有传承时间）；
  `p` 缺失时显示占位「初代」，与网页 `profile.js` 同口径。
- `PROFILE_VER` 是档案缓存的结构版本，**结构变了就 +1**（v67 起是 3）。不 bump 的话，
  10 分钟 TTL 内的旧缓存会让 0 转一直显示占位「初代」。

### 2. 分区凭据走私有 gist
凭据不能进公开仓库（Pages 源是 main 根目录）。所以：
```
私有 gist servers.json（11 区凭据，**必须是 {"servers": [...]} 字典**）
  → APK 启动用内置 gh.json token 拉
  → files/servers-remote.json（6h TTL）
  → 优先级高于 APK 内置 config.json
```
gist id：`91b6a13fa2cc94584a6647ce57b260f9`

**新增分区不必重打 APK**：改 gist + 改 CI Secret `FZJH_SERVERS` 即可。

⚠️ **v75 起这两处一律用 `python scripts/sync_creds.py --apply` 写**（`--check` 只打印掩码摘要）。
历史两次事故都是手写格式错：gist 写成裸数组 → APK 静默拉不到配置，只表现「该分区未找到」；
Secret 写成裸数组 → `build-apk.yml` 注入步骤抛 `AttributeError: 'list' object has no attribute 'get'`，
**云端构建连挂 6 次**（下载页一直挂旧包，11-17 → 11-18 才发现）。现在两边都有兼容层兜底，但别依赖它。

⚠️ 拉 gist **不能用** `fetch.F.ctx`（那是游戏接口的最小 CA 包），校验 `api.github.com` 会 `CERTIFICATE_VERIFY_FAILED`。必须用 `ssl._create_unverified_context()`。

### 3. 自动识别分区
`lookup_core.server_of_uid()` 按上表前缀直接定位，**只发 1 次请求**（原来要试 2–3 个）。命中区查不到会落回轮询。
`UID_PREFIX_SERVER` 现有 11 行，含 `("30", "ios1")`（老马识途，10 位 3 开头）、`("8", "ios2")`（野马分鬃，10 位 8 开头）、`("19", "ios3")`（仙人指路，11 位 19 开头）；`order_servers()` 的 10 位与 11 位兜底猜测列表都要带上对应 key。

### 3.1 加一个分区要同步 7 处（原写 5 处，v69 实测修正；v70、v71 再核仍是 7 处）

1. `config.json` 的 `servers` 数组（gitignored，本地）
2. 私有 gist `91b6a13fa2cc94584a6647ce57b260f9` 的 `servers.json` + CI Secret `FZJH_SERVERS`（PyNaCl SealedBox 重写）
3. `apk/lookup_core.py:354` 的 `UID_PREFIX_SERVER`
4. `apk/app_ui.py:1996-1999` 的 `_servers()` 兜底列表
5. `scripts/plan_refresh.py` 的 `SCHEDULE_MAP` + `LABELS`
6. `.github/workflows/refresh.yml` 的 `server` 选项 + cron 注释；`merge-exp.yml` 的 `server` 选项
7. `scripts/build_lookup_index.py:98-101` 的兜底名字表

`data/servers/index.json` 由 `scripts/fetch.py` 的 `write_index()` 自动生成，`assets/servers.js` / `assets/exp.js` 自动读，**不用手改**。
最后手动跑一次索引重建（`lookup-index.yml`），否则新服的人按昵称搜不到。

### 4. 经验快照口径
`exp-history.json` 的 `snapshots[]` **只认 `src === 'profile'`**。
`exp.js` 已加过滤：`filter(s => s.src === 'profile')`。

排行榜浮点值和档案整数值**不能混算**，否则出现假增量/负增长。

现在 `fetch.py` 写快照时会显式标 `src: "board"`（以前是不写该字段），再由
`merge_exp.py` 用档案值覆盖成 `src: "profile"`。这样「第一次抓排行榜的落后值」
即使因为档案抓失败而残留，也进不了增长基准——基准只会是档案口径的快照。

### 4.1 掉榜的人不再丢数据（2026-11-19 起）

以前掉榜 = 档案被删 + 快照里 exp 消失，之后再上榜时 3 天基准取不到值、经验变化显示「—」。现在三层都改：

| 层 | 位置 | 行为 |
|---|---|---|
| 档案 | `scripts/fetch_profiles.py` 的 `prune_profiles()`（`KEEP_DAYS = 30`） | 掉榜但 `updatedTs` 在 30 天内 → 保留；超期没再上榜才删。读不到 `updatedTs` / JSON 坏的一律保留。**`not fail` 保护照旧**（抓取失败整轮不清理） |
| 快照 | `scripts/merge_exp.py` 的「继承掉榜」段 | `prev_map` 里本轮不在榜、**且档案文件还在**的 uid，原值带进 `exp_map`（`carried` 计数，汇总行打印「继承掉榜 N」）。档案被 prune 掉后就不再继承，快照体积自然收敛 |
| 索引 | `scripts/build_lookup_index.py` | 仍只收当前榜 + `index-extra` + `extra-names`；掉榜者从索引消失，但回归后下一轮重建会自动收回来 |

`fresh` 字段仍只统计本轮真正用档案值的人数，不带继承者，所以它继续是「本轮刷新率」的口径。

### 4.2 昵称索引每轮重建（2026-11-19 起）

`refresh.yml` 在「合并档案经验」之后、「提交数据」之前加了一步 `python scripts/build_lookup_index.py`，
条件 `if: (github.event_name == 'schedule') || (inputs.mode == 'full')`。索引 `updatedAt` 每轮都会变，跟着同一批 `git add -A data` 一起提交。
`lookup-index.yml` 保留事件驱动（`extra-names.json` push）与每周一 04:00 兜底。

### 5. 武学等级
`lv = min(1100, ceil(((exp - 1) / 0.015) ** (1/3)))`

三处**活代码**需同步：`apk/lookup_core.py`、`scripts/fetch_profiles.py`、
`worker/src/profile.js`（未上线，仅本地）。第四处 `api/build/staging/lookup_core.py`
是**构建产物**，跑 `build_api_zip.py` 自动跟随，不要手改。

⚠️ `assets/profile.js` **不做等级换算**，只显示档案里的 `lv`（旧版本这里记错了）。
自检：`python scripts/preflight.py` 会比对两处数值，并在 staging 过期时告警。

### 6. 隐私名单
`data/hidden.json` **5 人**：玲珑望月(4047491326/4399) / 微生念(4168426/taptap) / 微生梦(6622657/taptap) /
咸味桃酥(21079748748/taptap_3) / **药乐(19035702184/ios3，v76 新增)**。
链路：榜单剔除 → 索引过滤 → 档案删除 → APK 查询前拦截（`app_ui.HIDDEN_UIDS` + `lookup_core.HIDDEN_UIDS_LOCAL` 两份兜底，
`preflight` 校验三份副本一致）。**远端那份档案要 `publish.py "说明" 文件... --delete data/servers/<key>/profiles/<uid>.json`**，
只删本地的话直链仍可访问。

---

## 改动后的必做步骤

| 改了什么 | 必须做什么 |
|---|---|
| 任何改动 | `python scripts/preflight.py`（**11 项**：语法/缓存戳/热更包/等级/等级(人物)/names/隐私/隐私三副本/字段级隐藏/经验快照窗口） |
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
| 模拟器 | 多实例：`127.0.0.1:16384`（普通区）/ `16416`（华为端）；端口从 `vms/*/configs/vm_config.json` 读，别硬编码 |
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
| **`docs/接手必读.md`** | **新会话入口**：30 秒状态、任务→命令、十条铁律、交接自检 |
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
| 数据 | **2026-11-19 16:12 索引每轮重建 + 掉榜数据保留**：<br>①`refresh.yml` 在 merge_exp 后新增「重建昵称索引」step（`if: (github.event_name == 'schedule') || (inputs.mode == 'full')`，`run: python scripts/build_lookup_index.py`），原「不在这里重建」注释段删除；`lookup-index.yml` 顶部注释与 `scripts/build_lookup_index.py` docstring 同步改成「三条重建入口」（每轮刷新 / extra-names 事件 / 每周一兜底）。<br>②`scripts/fetch_profiles.py` 新增模块级 `prune_profiles(out_dir, targets, now=None)` + `KEEP_DAYS = 30`：掉榜但 30 天内更新过 → 保留（回归后仍可查），超期才删，`updatedTs` 缺失或 JSON 坏一律保留；原「直接删掉所有不在 targets 的 .json」整块替换，`not fail` 保护保留。<br>③`scripts/merge_exp.py` 快照段在 `exp_map` 循环后追加「继承掉榜」：`have_prof` 取自 profiles 目录现存文件名，`for uid_s, v in prev_map.items(): if uid_s not in exp_map and (not have_prof or uid_s in have_prof)` 则带原值并 `carried += 1`；汇总行加「继承掉榜 %3d」。<br>④`data/lookup-index.json` 本地重建 956→**957 名玩家**（新收 林沫泠 22039035325 / 白剑小白 22039042793 等 6 人，去掉已掉榜 5 人；5 转 7685）。<br>⑤`data/servers/taptap_4/exp-history.json` 最新快照 100→**105 人**（补回 5 个掉榜者 exp，`fresh` 仍 100）；`data/servers/taptap_4/profiles/` 从 git `3752754^` 逐字节还原 5 份掉榜档案（月朔 22039002682 / 混沌毁灭 22039026462 / 秦可卿 22039028414 / 如梦令 22039030225 / 燕归梁 22039061175）。<br>验证：`prunetest`（边界 29 保留 / 30 保留 / 31 删除）、`carrytest`（有掉榜=1 / 无=0）、真数据副本 11 区仅 taptap_4「继承掉榜 5」；`preflight` 10 通过 / 2 警告 / 0 失败。提交 `f6afa3e9aee4` |
| v81 | **APK 收藏功能 + 修经验快照污染**：<br>`apk/lookup_core.py` 新增 `FAV_MAX = 50` / `favorites()` / `is_favorite()` / `add_favorite()` / `remove_favorite()` / `toggle_favorite()` / `refresh_favorite()`，存 `load_cache()["favorites"]`，每条 `{uid,name,server,serverName,at}`——只存四字段，不存整份 profile（一份带 skills/equips 有几十 KB）；`HIDDEN_UIDS_LOCAL` 内的 uid 加不进也不显示。<br>`apk/app_ui.py`：结果页底栏三控件（收藏/已收藏 · 导出 · 再查一个），新增 `_is_fav()` / `_toggle_fav()` / `_fav_card()` / `_drop_fav()`；`_set_foot(on, exportable=None)` 的默认值从 `True` 改成 `None` 并在函数内按 `p.get("_board")` 现算，因为 `_relayout()` 旋转会重调 `_set_foot(True)`；查询页在最近查询卡与入口卡之间插「我的收藏」卡（为空则整张卡不出现）；`_done()` 里 `L.refresh_favorite(prof)` 让改名后收藏仍显示新昵称。榜单兜底页数据残缺，不给收藏与导出。<br>**快照污染**：`scripts/merge_exp.py:129` 的 `prev_map = (snaps[-1].get("exp") or {}) if snaps else {}` → 倒序取第一条 `src is None or src == "profile"` 的快照。起因是 `scripts/fetch.py:275-325 update_history()` 本轮先写入一条 `src="board"` 的快照，`snaps[-1]` 于是是榜单旧值，`elif uid_s in prev_map` 把未刷新者回填成榜单里的浮点经验。实测污染 `data/servers/taptap_4/exp-history.json` 的 2026-11-18 12:50 那条（`fresh=35` / 100 人，65 个浮点值且 65/65 等于旧榜 `expBoard`、`expSrc` 全为 `board`）；影响时点精确到 **2026-11-21 当天**（`WINDOW_DAYS=3` 基准正好命中该条），届时 61 人增幅失真、合计 +18,890,942；11-22 起窗口滚过自愈。已回填 61 个值并取整，另 4 人（沐白歌 22039060705 / 久恒 22039039979 / 念卿一梦 22039044797 / 心随云往 22039060095）11-17 榜与快照均无记录，是新进榜者，保留首个榜单值。修后：非整数 0 / 经验倒退 0 / 11-21 偏差 0。<br>另删 5 个磁盘残留孤儿档案（`taptap_4/profiles/` 下 22039002682 / 22039026462 / 22039028414 / 22039030225 / 22039061175，HEAD `3752754` 已删但本地未清）。`preflight` 10 通过 / 2 警告 / 0 失败。包 = 202,552 B / md5 `f3b38d8fed4c…`，提交 `279e2360735d` |
| 文案 | **2026-11-19 网页文案校准**：`lookup.html:65` 下载按钮「下载 App（22.6 MB）」→ **23.6 MB**。实测 release `apk-v1.0` 的 `fzjh-lookup-v1.0.apk` = 24,728,132 字节（GitHub 资产区显示 23.6 MB，MiB 口径），旧文案差了约 1 MB。纯 HTML 文本改动，不涉及 JS/CSS，无需 `stamp_assets.py`；`preflight` 11 通过 / 1 警告 / 0 失败；`publish.py` 提交 `5bed56da9b02`，线上 `lookup.html` 已生效 |
| v46 | 蓝色水滴残影（Kivy `use_handles=False`） |
| v47 | 11 项界面/数据问题 |
| v48 | 三处视觉微调 |
| v49 | 查过的角色可搜（本机补录）+ 服务端索引合并 `extra-names`（全局共享） |
| v50 | 修标记闪退（markup `size` 必须整数） |
| v51/v52 | 武学搜索覆盖层对齐、填入文字色、展开保持位置 |
| v53 | 自动识别分区单请求 |
| v54/v55 | **应用汇接入** + 分区配置走私有 gist |
| **v56** | 网页/Worker 武学等级改 ceil + 封顶 1100 |
| v57 | 新增第七区「其他服」（榜前 50 / 索引前 100 / 16:00） |
| v58 | 新增第八区「华为」（榜前 50 / 索引前 100 / 次日 02:00） |
| v59/v60 | **榜单兜底**：查询失败可显示榜单快照（默认关闭，结果页右上角开关） |
| v61–v64 | 昵称索引状态条 + 手动刷新；归档 push 自动重建索引 |
| v65 | 索引状态条文案精简（提示与状态条都不再显示人数） |
| v66/v67 | **传承历程补 0 转（初代）**，`PROFILE_VER` 2→3 |
| v68 | 输入框有内容时收掉「请输入昵称或 UID」红字；经验日均分母 `max(3天,实际区间)`；补回墨羽惊鸿 11-14 快照；`preflight` 加第 8 项经验快照窗口检查 |
| v69 | **新增第九区「老马识途」（iOS 一区）**：协议加 `domain`/`platform` 两个可配项（`DOMAIN_IOS` + `domain_of()`），UID 30 前缀自动识别，定时 4 点与应用汇同批，索引 904 人 |
| v70 | **新增第十区「野马分鬃」（iOS 二区，`channel=fzjh`）**：UID 8 前缀自动识别，定时 **8 点**单独一批（cron `0 0 * * *`），索引 1003 人 |
| v71 | **新增第十一区「仙人指路」（iOS 三区，`channel=fzjh3`）**：UID 19 前缀 11 位自动识别，定时 **10 点**单独一批（cron `0 2 * * *`），索引 1104 人 |
| v72 | **字段级隐藏**（`data/hidden-fields.json`）：人还在榜上只清指定字段，与 `hidden.json` 整条剔除是两套机制；魔渊 `19035589937`（ios3）藏掉 skills/prepared/newSkills。**档案弹窗新增「经验快照」表**（`FZJH.appendSnapshots` + `loadSnapshots` + `PF_SEQ`），列该玩家每次扫描的时间/经验/比上次。`preflight` 加第 9 项字段级隐藏检查 |
| v76 | **隐私名单新增「药乐」**（ios3 `19035702184`，整条剔除）：`data/hidden.json` 5 人、`apk/app_ui.py::HIDDEN_UIDS` 与 `apk/lookup_core.py::HIDDEN_UIDS_LOCAL` 两份兜底同步；ios3 榜单 100→99 行重排名次、档案与快照条目删除、`extra-names.json` 337→336、索引 1104→1103；远端旧档案用 `publish.py --delete` 删除 |
| v75 | **分区凭据同步固化**：新增 `scripts/sync_creds.py`（`--check` / `--apply` / `--gist-only` / `--secret-only`），把 `config.json` 一次写进私有 gist（`{"servers": [...]}` 字典，写完回读校验）与 CI Secret `FZJH_SERVERS`（PyNaCl SealedBox 加密整份 config）。`apk/lookup_core.py` 加 `_norm_cfg()`：裸数组自动包成 dict，读不到 servers 时打印提示（原来静默 return False）；`build-apk.yml` 注入步骤兼容 dict / 数组两种 Secret 形状，空配置 `exit 1`。起因是修 11-17 起连续 6 次失败的 APK 云端构建。包 = 199,910 B / md5 `ba8ee82cff92…`，提交 `1ad93e71069b` |
| v77 | **人物等级反算改用游戏原式**：`exp = 0.1×(lv+4)³`，lv 级占据 `[0.1(lv+4)³, 0.1(lv+5)³)` 这段区间，反算走**候选 ±2 区间回代**而不是四舍五入。11 区 715 条 `(lv, expBoard)` **100.00% 命中、最大偏差 0.00 级**（v74 拟合式 99.0%/最大 1 级），20 万个区间内随机点 0 失败，旧公式多报的 9 条全是它更准。preflight 精度阈值同步收紧到「<99% 或 >1 级即 FAIL」。包 = 199,935 B / md5 `de7e7f1d234d…`，提交 `fda844505228` |
| v74 | **人物等级反算公式修正**：`0.100402×lv³` → `0.1×lv³ + 1.35×lv²`。旧公式是纯三次项、只在高等级段准，低等级段系统性偏大 3~4 级（墨羽惊鸿 100 人按 expBoard 反推偏差中位 +3.52，如梦令 888 级被反推成 891）；新公式全库 716 人命中整数等级 **99.0%**、最大偏差 1.0 级，同批严格校验墨羽惊鸿 120 人旧 0% → 新 96%。只影响「榜单没有 lv 时」的兜底反算，显示的等级与名次仍用游戏给的值。`preflight` 新增第 11 项「等级口径(人物)」精度回归。包 = 199,570 B / md5 `565b44a2e52d…`，提交 `cb20f5f7e126` |
| v73 | **代码审查后修 6 处隐患**：`fetch.py` 翻页中途报错整轮作废（不再写残缺榜单、不再级联删档案）；`fetch_profiles.py` 档案原子写 + 失败时不清理旧档；`publish.py` 路径规范化堵住敏感文件绕过（`..`/绝对路径）；`exp.html` 排序键 `exp`→`expN`（原来 100% 失效）；输入框 `'²'` 类字符不再闪退；候选弹窗返回键 + 最近查询隐私过滤。`preflight` 增至 **10 项**，隐私名单校验三份副本（json / app_ui / lookup_core）。包 = 199,011 B / md5 `2834024255a2…`，提交 `c9a994382b73` |
| v80 | **多昵称索引 + 候选上限 20 + iOS 三区只跑前 50**：`data/extra-names.json` 每条可带 `a`（旧昵称数组），`scripts/build_lookup_index.py` 汇总成索引顶层 `aliases`，`apk/names_index.py` 的 `_parse_aliases()` / `_search_rows()` 把「当前名 ∪ 历史名」一起搜——改名后旧名仍能搜到同一 UID（首个实例：`22039038872` 无名氏→**陆云**，旧名 段潇/无名氏）。`apk/app_ui.py` 两处 `NI.search(..., 8)`→`20`（「无名氏」有 10 个，8 个会挤掉目标）。`config.json` 的 `ios1/ios2/ios3` `maxRank` 100→50，`sync_creds.py --apply` 同步 gist + Secret，重抓三区后榜单/档案/快照各 50。包 = 200,547 B / md5 `f3500651cb09…`，提交 `212c2a4fada6` |
| v79 | **榜单等级与经验口径统一**：`lv` 改按实时 `exp` 反算（游戏原始榜单值存 `lvBoard`），等级与经验始终自洽；删掉手动的「等级」排序（等级由经验唯一决定）。新增 `scripts/lv_formula.py` 作为 scripts 侧唯一公式实现（CI 只装标准库，不能复用 `apk/lookup_core.py`）。`apk/lookup_core.py` 的 `parse_profile()` / `board_profile()` 改成「经验反算优先」，`PROFILE_VER` 4→5。11 区 715 行实测不一致从 174 行降到 **0**。包 = 200,180 B / md5 `a76571ece93c…`，提交 `6f6000adc5de` |
| 数据 | 应用汇首百昵称补录；修经验快照混口径（删 `src=None`） |
| 工具 | 2026-11-15：`preflight` / `publish` / `check_drift` / `plan_refresh`；CI 映射抽脚本、merge-exp 补 artifact、删重复 `api/index.py` |
