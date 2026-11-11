# 放置江湖 · 高手榜

一个纯静态的排行榜查询站：展示全服高手榜（武学造诣 Top 100），支持搜索、排序、门派筛选。
数据每天自动刷新 2 次，不需要服务器、不需要数据库。

## 长什么样

- 桌面端 8 列：名次 / 侠名 / 门派 / 等级 / 经验 / 福缘 / 容貌 / 年龄
- 手机端自动收成 4 列：名次 / 侠名+门派 / 等级 / 经验，一屏能看到 12 行
- 点表头排序；搜昵称、ID、门派都能搜；地址加 `?me=你的ID` 高亮自己
- **多分区切换**：页头「分区」一排按钮，苍松迎客 / 墨羽惊鸿 各自独立的数据
- **点侠名弹出该玩家完整档案**：12 项基础数值、准备位、近期新增武学、全部武学（可展开）、装备
- **经验变化页**（右上角按钮进入）：每次刷新记一次经验快照，按 3 天窗口算增长、日均、增幅
- 有历史数据后，名次旁会显示涨跌箭头（▲2 / ▼1 / NEW）

## 目录

```
fzjh-rank/
├─ index.html          高手榜页面
├─ exp.html            经验变化页面
├─ assets/
│  ├─ style.css
│  ├─ app.js
│  └─ exp.js
├─ data/
│  ├─ names.json        技能/装备 id → 中文名（一次性生成）
│  └─ servers/
│     ├─ index.json     分区清单（前端读，不含凭据）
│     ├─ taptap/        苍松迎客：gaoshoubang.json / exp-history.json / profiles/
│     └─ taptap_4/      墨羽惊鸿：同上
├─ scripts/
│  ├─ fetch.py          抓榜单 + 记经验快照（自包含，只依赖 pycryptodome）
│  ├─ fetch_profiles.py 抓玩家档案
│  ├─ build_names.py    生成中文名映射（换游戏版本后重跑）
│  ├─ summary.py        输出刷新摘要（CI 用）
│  └─ serve.py          本地预览用（正式站不需要）
├─ .github/workflows/refresh.yml   定时刷新（GitHub Actions）
├─ requirements.txt      CI 依赖
├─ config.json         设备 uuid / 账号 / hotver（★ 不要提交到公开仓库）
├─ refresh.bat         双击即刷新，日志写 data/logs/
└─ .gitignore
```

## 多分区是怎么工作的

**分区由请求头 `channel` 决定，但每个分区必须有自己的一套 `uuid` + `account`**——服务端会校验账号是否在该分区，用别的分区凭据会返回 `500 游戏档案数据不存在`。

已知的 taptap 分区：

| channel | 分区 |
|---|---|
| `taptap` | 苍松迎客 [1服] |
| `taptap_2` | 白鹤亮翅 [2服] |
| `taptap_3` | 丹凤朝阳 [3服] |
| `taptap_4` | 墨羽惊鸿 [新服] |

凭据从对应客户端里取（只读）：

- `uuid` ← `/data/user/<N>/com.xhtt.app.fzjh/shared_prefs/extends.xml` 的 `fzjh_uuid`
- `account` ← 同目录 `Cocos2dxPrefsFile.xml` 的 `userid`

> 分身/多开客户端在**另一个 Android 用户空间**（`/data/user/10/…`），主空间读到的 uuid 是另一个分区的，别搞混。
> 4399 端是独立渠道：`uuid` 前缀为 `4399`，`channel` 填 `4399`。

## 数据是怎么来的

游戏客户端本身不存榜单，运行时向服务端按页拉取。抓取脚本复刻了客户端协议：

1. `POST /api/service/exchange_publickey`：用设备 uuid 换本会话的加密密钥
2. `POST /api/v5/get_board/1 {"page":N}`：拿高手榜第 N 页（每页 10 条）
3. `POST /api/v5/get_user_info {"userid":N,"type":0}`：拿单个玩家的完整档案（武学、准备位、装备）
4. 响应是 AES 加密的，解密后剥掉尾部填充字符 `'0'` 才是 JSON

全程不需要开模拟器、不需要抓包、不需要内存转储——只要 `config.json` 里那三个值是对的。

## 跑起来

**依赖**：Python 3.8+、`pycryptodome`

```powershell
pip install pycryptodome
```

**抓一次数据**：

```powershell
python scripts\fetch.py
# 或双击 refresh.bat（会写日志）
```

成功的话 `data/gaoshoubang.json` 会被更新，控制台打印前 3 名。

**抓玩家档案**（点侠名能看详情）：

```powershell
python scripts\build_names.py        # 首次或游戏大版本更新后跑一次
python scripts\fetch_profiles.py     # 100 份，约 1 分钟
```

每人存成 `data/profiles/<userid>.json`，单份约 16 KB，页面点击时才拉取——首屏不会因为详情变大。
某个玩家抓失败（已删号、改名等）只会缺他那份，页面点开时提示读取失败，不影响其他人。

**「近期新增武学」怎么来的**：每次抓档案时，把本次的武学集合和**上一版档案**比对，新出现的记为「当天新增」，写进档案的 `newSkills` 字段；30 天内的记录会一直保留并累计显示。所以：

- 第一次抓（没有上一版）不会把已有武学误判为新增
- 需要至少跑两次才有意义；玩家没学新武学时这个区块不显示
- 玩家掉出榜单再回来，档案被清掉，会重新从零开始记

**本地预览**：

```powershell
python scripts\serve.py 8791
# 浏览器打开 http://127.0.0.1:8791/
```

> 不要直接双击 index.html——浏览器会因为 `file://` 的跨域策略拒绝读取 JSON。

## 每天自动刷新

Windows 任务计划程序，一天两次（早 6 点、晚 6 点）：

```powershell
schtasks /Create /TN "FZJH高手榜刷新" /TR "E:\workbuddy2\fzjh-rank\refresh.bat" /SC DAILY /ST 06:00 /F
schtasks /Create /TN "FZJH高手榜刷新-晚间" /TR "E:\workbuddy2\fzjh-rank\refresh.bat" /SC DAILY /ST 18:00 /F
```

删掉：`schtasks /Delete /TN "FZJH高手榜刷新" /F`

> 也可以拆成一条命令用 `/SC DAILY /RI 720`（每 12 小时一次）。

## 部署到 GitHub Pages

仓库结构就是站点根目录，直接推上去即可：

1. 新建仓库，把 `index.html`、`assets/`、`data/` 推上去
2. Settings → Pages → Source 选 `main` 分支根目录
3. 得到 `https://<用户名>.github.io/<仓库名>/`

**⚠️ 两个必须注意的点**

1. **`config.json` 绝对不能提交**。里面的 `uuid` + `account` 等于登录凭据，谁拿到都能查数据、也能冒充你的设备。`.gitignore` 已经排除了它，别用手动添加绕过。
2. **`data/` 必须提交**。页面靠这个 JSON 渲染；如果你把仓库设成私有，Pages 需要付费（Pro/Team），公开仓库则免费。

如果想让线上数据也自动更新，有两种做法：

| 做法 | 说明 |
|---|---|
| 本地定时跑 + `git push` | 在你自己的机器上跑，抓取最稳；但电脑得开着 |
| **GitHub Actions 定时** | 不依赖你的电脑，下面单独讲 |

## 用 GitHub Actions 全自动（不依赖本地电脑）

仓库里已经带好 `.github/workflows/refresh.yml`，推上去就能用。

### 1. 建仓库并推送

```bash
cd E:\workbuddy2\fzjh-rank
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<你的用户名>/fzjh-rank.git
git push -u origin main
```

> `config.json` 已被 `.gitignore` 排除，**不会被推上去**，这是故意的。

### 2. 配置 Secrets（凭据）

仓库 → **Settings → Secrets and variables → Actions → New repository secret**，加三个：

| Name | Value |
|---|---|
| `FZJH_UUID` | 设备 uuid，如 `taptapa7b061561d947e784d18bf9f07` |
| `FZJH_ACCOUNT` | 账号 userid，如 `10024430` |
| `FZJH_HOTVER` | 如 `18450`（游戏更新后要往上调） |

脚本优先读环境变量，读不到才回退 `config.json`，所以本地和 CI 可以共用一套代码。

### 3. 先跑一次连通性探测（★ 必做）

Actions 标签页 → 左侧「刷新高手榜」→ **Run workflow** → 模式选 `probe` → 运行。

看日志末尾：

- `[probe] ✓ 第一名：xxx` → 海外出口能访问游戏服，可以进入下一步
- `握手失败` / `数据未取到` / `游戏版本过低` → 说明这条路走不通，改用云服务器或家中小主机

**这一步必须先做**：runner 在海外，而这个接口是国内的，能不能通只有实测才知道。

### 4. 开启定时

探测通过后不用再改代码，workflow 已经配好两条计划任务：

| UTC | 北京时间 | 动作 |
|---|---|---|
| `0 22 * * *` | 次日 06:00 | 榜单 + 档案（全量） |
| `0 10 * * *` | 当日 18:00 | 只抓榜单 |

档案（`data/profiles/`，约 1 MB）每天只在早班更新一次，晚班只更新榜单和经验快照——**这是为了压住仓库增长**，按每天 1 MB 估算，一年约 350 MB，GitHub 建议仓库控制在 1 GB 内；真跑久了可以定期用孤儿分支重写历史来瘦身。

### 5. 开启 Pages

Settings → Pages → Source 选 `main` / 根目录，得到 `https://<用户名>.github.io/fzjh-rank/`。

### 几个坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 定时不准，晚十几分钟 | GitHub 的计划任务有排队延迟，官方只保证「大致按点」 | 属正常，别指望精确到分 |
| 60 天后定时突然不跑了 | 仓库长期无活动会被自动停用计划任务 | 在 Actions 页面点一次 Enable；本项目每天有提交，一般不会触发 |
| 任务失败没察觉 | 默认不通知 | GitHub 会给仓库 watcher 发「workflow run failed」邮件，确保 Star/Watch 自己 |
| `git push` 403 | `permissions` 缺 `contents: write`，或分支保护规则拦截机器人提交 | 检查 workflow 的 `permissions` 与分支保护设置 |
| 免费额度不够 | 私有仓库 2000 分钟/月，本项目约 12 分钟/天 | 公开仓库不限时长，私有仓库也够用 |

## 出错对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| `errcode=1 游戏版本过低` | 请求头 `hotver` 低于服务端门槛 | 把 `config.json` 的 `hotver` 往上调（+1 或 +10 试），或开游戏更新后读设备上的真实值 |
| `errcode=20616 请求错误` | 请求太频繁被限速 | 脚本已有 0.6s 间隔 + 3 次重试；仍报就把 `SLEEP` 调到 1.0 |
| `errcode=500 游戏档案数据不存在` | 请求头 `userid` 不是本机账号 | 重新从 `shared_prefs/Cocos2dxPrefsFile.xml` 读 `userid` |
| `握手失败` | `uuid` 不对 | 重新从 `shared_prefs/extends.xml` 读 `fzjh_uuid` |
| 页面显示"数据读取失败" | 直接双击打开了 html | 用 `scripts/serve.py` 起本地服务 |
| 改了列/样式但页面没变化 | 浏览器缓存了旧的 `app.js` / `style.css` | 改完把 `index.html` 里资源地址的 `?v=3` 递增（`?v=4`），再按 Ctrl+F5 |

**hotver 怎么取**（游戏更新后）：

```powershell
$adb='D:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe'
& $adb connect 127.0.0.1:16416
& $adb -s 127.0.0.1:16416 shell "grep -o 'name=`"hotver`">[^<]*' /data/user/0/com.xhtt.app.fzjh/shared_prefs/Cocos2dxPrefsFile.xml"
```

> 设备上的 hotver 有时会比服务端要求的低（客户端还没热更），以服务端实际接受值为准，用递增法试出来。

## 限度说明

- 只有高手榜（`boardType=1`）。其它榜（财富/阅历/佳人…）把 `--board` 换成对应数字即可，脚本通用。
- 少数新技能的 id 在旧版技能表里查不到，已在 `build_names.py` 的 `SKILL_OVERRIDES` 里补录（燕不留痕、寸芒行、太初缚龙诀、惊弦录，取自 whfie/fzjhskill 的 skill.json）。再出现新的补一行即可。
- 装备里 `weapon_xxx` 这类 id 不是物品 id（是武器外观），两个装备表都没有，页面显示为「未知」，鼠标悬停可看原始 id。
- 只取前 100 名（榜单本身只有 100 人，10 页 × 10 条）。
- 数据是游戏内公开排行榜，仅作查询展示。
