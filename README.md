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

## 目录

```
fzjh-rank/
├─ index.html                 高手榜
├─ exp.html                   经验变化
├─ assets/
│  ├─ style.css               全部样式（含 ≤560px / 561–900px 断点）
│  ├─ servers.js              分区解析、切换器、跨页链接参数
│  ├─ app.js                  高手榜渲染、搜索、排序、详情弹窗
│  └─ exp.js                  经验页渲染
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
│  ├─ stamp_assets.py         把 html 里的 ?v= 刷成资源内容哈希
│  ├─ summary.py              输出刷新摘要（CI 用）
│  └─ serve.py                本地预览（正式站不需要）
├─ apk/                       「输入 UID 查档案」安卓 App 源码 + 热更包
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

`apk/` 是一个「输入 UID 查玩家档案」的小工具，Kivy 写的，和网页共用同一套协议代码。

- 启动器 `main.py` 冷启动时检查 `apk/update/version.json`，版本更高就下 `code.zip` 解压到私有目录 `live/` 并运行；失败静默回退内置代码（p4a 的 Python 不带系统根证书，所以用了不校验证书的 HTTPS，只做 md5 + 语法校验）
- 改 UI / 逻辑只需推一个约 25 KB 的热更包（本地脚本 `pack_update.py`），不用重新装 APK
- `build-apk.yml` 只在 `apk/**` 或自身改动时触发，构建产物在 Actions 的 artifact 里

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
