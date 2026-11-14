# APK 修改操作手册

> 项目：`E:/workbuddy2/fzjh-rank`（仓库 `fzpaihang/lanlandeku`）
> 适用：给「玩家查询」App 改界面、改逻辑、改数据、重打包
> 最后校准：2026-11-13，线上热更 v20

---

## 0. 三十秒速查

日常改界面/逻辑，走这三步就够：

```bash
cd /e/workbuddy2/fzjh-rank
python -m py_compile apk/app_ui.py            # 1. 语法检查
python scripts/pack_update.py "这次改了什么"   # 2. 打包热更（版本号自动 +1）
# 3. 提交并推送 apk/ 源码 + apk/update/ 两个文件（见 §3.4）
```

用户侧：**完全退出 App 再打开** → 启动器自动下载 → 页面底部显示新版本号即生效，不需要重装。

---

## 1. 代码地图

`apk/` 目录就是打包进 APK 的全部源码。改之前先确认要改的文件属于哪一类。

| 文件 | 行数 | 职责 | 在热更包内 |
|---|---|---|---|
| `main.py` | 181 | 启动器：比对版本 → 下载 code.zip → 校验 → 解压到 `live/` → 加载 `app_ui` | ✗（改它必须重装） |
| `app_ui.py` | 1419 | 全部界面与交互（查询页、结果页、分组折叠、输入框、内嵌网页入口） | ✓ |
| `lookup_core.py` | 485 | 接口与数据层：分区、档案解析、等级换算、缓存、最近查询 | ✓ |
| `fetch.py` | 645 | 游戏接口请求、握手、AES 会话 | ✓ |
| `aes_pure.py` | 188 | 纯 Python AES（避免引入 pycryptodome） | ✓ |
| `names_index.py` | 252 | 昵称索引：拉 `lookup-index.json`、本地模糊搜索、隐私名单过滤 | ✓ |
| `archive_local.py` | 258 | 查询成功回写昵称：本地 `pending_names.jsonl` → 后台提交 GitHub | ✓ |
| `webview_overlay.py` | 314 | 安卓原生 WebView 覆盖层（App 内看高手榜） | ✓ |
| `skill_groups.py` | 138 | 武学分组逻辑（多对多 + 关键词兜底） | ✓ |
| `skill_class.py` | 785 | **自动生成**的武学位置表（774 条 `id → "内功,拳脚,招架"`） | ✓ |
| `names.json` | 64 KB | 武学 / 门派 / 槽位 id→中文名 | ✗（改它必须重装） |
| `fonts/NotoSansSC-Regular.ttf` | 7.1 MB | **自动生成**的中文字体子集（21637 字），见 §5.3 | ✗（改它必须重装） |
| `buildozer.spec` | 44 | 打包配置（包名、权限、架构、依赖） | ✗ |
| `icon.png` | 3.8 KB | 图标 | ✗ |
| `config.json` | — | 分区 uuid/账号，**gitignore，绝不提交** | ✗（Secret 注入） |
| `gh.json` | — | 回写仓库的 token，**gitignore** | ✗（Secret 注入） |
| `data/skill.json.gz` | 121 KB | 只给生成脚本用的上游原始表缓存，不进 APK | ✗ |
| `update/code.zip` | ~53 KB | 热更代码包 | 发布物 |
| `update/version.json` | — | 热更版本号 + md5 + 大小 + 说明 | 发布物 |

关键约束：

- **热更只替换 `.py`**。`names.json`、`fonts/*.ttf`、`config.json`、`icon.png`、`buildozer.spec`、新增第三方依赖，都不在热更包里 → 必须重打 APK。
- `buildozer.spec` 的 `source.include_exts = py,json,png,jpg,kv,atlas,ttf,otf`；`.gz` 不打包，所以 `data/skill.json.gz` 只在本地生成时用。
- **字体必须重装才生效**：热更包带不了 `.ttf`。发 v26 时热更先上线，老 APK 会自动回退系统字体（`_local_font()` 返回空），新 APK 才用到打包字体。
- 缓存和用户数据写在 `ANDROID_PRIVATE`（`/data/data/com.fzjh.fzjhlookup/files/`），**不放 `live/`**，否则每次热更 `/data` 里的分区记忆和最近查询都会被清掉。

### 1.1 本地目录约定

| 路径 | 用途 | 是否进 git |
|---|---|---|
| `E:/workbuddy2/fzjh-rank/apk/` | 源码 | 是 |
| `E:/workbuddy2/fzjh-rank/dist/` | 打好的 APK 归档（`fzjhlookup-1.x-<改动>.apk`） | 否（已 ignore） |
| `E:/workbuddy2/fzjh-rank/docs/` | 方案、校对表、本手册 | 是 |
| `E:/workbuddy2/_agent_tmp/` | 临时脚本、截图、worktree | 否 |

所有产物都放 E 盘，不要写 `%TEMP%` 或桌面（Git Bash 的 `/tmp` 实际落在 `C:\Users\...\AppData\Local\Temp`）。

---

## 2. 先判断改动属于哪一类

| 改动内容 | 走哪条通道 | 用户要做什么 |
|---|---|---|
| `app_ui.py` / `lookup_core.py` / `webview_overlay.py` 等 .py | **热更**（§3） | 退出重开 |
| 新增一个 `.py` 模块 | 热更，但**必须加进 `pack_update.py` 的 FILES** | 退出重开 |
| `names.json` / `fonts/*.ttf` / `icon.png` / `buildozer.spec` / 新依赖 | **重打 APK**（§4） | 下载重装 |
| 武学位置表（`skill_class.py`） | 重新生成后热更（§5.1） | 退出重开 |
| 服务端数据（榜单、昵称索引、隐私名单） | 不碰 APK，改仓库数据即可（§5.2） | 无感 |

---

## 3. 通道 A：热更（日常 95% 的情况）

### 3.1 改代码

只改 `apk/` 下的 `.py`。几个硬规则见 §7，尤其：

- 给按钮传宽度用**纯数字**（`width=104`），不要再套 `dp()`；
- 调 Java 的 `setText` 必须用 `autoclass("java.lang.String")(...)`；
- 别在 `live/` 放用户数据。

### 3.2 语法检查

```bash
cd /e/workbuddy2/fzjh-rank
python -m py_compile apk/app_ui.py apk/lookup_core.py apk/skill_groups.py
echo $?      # 0 才继续
```

### 3.3 打热更包

```bash
python scripts/pack_update.py "一句话说明这次改了什么"
cat apk/update/version.json
```

输出示例：

```
已生成 v21：9 个文件 / 52.5 KB / md5 1543363f...
```

规则：

- 版本号是**读旧的 version.json 再 +1**，不要手改 `version.json`（会导致号段重复、老客户端不更新）。
- `version.txt` 不用管，由启动器在安装时写入。
- `code.zip` 与 `version.json` 是**一对**，必须同时提交。只提交一个 → md5 与包不匹配 → 客户端校验失败静默回退，看起来像「热更没生效」。
- 新增模块一定要先进 `scripts/pack_update.py` 的 `FILES` 列表，否则包里没有它，`import` 会走 `except` 兜底 → 功能静默降级。`main.py` 的 `REQUIRED` 只校验 4 个老文件，拦不住这种漏。

### 3.4 发布

**情况一：本地仓库与远端一致（常规）**

```bash
cd /e/workbuddy2/fzjh-rank
git add apk/*.py apk/update/code.zip apk/update/version.json scripts/ docs/
git commit -m "热更 v21：xxx"
git push origin HEAD:main
```

**情况二：本地与远端分叉 / push 被拒（历史遗留，实际常遇到）**

不要 `--force`，用临时 worktree 从远端干净拉一份再提交：

```bash
cd /e/workbuddy2/fzjh-rank
git worktree prune
git fetch -q origin
git worktree add --detach "E:/workbuddy2/_agent_tmp/pxx" origin/main

W="E:/workbuddy2/_agent_tmp/pxx"
cp apk/app_ui.py apk/update/code.zip apk/update/version.json "$W/apk/"   # 按实际改动复制
cd "$W"
git add apk/
git commit -q -m "热更 v21：xxx"
git push origin HEAD:main

cd /e/workbuddy2/fzjh-rank
git worktree remove --force "$W"
git worktree prune
git fetch -q origin
git reset --mixed origin/main        # 让本地索引与远端对齐，不动工作区文件
```

**代理问题**：本机环境变量里挂着 `HTTP_PROXY`（端口会变，`echo $HTTP_PROXY` 看当前值），会让 git 偶发 502。直连成功率高：

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy \
  timeout 90 git -c http.proxy= -c http.sslBackend=openssl push origin HEAD:main
```

**`-c http.sslBackend=openssl` 别省**：Git for Windows 默认走 schannel，本机实测会
`Failed to connect to github.com:443 after 21004 ms`（而同一时刻 `curl --noproxy '*'` 却能通，
容易误判成网络问题）。换 openssl 后端后秒过。诊断顺序：

```bash
curl -sI --noproxy '*' --max-time 12 https://github.com          # 200 → 网络没问题
git -c http.proxy= -c http.sslBackend=openssl ls-remote origin HEAD  # 能列出 sha → 通道没问题
```

断了就等 1–2 分钟重试，别连续猛推。

### 3.5 线上校验

GitHub Pages 有 30–90 秒缓存延迟：

```bash
for i in 1 2 3 4 5; do
  sleep 15
  v=$(curl -s --noproxy '*' --max-time 15 \
      https://fzpaihang.github.io/lanlandeku/apk/update/version.json | grep -o '"version": *[0-9]*')
  echo "try$i: $v"
  echo "$v" | grep -q 21 && break
done
```

`curl` 访问公网要带 `--noproxy '*'`，否则会被本地代理拦成假 502。

### 3.6 设备验证

见 §6.3「模拟老客户端走一遍真热更」。核心是删掉 `files/live` 再重启，等价于老用户升级。

### 3.7 回滚

客户端只升不降，**不能把 version 改小**。正确做法：

1. 把代码恢复成上一版；
2. 重新 `pack_update.py "回滚：xxx"` → 得到更大的版本号；
3. 推送。

---

## 4. 通道 B：重打 APK（改了内置资源或依赖）

### 4.1 触发构建

构建在 GitHub Actions，`push` 命中 `apk/**`（但排除 `apk/update/**`）会自动跑；也可以手动：

```bash
gh workflow run build-apk.yml --repo fzpaihang/lanlandeku
gh run list --repo fzpaihang/lanlandeku --limit 3
```

要点（都在 `build-apk.yml` 里，改之前先读注释）：

- `runs-on: ubuntu-22.04`，不用 `ubuntu-latest`（新镜像 ant 工具链会挂）；
- Python **3.10**，因为 p4a 锁 `pyjnius==1.7.0`，3.11 没有 wheel；
- `p4a.branch = v2024.01.21`（Python 3.11 + pyjnius 1.6.1），不要升 master，Kivy 2.3 编译不过；
- 只编 `arm64-v8a`，两个架构会让构建时间翻倍；
- 首次构建要下 2–3 GB SDK/NDK，约 40–60 分钟；命中缓存 15–20 分钟。

注意副作用：**推任何 `apk/*.py` 都会顺带触发一次 APK 构建**（即使你只想发热更）。这是设计如此，接受即可，不影响热更分发。

### 4.2 取产物

Actions 页面下载 artifact `fzjh-lookup-apk`，或者：

```bash
gh run download <run-id> -n fzjh-lookup-apk -D E:/workbuddy2/fzjh-rank/dist
```

重命名成本地归档：`dist/fzjhlookup-1.3-<改动名>.apk`。

### 4.3 替换 Release 下载文件

网页上「查询已停用」页的下载按钮指向：

```
https://github.com/fzpaihang/lanlandeku/releases/download/apk-v1.0/fzjh-lookup-v1.0.apk
```

换版本时**保持文件名不变**，只替换 Release `apk-v1.0` 下的 asset（网页地址就不用改）。用网页上传，或：

```bash
gh release upload apk-v1.0 "dist/fzjhlookup-1.3-xxx.apk#fzjh-lookup-v1.0.apk" \
  --repo fzpaihang/lanlandeku --clobber
```

### 4.4 重装后的注意点

- 覆盖安装**保留** `/data/data/.../files/`（含 `live/`、缓存、`gh.json`），所以重装后热更链路照常；
- 卸载重装会清空 `live/`，App 会先跑内置代码，再自动升到线上最新热更版本；
- 重装后第一次启动要等 10–30 秒做热更检查，属正常。

---

## 5. 通道 C：只改数据

### 5.1 武学位置表（`skill_class.py`）

上游是 `whfie/fzjhskill` 的 `public/data/skill.json.gz`，与本项目 `names.json` 的 774 个 id 完全一致。

```bash
cd /e/workbuddy2/fzjh-rank
python scripts/build_skill_class.py            # 用本地缓存 apk/data/skill.json.gz
python scripts/build_skill_class.py --fetch    # 上游更新了才需要重新下
python -m py_compile apk/skill_class.py
python scripts/pack_update.py "更新武学位置表"
```

单条纠错：直接在 `apk/skill_class.py` 里改 `CLASS["taixuangong"] = "内功,拳脚,招架"`，再打包热更。别去改 `skill_groups.py` 的关键词规则——那只是「表里查不到」时的兜底。

### 5.2 服务端数据（APK 无需改动）

| 数据 | 仓库路径 | 生成脚本 | APK 何时读到 |
|---|---|---|---|
| 昵称索引 | `data/lookup-index.json` | `scripts/build_lookup_index.py` | 启动时后台拉，6 小时最多检查一次 |
| 昵称回写 | `data/extra-names.json` | APK 自己提交 | 下次别人查时进索引 |
| 隐私名单 | `data/hidden.json` | 手改 | 随 `lookup-index.json` 的 `hidden` 字段下发 |
| 榜单 | `data/servers/<key>/gaoshoubang.json` | `scripts/fetch.py`（Actions 定时） | 进结果页时按需拉 |

改完推 `main` 即可，用户下次打开就吃到新数据。隐私名单要重新跑一次 `build_lookup_index.py` 才会进索引。

### 5.3 中文字体子集（`fonts/NotoSansSC-Regular.ttf`）

**为什么必须打包**：App 原来按路径探测系统字体，三条候选都不靠谱 ——
`NotoSansCJKsc-Regular.ttf` 只有部分 ROM 有、`DroidSansFallback.ttf` 在 Android 9 后已移除、
`NotoSansCJK-Regular.ttc` 的 face 0 是**日文字形**（简体「门」都没有）。三条全落空时退回
`Roboto`（不含中文）→ 全屏豆腐块。而 MuMu 是 AOSP，一定有第一个文件，**这个故障在模拟器上永远复现不出来**。

生成（源文件用 Windows 自带的 `NotoSansSC-VF.ttf`，OFL 1.1 可随 APK 分发）：

```bash
cd /e/workbuddy2/fzjh-rank
python scripts/build_font_subset.py            # 默认 C:/Windows/Fonts/NotoSansSC-VF.ttf
python scripts/build_font_subset.py --src "D:/xxx/NotoSansSC-VF.ttf"
```

脚本做三件事：`instancer` 固定 `wght=400` → 子集化 21637 字 → 输出单体 ttf（7.1 MB）。
字符集 = CJK 基本区全量（20992）+ ASCII + Latin-1 + CJK 标点 + 全角 + **几何符号 U+25A0–U+25FF**。

> 踩过的坑：折叠箭头 `▶` 就在几何符号区，第一版字符集漏了它，武学分组全变豆腐块（☒）。
> Kivy 不做字体回退，缺一个字就是豆腐块，所以字符集宁大勿小。

`_local_font()` 的查找顺序：`__file__` 目录（热更时是 `live/`）→ `ANDROID_APP_PATH` → `sys.path`。
所以调试时把字体推到 `files/live/fonts/` 就能生效，不必重打 APK。

改完字体要**重打 APK**（§4），热更包带不了 `.ttf`。

---

## 6. 模拟器调试环境（MuMu）

只在需要真机级验证（输入法、WebView、触摸）时用。

### 6.1 连接

```bash
export MSYS_NO_PATHCONV=1
ADB="D:/Program Files/Netease/MuMuPlayer-12.0/shell/adb.exe"
"$ADB" start-server
"$ADB" connect 127.0.0.1:7555
"$ADB" -s 127.0.0.1:7555 shell getprop ro.product.model
```

`MSYS_NO_PATHCONV=1` 必须加，否则 Git Bash 会把 `/sdcard/x.png` 改写成 Windows 路径。每条命令都要显式 `-s 127.0.0.1:7555`，别依赖默认设备。

包名 `com.fzjh.fzjhlookup`，入口 Activity `org.kivy.android.PythonActivity`。

### 6.2 启动 / 截图 / 日志

```bash
D="-s 127.0.0.1:7555"; P=com.fzjh.fzjhlookup
"$ADB" $D shell am force-stop $P
"$ADB" $D shell am start -n $P/org.kivy.android.PythonActivity
sleep 11
"$ADB" $D shell screencap -p /sdcard/s.png
"$ADB" $D pull /sdcard/s.png "E:/workbuddy2/_agent_tmp/s.png"

"$ADB" $D logcat -d | grep -iE "python|kivy|FATAL|AndroidRuntime" | tail -30
"$ADB" $D shell dumpsys input_method | grep -E "^  mServedView=|mInputShown"
```

坐标按 `wm size`（本例 900×1600）换算，点输入框 `input tap 450 200`，查示例 `input tap 859 600`。

### 6.3 模拟老客户端走真热更（最可靠的验收方式）

```bash
D="-s 127.0.0.1:7555"; P=com.fzjh.fzjhlookup
"$ADB" $D shell run-as $P rm -rf files/live
"$ADB" $D shell am force-stop $P
"$ADB" $D shell am start -n $P/org.kivy.android.PythonActivity
sleep 30
"$ADB" $D shell run-as $P cat files/live/version.txt      # 应等于线上版本
"$ADB" $D shell run-as $P ls files/live | tr '\n' ' '
```

### 6.4 不发布、直接把本地代码塞进设备（调试用）

改一次就打包发布太慢，用 `run-as` 覆盖 `live/` 里的文件即可：

```bash
D="-s 127.0.0.1:7555"; P=com.fzjh.fzjhlookup
"$ADB" $D shell am force-stop $P
for f in app_ui.py skill_groups.py skill_class.py; do
  "$ADB" $D push "E:/workbuddy2/fzjh-rank/apk/$f" "/data/local/tmp/$f"
  "$ADB" $D shell run-as $P cp "/data/local/tmp/$f" "files/live/$f"
done
"$ADB" $D shell run-as $P rm -rf files/live/__pycache__    # 必须删，否则跑旧字节码
"$ADB" $D shell am start -n $P/org.kivy.android.PythonActivity
```

**注意**：设备上 `files/live/version.txt` 如果小于线上版本，下次启动会被自动热更覆盖回线上。调试期间可以把 `version.txt` 写成 `99` 顶住：

```bash
printf '99' > E:/workbuddy2/_agent_tmp/v99.txt
"$ADB" $D push "E:/workbuddy2/_agent_tmp/v99.txt" /data/local/tmp/v99.txt
"$ADB" $D shell run-as $P cp /data/local/tmp/v99.txt files/live/version.txt
```

### 6.5 模拟器的已知局限

- MuMu 里搜狗输入法窗口高度为 0（`mSurfacePosition=Point(0,1600)`），`adb shell input text` 的字**到不了 Kivy**。「能不能真的打字」只能真机确认；模拟器只能验到「输入法焦点回到 `DummyEdit`、`mInputShown=true`」这一层。
- 系统低内存会杀进程（`lowmemorykiller`），界面突然变桌面不是崩溃，重启即可。

---

## 7. 界面改动的硬规则（都是踩过的坑）

| 坑 | 现象 | 正确写法 |
|---|---|---|
| 宽度重复套 `dp` | `txt_button(width=dp(150))` → 实际 337px，比整行还宽，标题 `text_size` 被压成 0，汉字各占一行、溢出盖住列表 | `txt_button(width=104)`（内部已乘 dp） |
| 手动估列表高度 | `height = dp(35) * len(items)`，搜索过滤后条数变了会错位 | 绑 `minimum_height`，别手算 |
| pyjnius 传 Python str 给 Java | `JavaException: No methods called setText` → 整个 WebView 构建失败 → 静默跳浏览器 | `autoclass("java.lang.String")("关闭")` |
| `getParent()` 的静态类型是 `ViewParent` | `No methods called removeView`，异常被吞 → 白色 about:blank 一直盖在 App 上 | `cast("android.view.ViewGroup", root.getParent())` 再 `removeView` |
| WebView 抢走输入法焦点 | 关掉网页后 Kivy 输入框「像被禁用」，软键盘弹出来字却进了看不见的网页 | 关闭时 `hideSoftInputFromWindow` + `clearFocus` + `removeView` + `destroy()`；打开网页前先让 App 输入框失焦 |
| Kivy 默认不弹虚拟键盘 | 日志 `virtual keyboard not allowed`，点输入框没键盘 | `Config.set("kivy", "keyboard_mode", "system")`（启动最早期设置） |
| 已聚焦的输入框再点不重申请键盘 | 关网页后再也调不回输入法 | `RoundInput.on_touch_down` 里 `rekeyboard()` + 补一次 `SDL_StartTextInput()` |
| 依赖系统字体路径 | 厂商 ROM 可能一个都没有 → 退回 Roboto → 全屏豆腐块；MuMu 是 AOSP 测不出来 | 字体打包进 APK（§5.3），系统字体只做兜底 |
| 子集漏字符 | Kivy 无字体回退，缺一个字符就是豆腐块（折叠箭头 ▶ 曾整片变 ☒） | 字符集按区段整段收（几何符号 U+25A0–U+25FF 等），别只挑几个 |
| 依赖 Kivy 软键盘 | SDL 能把 IME 拉起来，但 Kivy 0.2 秒轮询 `is_keyboard_shown()` 会把它收走；且 system 模式下 `Window.on_textinput` 不转发给控件、`TextInput` 也不走 `_bind_keyboard()` | `RoundInput._on_focus` 里自己 `Window.bind(on_textinput/on_key_down)` + `SDL_StartTextInput()`（见 `docs/UI优化-实施记录.md` §10） |
| 拿 `keyboard_height` 判断键盘 | SDL2 构建里 `_get_android_kheight()` 恒返回 0 | 别用它；看 `dumpsys input_method` 的 `mInputShown` |
| `virtual keyboard not allowed` 日志 | 这是 `WindowBase.__init__` 的常规日志，system 模式也这么打 | 不要当报错，真正的证据是 `mServedView` |
| BoxLayout 置顶写反 | `add_widget(w, index=0)` 在 `orientation="vertical"` 里落到**最下面**（children 逆序铺） | 置顶用 `add_widget(w, index=len(children))` |
| 拼音 id 参与英文关键词匹配 | `jibenqinfa` 含 `qi` → 被误判成内功 | 只对含大写的驼峰 id 做英文匹配 |
| 新模块忘了进 `FILES` | 热更包里没这个文件，功能静默降级 | 改 `scripts/pack_update.py` 的 `FILES` |
| 起名带 `dp(78)` 当纯数字 | 按钮宽度翻倍 | 见第一条 |

---

## 8. 发布检查清单

发之前逐条确认：

- [ ] `python -m py_compile` 全绿
- [ ] 新增 `.py` 已加入 `scripts/pack_update.py` 的 `FILES`
- [ ] `version.json` 的 `version` 比线上大 1（由脚本自动完成，没手改）
- [ ] `code.zip` 与 `version.json` **一起**提交
- [ ] `config.json` / `gh.json` 没被提交（`git status` 里不应出现）
- [ ] 线上 `version.json` 已是新版本（§3.5）
- [ ] 模拟器删 `files/live` 重启后 `version.txt` 等于新版本（§6.3）
- [ ] 三处界面回归：查询页首屏、结果页指标 + 准备位、武学分组
- [ ] 输入框可输入、内嵌高手榜可开可关（关完还能继续打字）

---

## 9. 故障排查表

| 现象 | 先查什么 | 结论 |
|---|---|---|
| 改了代码但界面没变 | `version.txt` 与线上 `version.json` 对比 | 号没涨 / md5 不匹配 / Pages 还没刷 |
| 热更后打不开（闪退） | `logcat \| grep -i python`，看 `is_valid_dir` 的报错 | 包里文件缺失或语法错，启动器会回退内置代码 |
| App 启动慢十几秒 | logcat 里 `[launcher]` 行 | 在等 8 秒版本检查 + 25 秒下载，正常 |
| 内嵌网页跳浏览器 | logcat 找 `JavaException` | 多半是 pyjnius 类型转换（§7） |
| 搜索框打不了字 | `dumpsys input_method \| grep mServedView` | 是否仍指向 WebView；是则收焦点没做干净 |
| 武学全挤在「其他」 | `run-as cat files/live/skill_class.py \| head` | 热更包里漏了 `skill_class.py` |
| 查询报 `errcode=-1` / 空数据 | 是否刚有其他查询在跑 | 一个 uuid 只保留一个会话，并发会互踢；等 2 分钟重试 |
| 线上 404 | 文件是否真在 `apk/update/` 下、是否推上 main | Pages 源是 main 根目录 |

---

## 10. 不要做的事

- 不要手改 `apk/update/version.json` 的版本号（会打断号段，老客户端收不到更新）。
- 不要 `git push --force` 到 main（会顶掉 Actions 提交的抓取数据）。
- 不要把 `config.json` / `gh.json` 提交进仓库（等同凭据）。
- 不要在 `live/` 里放缓存或用户数据（热更会整个删掉）。
- 不要把 `dp()` 套在已经是 dp 的参数上。
- 不要为了「省一次构建」把 `apk/**` 从 workflow 的 `paths` 里去掉——重装包会拿不到新代码。
