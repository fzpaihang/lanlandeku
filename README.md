# 放置江湖 · 高手榜

一个纯静态的排行榜查询站：五个分区的高手榜（武学造诣 Top 100），支持搜索、排序、门派筛选、点开玩家完整档案，另有一个「经验变化」页做三日增长对比。

没有后端、没有数据库，数据由 GitHub Actions 每天定时抓取后提交成 JSON，页面直接读。

## 页面长什么样

**高手榜（`index.html`）**

- 桌面（>560px）8 列表格：名次 / 侠名 / 门派 / 等级 / 经验 / 福缘 / 容貌 / 年龄
- 手机（≤560px）自动收成卡片列表：名次 + 侠名 + 转数 / 门派 · 等级 · 经验 · 福缘，一屏十来张
- 点表头排序；昵称、ID、门派都能搜；`?me=你的ID` 高亮自己
- 门派筛选项默认只露 8 个（手机直接收起），点「展开全部 N 个门派」看全量
- 页头分区切换：苍松迎客 / 白鹤亮翅 / 丹凤朝阳 / 墨羽惊鸿 / 4399，选择记在 localStorage
- 点侠名弹档案：12 项基础数值、传承历程（带月份）、准备位、近期新增武学、全部武学（可搜索/展开）、装备
- 有历史榜单时，名次旁显示涨跌（▲2 / ▼1 / NEW）

**经验变化（`exp.html`）**

- 每次抓榜单都记一条经验快照，保留最近 8 天
- 「区间增长」= 最新快照 − 3 天前快照；「日均」= 区间增长 ÷ 3，不足 3 天不显示；「增幅」= 增长 ÷ 基准经验
- 打开时会提示当前对比区间跨度——不足 3 天会明确说明日均为什么不显示

> 排行榜数据只在玩家本人活跃时才刷新，长期不上线的号经验会一直冻着、一上线整块跳变。这是游戏机制，不是抓取 bug。

**玩家查询（`lookup.html`，已停用）**

- 原功能：输入任意 UID，实时拉这个角色的完整档案（等级、门派、气血、加力、传承与装备）
- 2026-11 起暂停：实时查询必须有常驻后端，按量计费约 1–4 元/月，暂不续费
- 页面保留为静态说明，**不加载任何脚本**，输入框和按钮都是 `disabled`
- 恢复步骤见下文「玩家查询为什么停了」

> 排行榜点侠名看的是**快照档案**（随定时任务更新），查询页走的是**实时接口**，两者数字可能不同。

## 目录

```
fzjh-rank/
├─ index.html                 高手榜
├─ exp.html                   经验变化
├─ lookup.html                玩家查询（已停用，仅静态说明）
├─ assets/
│  ├─ style.css               全部样式（含 ≤560px / 561–900px 断点）
│  ├─ servers.js              分区解析、切换器、跨页链接参数
│  ├─ profile.js              玩家档案渲染（详情弹窗 与 查询页共用）
│  ├─ app.js                  高手榜渲染、搜索、排序、详情弹窗
│  ├─ exp.js                  经验页渲染
│  └─ lookup.js               查询页逻辑（当前无页面引用，为恢复预留）
├─ api/
│  ├─ index.py                云函数入口（阿里云 FC / 腾讯云 SCF 通用）
│  └─ build/                  打包产物（gitignored，本地生成）
├─ data/
│  ├─ names.json              技能 / 装备 id → 中文名（一次性生成）
│  ├─ hidden.json             隐私名单：这些 uid 不出榜、不进快照、不生成档案
│  └─ servers/
│     ├─ index.json           分区清单（前端读，不含任何凭据）
│     └─ <key>/               gaoshoubang.json / exp-history.json / profiles/
├─ scripts/
│  ├─ fetch.py                抓榜单 + 记经验快照
│  ├─ fetch_profiles.py       抓玩家档案（含「近期新增武学」比对）
│  ├─ build_names.py          生成中文名映射（换游戏版本后重跑）
│  ├─ build_api_zip.py        打包云函数部署包（api/build/*.zip）
│  ├─ stamp_assets.py         把 html 里的 ?v= 刷成资源内容哈希
│  ├─ summary.py              输出刷新摘要（CI 用）
│  ├─ serve.py                本地预览（正式站不需要）
│  └─ serve_api.py            本地联调：静态站 + /api/query
├─ apk/                       安卓 App：昵称/UID 查实时档案、结果回写昵称库、可跳高手榜
├─ .github/workflows/
│  ├─ refresh.yml             五分区定时抓取
│  └─ build-apk.yml           APK 构建（仅 apk/ 改动时触发）
├─ config.json                本地凭据（★ 已 gitignore，绝不提交）
├─ refresh.bat                双击即刷新，日志写 data/logs/
└─ requirements.txt           CI 依赖
```

## 多分区是怎么工作的

分区由请求头 `channel` 决定，但**每个分区必须有自己的一套 `uuid` + `account`**——服务端会校验账号是否属于该分区，配置错了返回 `500 游戏档案数据不存在`。

| channel | 分区 |
|---|---|
| `taptap` | 苍松迎客 [1服] |
| `taptap_2` | 白鹤亮翅 [2服] |
| `taptap_3` | 丹凤朝阳 [3服] |
| `taptap_4` | 墨羽惊鸿 [新服] |
| `4399` | 4399 渠道服 |

凭据从对应客户端里取（只读）：

- `uuid` ← `/data/user/<N>/com.xhtt.app.fzjh/shared_prefs/extends.xml` 的 `fzjh_uuid`
- `account` ← 同目录 `Cocos2dxPrefsFile.xml` 的 `userid`

> 分身/多开客户端在**另一个 Android 用户空间**（`/data/user/10/…`），主空间读到的 uuid 是另一个分区的，别搞混。
> 4399 端是独立渠道：`uuid` 以 `4399` 开头，`channel` 填 `4399`。

## 数据是怎么来的

游戏客户端本身不存榜单，运行时向服务端按页拉取。抓取脚本复刻了客户端协议：

1. `POST /api/service/exchange_publickey`：用设备 uuid 换本会话的加密密钥
2. `POST /api/v5/get_board/1 {"page":N}`：拿高手榜第 N 页（每页 10 条）
3. `POST /api/v5/get_user_info {"userid":N,"type":0}`：拿单个玩家的完整档案（武学、准备位、装备）
4. 响应是 AES 加密的，解密后剥掉尾部填充字符 `'0'` 才是 JSON

全程不需要开模拟器、不需要抓包、不需要内存转储——只要凭据和 `hotver` 对。

## 跑起来

**依赖**：Python 3.8+、`pycryptodome`

```powershell
pip install pycryptodome
```

**抓一次数据**：

```powershell
python scripts\fetch.py                       # 全部五个区
python scripts\fetch.py --server taptap_3     # 只抓丹凤朝阳
# 或双击 refresh.bat（会写日志）
```

**抓玩家档案**（点侠名能看详情）：

```powershell
python scripts\build_names.py        # 首次或游戏大版本更新后跑一次
python scripts\fetch_profiles.py     # 每个区 100 份，单区约 1 分钟
```

每人存成 `data/servers/<key>/profiles/<userid>.json`，单份约 16 KB，页面点击时才拉取——首屏不会因为详情变大。某个玩家抓失败（已删号、改名等）只会缺他那份，点开时提示读取失败，不影响其他人。

**「近期新增武学」怎么来的**：每次抓档案时把本次武学集合和上一版档案比对，新出现的记为新增，写进 `newSkills`；30 天内一直累计显示。所以：

- 第一次抓（没有上一版）不会把已有武学误判为新增
- 至少跑两次才有意义；没学新武学时该区块不显示
- 玩家掉出榜单再回来，档案被清掉，会重新从零开始记

**本地预览**：

```powershell
python scripts\serve.py 8791
# 打开 http://127.0.0.1:8791/
```

> 不要直接双击 index.html——`file://` 下浏览器会拒绝读取 JSON。

## 改前端之后

资源引用形如 `./assets/app.js?v=c4e19875`，`?v=` 是**文件内容哈希**，改完跑一次即可，不用手动递增：

```powershell
python scripts\stamp_assets.py
```

内容没变时不会改文件，可以放心重复执行。刷新线上后如果还看到旧样式，Ctrl+F5 强刷一次。

## 玩家查询为什么停了

纯静态站调不了游戏接口：接口不返回 CORS 头，浏览器预检直接被拒；而且 `uuid` / `account` 一旦写进前端 JS 就等于公开凭据。所以查询页必须走一层「薄转发」——云函数，凭据只放在函数的环境变量里。

```
lookup.html  →  云函数 /api/query  →  游戏接口（握手 + get_user_info，2 次请求）  →  档案 JSON
```

### 三个方案实测结果（2026-11）

| 方案 | 结果 | 成本 |
|---|---|---|
| 腾讯云 SCF（广州/上海） | 机房出口 IP 被游戏风控，握手后 `errcode=-1` 挂死 | 每月有永久免费额度 |
| 阿里云 FC（杭州） | **可用**，实测首查约 5 秒、缓存命中 0.5 秒 | 按量约 1–4 元/月，无永久免费额度 |
| Cloudflare Workers | 协议层已跑通（1.0 秒），但 `workers.dev` 国内 DNS 被污染、直连不通 | 免费额度够用，但需自有域名（10–60 元/年） |

结论：不产生费用就没有稳定方案，所以网页端暂停。**查询能力已转移到安卓 App**（`apk/`）：直连游戏接口、出口是用户自己的网络，不受机房 IP 风控影响。

### 恢复步骤

1. 打包：`python scripts/build_api_zip.py` → 生成 `api/build/fzjh-lookup-api.zip`（约 74 KB，零第三方依赖，纯 Python AES）
2. 部署到云函数：运行环境 Python 3.9，执行入口 `index.main_handler`，超时 **15 秒**，内存 128 MB
3. 环境变量：

   | 名称 | 值 |
   |---|---|
   | `FZJH_SERVERS` | 和 GitHub Secret 里那个同名值**一模一样**（JSON 数组，含五区 uuid/account/channel） |
   | `FZJH_HOTVER` | 如 `18464`，游戏更新后往上调 |
   | `FZJH_ORIGIN` | `https://fzpaihang.github.io` |

4. 创建免鉴权 HTTP 触发器，复制生成的地址
5. 改 `lookup.html`：填入 `window.FZJH_API_BASE`、取消脚本注释、去掉输入框和按钮的 `disabled`、`#state` 改回「待查询」
6. `python scripts/stamp_assets.py` 后提交

**自检**：浏览器打开 `<函数地址>/api/query?uid=21079748850&server=taptap_3`，应返回 `{"ok":true,...}`。

### 运行约定（恢复后）

- 同一 UID **10 分钟**内复用结果；「查无此人」只压 15 秒
- 前端两次查询至少间隔 **30 秒**，按钮带倒计时
- 云函数每个实例每分钟最多 30 次真实查询
- 自动模式只按 UID 位数猜 **2 个**最可能的区，不轮询五区（五区连打必被限流）
- `hotver` 变了改环境变量即可，不用重新部署代码

### 本地联调（不部署也能验）

```powershell
python scripts\build_api_zip.py --stage-only     # 准备 api/build/staging
python scripts\serve_api.py 8788                 # 静态站 + /api/query 直连 handler
# 打开 http://127.0.0.1:8788/lookup.html?uid=21079729670
```

## 每天自动刷新（GitHub Actions）

`refresh.yml` 里四个计划档位，**每个区每天一次全量**，刻意错开以避开接口限流：

| UTC | 北京时间 | 抓哪个区 |
|---|---|---|
| `0 22 * * *` | 次日 06:00 | 苍松迎客（`taptap`） |
| `0 4 * * *` | 当日 12:00 | 墨羽惊鸿（`taptap_4`） |
| `0 10 * * *` | 当日 18:00 | 4399 |
| `55 15 * * *` | 当日 23:55 | 白鹤亮翅 + 丹凤朝阳（`taptap_2,taptap_3`） |

**为什么拆开**：五区串行全量约 28 分钟，接近单任务超时，而且连续请求容易触发 `20616` 限流。拆开后单次 5–15 分钟。

**实际会比计划晚**：GitHub 的计划任务只保证排队，实测常晚 40–50 分钟，所以网页上看到的更新时间会晚于表上的整点。

**提交数据前会先同步远端**：`git fetch origin main && git rebase FETCH_HEAD` 再 push，失败重试 3 次。这样即使抓取期间有人推了别的 commit，也不会 `fetch first` 被拒、白抓一场。抓取失败时还会把 `data/` 上传成 artifact（保留 7 天），可下载补救。

> 定时任务没有输入参数，workflow 通过 `github.event.schedule` 反查该抓哪个区（比较前会归一化空格）。手动触发可选 `mode`（probe / board / full）和 `server`（all / taptap / taptap_2 / taptap_3 / taptap_4 / 4399）。

### Secrets

仓库 → Settings → Secrets and variables → Actions：

| Name | Value |
|---|---|
| `FZJH_SERVERS` | JSON 数组，一个 Secret 装全部分区凭据：`[{"key":"taptap","name":"苍松迎客","uuid":"...","account":"...","channel":"taptap"}]`（也可直接贴整个 `config.json`） |
| `FZJH_HOTVER` | 如 `18464`，游戏更新后要往上调 |

脚本优先读环境变量，读不到才回退 `config.json`，本地和 CI 共用一套代码。

**开启前先跑一次 `probe`**：runner 在海外、接口在国内，能不能通只有实测知道。`probe` 不打数据、不提交。

## 安卓 App（可选）

`apk/` 是安卓端「按昵称 / UID 查玩家档案」的小工具，Kivy 写的，和网页共用同一套协议代码。查询直连游戏接口，出口是用户自己的网络，不受机房 IP 风控影响。

- **昵称搜索**：启动时后台拉 `data/lookup-index.json`（五区榜单 + 苍松 5 转普查，约 8000 人），本地缓存 6 小时，断网降级为纯 UID 模式
- **结果回写**：查询成功后先写本地 `pending_names.jsonl`，再由后台线程同步进 `data/extra-names.json`；`409` 冲突自动重读重试。凭据由 `GH_TOKEN_APK` 在打包时注入 `apk/gh.json`，不进热更包
- **隐私名单**：`data/hidden.json` 里的 uid 在榜单生成、昵称索引、网页查询、APK 查询四处同时拦截；APK 内置一份 uid 兜底，索引没下载成功也拦得住
- **内嵌高手榜**：点右上角「高手榜 ›」用原生 WebView 在 App 内打开 `index.html`，顶栏「关闭」或返回键退出；创建失败会把具体原因显示在页面上，再回退系统浏览器
  - ⚠️ pyjnius 1.7 不会把 Python `str` 自动转成 Java `CharSequence`，`btn.setText("关闭")` 会抛 `JavaException` 并让整个 WebView 创建失败（表现为「一点就跳浏览器」）。必须 `autoclass("java.lang.String")("关闭")` 显式构造
- **联网热更**：启动器 `main.py` 冷启动比对 `apk/update/version.json`，版本更高就下 `code.zip` 解压到私有目录 `live/`；失败静默回退内置代码（p4a 的 Python 不带系统根证书，所以用了不校验证书的 HTTPS，只做 md5 + 语法校验）
- 改 UI / 逻辑只需推一个约 39 KB 的热更包（本地脚本 `scripts/pack_update.py`），不用重新装 APK
- 安装包在仓库 Release `apk-v1.0`；`build-apk.yml` 只在 `apk/**` 或自身改动时触发，产物在 Actions 的 artifact 里

## 几个坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `errcode=1 游戏版本过低` | 请求头 `hotver` 低于服务端门槛 | 调高 `FZJH_HOTVER` / `config.json` 的 `hotver`，或开游戏更新后读设备真实值 |
| `errcode=20616 请求错误` | 请求太频繁被限速 | 脚本已有 0.6s 间隔 + 重试；仍报就把 `SLEEP` 调到 1.0 |
| `errcode=500 游戏档案数据不存在` | 请求头 `userid` 不是本机账号 | 重新从 `Cocos2dxPrefsFile.xml` 读 `userid` |
| `握手失败` | `uuid` 不对 | 重新从 `extends.xml` 读 `fzjh_uuid` |
| 页面「数据读取失败」 | 直接双击打开了 html | 用 `scripts/serve.py` 起本地服务 |
| 改了样式没生效 | 浏览器缓存 | 跑 `stamp_assets.py` 再 Ctrl+F5 |
| 定时不准，晚几十分钟 | Actions 排队延迟 | 正常，别指望精确到分 |
| 60 天后定时不跑了 | 仓库长期无活动，计划任务被停用 | Actions 页面点一次 Enable |
| `git push` 403 | `permissions` 缺 `contents: write` | 检查 workflow 的 `permissions` |

**hotver 怎么取**（游戏更新后）：

```powershell
$adb='D:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe'
& $adb connect 127.0.0.1:7555
& $adb shell "grep -o 'name=`"hotver`">[^<]*' /data/user/0/com.xhtt.app.fzjh/shared_prefs/Cocos2dxPrefsFile.xml"
```

> 设备上的 hotver 有时比服务端要求的低（客户端还没热更），以服务端实际接受值为准，用递增法试。

## 限度说明

- 只抓高手榜（`boardType=1`）。其它榜（财富/阅历/佳人…）把 `--board` 换成对应数字即可，脚本通用。
- 少数新技能的 id 在旧版技能表里查不到，已在 `build_names.py` 的 `SKILL_OVERRIDES` 里补录（燕不留痕、寸芒行、太初缚龙诀、惊弦录，取自 whfie/fzjhskill 的 skill.json）。再出现新的补一行。
- 装备里 `weapon_xxx` 这类 id 是武器外观、不是物品 id，两个装备表都没有，页面显示「未知」，悬停可看原始 id。
- 只取榜单前 100 名（10 页 × 10 条）。
- 档案每个区约 1 MB/天，五区一年约 2 GB；GitHub 建议仓库控制在 1 GB 内，跑久了可以只抓前 50 名或用孤儿分支瘦身。
- 数据来自游戏内公开排行榜，仅作查询展示，不作为任何交易依据。
