# APK 修改操作手册

> 项目：`E:/workbuddy2/fzjh-rank`　仓库：`fzpaihang/lanlandeku`
> 应用名：**霜霜妙妙屋**（`package.domain = com.fzjh`，`package.name = fzjhlookup`）
> 最后校准：2026-11-14　线上热更：**v49**　安装包：Release `apk-v1.0 / fzjh-lookup-v1.0.apk`
> 本文汇总的是「改这个 APK 实际会用到的全部操作」；逐次改动的背景与推理见 `docs/UI优化-实施记录.md`。

---

## 0. 三十秒速查

**日常改界面 / 逻辑（热更）**

> 环境提示：本机是 PowerShell，没有 Git Bash。命令请改写成等价的
> PowerShell / Python 写法；**提交一律走 §9.1 的 GitHub API**，不执行
> `git add/commit/push`（本地 git 与远端长期分叉）。

```bash
cd /e/workbuddy2/fzjh-rank
python -m py_compile apk/app_ui.py apk/inline_input.py          # 1 语法
python scripts/pack_update.py "这次改了什么"                     # 2 打包 + 自动签名 + 版本号 +1
# 3 用 §9.1 的 GitHub API 脚本推 apk/*.py + apk/update/{code.zip,version.json}
# 4 curl 确认线上版本号；模拟器删 files/live 重启做全量验收
```

用户侧：**完全退出 App 再打开**即自动热更，不用重装。

**改了内置资源 / `main.py` / Java 层 / 应用名 / 图标** → 必须重打 APK（§4），用户要重新下载安装。

**改了网页脚本** → 推 HTML/JS 后**必须**跑 `python scripts/stamp_assets.py` 刷 `?v=hash`，否则 App 内 WebView 一直用缓存里的旧脚本（§5.4）。

---

## 1. 环境与凭据

### 1.1 路径

| 路径 | 用途 | 进 git |
|---|---|---|
| `E:/workbuddy2/fzjh-rank/apk/` | APK 全部源码与内置资源 | 是 |
| `E:/workbuddy2/fzjh-rank/dist/` | 交付给用户的 APK 归档 | 否 |
| `E:/workbuddy2/fzjh-rank/docs/` | 本手册、实施记录、校对表 | 是 |
| `E:/workbuddy2/fzjh-rank/scripts/` | 打包、生成、发布辅助脚本 | 是 |
| `E:/workbuddy2/_agent_tmp/` | 临时脚本、截图、备份、ffmpeg、token | 否 |
| `E:/workbuddy2/fzjh-rank/.keys/update.key` | **更新包签名私钥** | 否（已 gitignore） |

所有产物放 E 盘。Git Bash 的 `/tmp` 实际落在 `C:\Users\...\AppData\Local\Temp`，不要用；也不要写桌面/文档。

### 1.2 设备

```bash
export MSYS_NO_PATHCONV=1
ADB="D:/Program Files/Netease/MuMuPlayer-12.0/shell/adb.exe"
"$ADB" start-server && "$ADB" connect 127.0.0.1:7555
D="-s 127.0.0.1:7555"; P=com.fzjh.fzjhlookup
```

- 包名 `com.fzjh.fzjhlookup`，入口 `org.kivy.android.PythonActivity`
- 屏幕 900×1600；常用坐标：输入框 `(450,592)`、查询按钮 `(450,800)`、顶栏空白 `(450,150)`
- `MSYS_NO_PATHCONV=1` 必须加，否则 `/sdcard/x.png` 被改写成 Windows 路径
- 每条 adb 都显式带 `-s`，不依赖默认设备

### 1.3 发布凭据与密钥

| 项 | 位置 / 值 | 说明 |
|---|---|---|
| GitHub token | `E:/workbuddy2/_agent_tmp/gh_token.txt` | 用于 GitHub API 建 commit |
| 签名私钥 | `.keys/update.key` | 丢了就无法再打热更包，必须备份 |
| 签名公钥 | 硬编码在 `apk/main.py` 的 `UPDATE_PUBKEY` | `22d04f4b…` |
| 更新源 | `https://fzpaihang.github.io/lanlandeku/apk/update/` | 主源 |
| 更新镜像 | `https://cdn.jsdelivr.net/gh/fzpaihang/lanlandeku@main/apk/update/` | 主源失败自动切 |
| 内置 CA | `apk/cacert.pem` | 3 张根：ISRG X1 / DigiCert G2 / GlobalSign R46 |

Python 访问 GitHub API 用 `urllib.request.build_opener(urllib.request.ProxyHandler({}))` 绕开本机代理；`curl` 访问 Pages 必须带 `--noproxy '*'`，否则被本地代理拦成假 502。

---

## 2. 代码地图

### 2.1 `apk/` 文件职责

| 文件 | 职责 | 热更包内 |
|---|---|---|
| `main.py` | 启动器：比对版本 → 下载 → md5 → **验签** → 解压到 `live/` → 加载 `app_ui` | ✗ 改它必须重装 |
| `app_ui.py` | 全部界面与交互（查询页、结果页、顶栏、圆形头像、输入焦点、内嵌网页入口） | ✓ |
| `lookup_core.py` | 接口与数据层：分区、档案解析、缓存、20s 查询预算、失败归因 | ✓ |
| `fetch.py` | 游戏接口请求、握手、AES 会话、TLS 上下文 | ✓ |
| `aes_pure.py` | 纯 Python AES | ✓ |
| `names_index.py` | 昵称索引、模糊搜索、隐私名单 | ✓ |
| `archive_local.py` | 查询成功后回写昵称 | ✓ |
| `webview_overlay.py` | 安卓原生 WebView 覆盖层（App 内看高手榜） | ✓ |
| `skill_groups.py` / `skill_class.py` | 武学分组规则 / 自动生成的 id→分类表 | ✓ |
| `native_input.py` | 原生 AlertDialog 输入（**当前是兜底路径，不是主路径**） | ✓ |
| `inline_input.py` | 内联原生 EditText 覆盖层（**当前主路径**） | ✓ |
| `ed25519.py` | 纯 Python Ed25519，RFC 8032 向量自测通过 | ✓ |
| `cacert.pem` | 最小 CA 根证书集（EXTRA） | ✓ |
| `seal.jpg` | 顶栏圆形头像（EXTRA） | ✓ |
| `icon_src.jpg` / `icon.png` | 应用图标；CI 用 ImageMagick 把 jpg 转 512 png | ✗ |
| `fonts/NotoSansSC-Regular.ttf` | 中文字体子集 | ✗ 改它必须重装 |
| `names.json` | 武学/门派/槽位 id→中文名 | ✗ 改它必须重装 |
| `buildozer.spec` | 打包配置 | ✗ |
| `config.json` / `gh.json` | 分区凭据、回写 token | ✗ 绝不提交，CI Secret 注入 |
| `update/code.zip` / `version.json` | 热更发布物（一对，必须同时推） | 发布物 |

### 2.2 关键约束

- **热更只替换热更包里的文件**。`main.py`、`names.json`、字体、图标、`buildozer.spec`、Java 层、新第三方依赖都不在包里 → 必须重打 APK 并重装。
- `buildozer.spec`：`source.include_exts = py,json,png,jpg,kv,atlas,ttf,otf,pem`（`pem` 是为了带 CA 包加的）。
- `apk/main.py` 的 `REQUIRED` 只校验 4 个老文件；**新增 `.py` 必须同时加进 `scripts/pack_update.py` 的 `FILES`**，否则包里没有，功能静默降级。
- 缓存与用户数据写 `ANDROID_PRIVATE`（`/data/data/com.fzjh.fzjhlookup/files/`），**绝不写 `live/`** —— 每次热更 `live/` 会被整个删掉重建。
- 当前热更包：12 个 `.py` + `cacert.pem` + `seal.jpg`，约 175 KB。

### 2.3 启动器怎么装热更包

`main.py` 流程（`ensure_code` → `install`）：

```
比对 version.json（主源失败切 jsDelivr）
  → 下载 code.zip → md5 校验
  → Ed25519 验签（sig 覆盖 version|md5|size + 整包字节；False 直接丢弃）
  → 解压到 live.new（带目录穿越防护）
  → is_valid_dir() 对 REQUIRED 逐个 compile() 语法检查
  → 写 live.new/version.txt → 删旧 live/ → rename 成 live/
  → 把 live/ 插到 sys.path 最前面
```

任一环节失败都记日志并继续用现有版本，所以**热更失败表现为"界面没变"，不会闪退**。

---

## 3. 通道 A：热更（日常 95%）

### 3.1 改代码 → 语法检查

```bash
cd /e/workbuddy2/fzjh-rank
python -m py_compile apk/app_ui.py apk/inline_input.py apk/lookup_core.py apk/fetch.py
```

### 3.2 不发布，直接塞进设备快验

改一次就打包发布太慢。用 `run-as` 覆盖 `live/`，并写 `version.txt = 99` 顶住自动热更：

```bash
D="-s 127.0.0.1:7555"; P=com.fzjh.fzjhlookup
"$ADB" $D shell am force-stop $P
for f in app_ui.py inline_input.py; do
  "$ADB" $D push "E:/workbuddy2/fzjh-rank/apk/$f" "/data/local/tmp/$f" >/dev/null 2>&1
  "$ADB" $D shell run-as $P cp "/data/local/tmp/$f" "files/live/$f"
done
"$ADB" $D shell run-as $P rm -rf files/live/__pycache__     # 必须删，否则跑旧字节码
printf '99' > E:/workbuddy2/_agent_tmp/v99.txt
"$ADB" $D push E:/workbuddy2/_agent_tmp/v99.txt /data/local/tmp/v99.txt >/dev/null 2>&1
"$ADB" $D shell run-as $P cp /data/local/tmp/v99.txt files/live/version.txt
"$ADB" $D shell am start -n $P/org.kivy.android.PythonActivity >/dev/null 2>&1
sleep 15
```

**快验期间加的 `print()` 调试日志，发布前必须清掉**（`grep -n 'print("\[' apk/*.py`）。

### 3.3 打包 + 验签

```bash
python scripts/pack_update.py "一句话说明"
cat apk/update/version.json
```

- 版本号读旧 `version.json` **自动 +1**，不要手改。
- 脚本同时算 md5、size，用 `.keys/update.key` 对 `version|md5|size|整包字节` 签名写 `sig`。
- `code.zip` 与 `version.json` 是**一对**，必须一起提交；只推一个 → md5 不匹配 → 客户端静默回退。
- 本地自检见 §9.3。

### 3.4 发布

**实际常用：GitHub API 建 commit**（本地 git 与远端经常分叉，直接 `git push` 会被拒；API 方式不需要 worktree，也不影响工作区）：模板见 §9.1。

要点：
- 用 `base_tree` 增量建 tree，只改本次涉及的文件，不会覆盖 CI 抓下来的数据文件；
- 顺序：`git/blobs` → `git/trees` → `git/commits` → `PATCH /git/refs/heads/main`；
- 每次都要推**源码 `.py` + `code.zip` + `version.json`**（源码供追溯与下次打包，两个发布物供客户端）。

**备选：本地 git 直推**（仅当本地与远端一致时）

```bash
git add apk/*.py apk/update/code.zip apk/update/version.json scripts/ docs/
git commit -m "热更 vXX：xxx"
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy \
  timeout 90 git -c http.proxy= -c http.sslBackend=openssl push origin HEAD:main
```

`-c http.sslBackend=openssl` 别省：Git for Windows 默认 schannel 会 `Failed to connect to github.com:443`。诊断：`curl -sI --noproxy '*' --max-time 12 https://github.com` 先看网络。

**推 `apk/*.py` 会顺带触发一次 APK 构建**（workflow 的 paths 命中 `apk/**` 但排除 `apk/update/**`），这是设计如此，不影响热更分发。

### 3.5 确认线上生效

GitHub Pages 有 30–90 秒缓存：

```bash
for i in 1 2 3 4 5; do
  sleep 12
  v=$(curl -s --noproxy '*' --max-time 15 \
      https://fzpaihang.github.io/lanlandeku/apk/update/version.json | grep -o '"version": *[0-9]*')
  echo "try$i: $v"; echo "$v" | grep -q 45 && break
done
```

### 3.6 全量验收（最可靠）

删掉 `files/live` 再启动，等价于老用户升级：

```bash
D="-s 127.0.0.1:7555"; P=com.fzjh.fzjhlookup
"$ADB" $D shell run-as $P rm -rf files/live
"$ADB" $D shell am force-stop $P
"$ADB" $D logcat -c
"$ADB" $D shell am start -n $P/org.kivy.android.PythonActivity >/dev/null 2>&1
sleep 45
"$ADB" $D shell run-as $P cat files/live/version.txt       # 应等于线上版本
"$ADB" $D shell run-as $P ls files/live | tr '\n' ' '
"$ADB" $D logcat -d | grep -E "\[launcher\]|\[tls\]|NotImplementedError|Traceback" | tail -8
```

### 3.7 回归清单

- [ ] 查询页首屏、圆形头像、分区下拉
- [ ] 输入框：点开 → 打字 → 点外面收起 → 再点回来 → **退格能删**（见 §8）
- [ ] 完整查询出结果页：角色名、指标、准备位、顶栏「刷新」与返回箭头
- [ ] 结果页按系统返回键回查询页，不退出 App
- [ ] 内嵌高手榜能开能关，关完还能继续操作
- [ ] 缓存命中副标题带「· 缓存」，点「刷新」后标记消失
- [ ] 无水滴之外的残留、`logcat` 无 `NotImplementedError` / `Traceback`

### 3.8 回滚

客户端只升不降，**不能把 version 改小**。正确做法：

1. 从 GitHub 历史 commit 取回旧版文件（模板 §9.2），或把代码恢复成上一版；
2. 重新 `pack_update.py "回滚：xxx"` → 得到更大的版本号；
3. 按 §3.4 推送。

v45 就是这么做的：从 `7b8c19e1`（v42）取回 `app_ui.py` + `inline_input.py`，其余文件保持最新。

---

## 4. 通道 B：重打 APK

### 4.1 什么时候必须

| 改动 | 原因 |
|---|---|
| `main.py`（启动器、验签、TLS、更新源） | 在 APK 内，热更换不到 |
| 新增 Java 层 / `InputConnection` | 同上 |
| `names.json`、字体、图标、应用名、`buildozer.spec` | 内置资源/配置 |
| 新第三方依赖 | `requirements` 变了 |

⚠️ 改 `buildozer.spec` / `main.py` 曾经会因为 CI 缓存 key 里带这两个文件的 hash 而**连带换掉自动生成的调试签名密钥** → 用户覆盖安装报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`，必须卸载重装。缓存 key 已固定为 `buildozer-${{ runner.os }}-stable-v1`，不要再改回带 hash 的写法。

### 4.2 CI 配置要点（`.github/workflows/build-apk.yml`）

- `runs-on: ubuntu-22.04`（新镜像 ant 工具链会挂）；Python 3.10（p4a 锁 `pyjnius==1.7.0`）
- `p4a.branch = v2024.01.21`，别升 master；只编 `arm64-v8a`
- 步骤「生成应用图标」：`convert icon_src.jpg -resize 512x512^ -gravity center -extent 512x512 -strip icon.png`，仓库不用提交生成的 png
- 首次构建下 2–3 GB SDK/NDK，40–60 分钟；命中缓存 15–20 分钟
- 上传 artifact `fzjh-lookup-apk`，再 `gh release upload apk-v1.0 … --clobber` 覆盖**固定文件名** `fzjh-lookup-v1.0.apk`（网页下载按钮写死这个 URL，不能改名）

```bash
gh workflow run build-apk.yml --repo fzpaihang/lanlandeku
gh run list --repo fzpaihang/lanlandeku --limit 3
```

### 4.3 取产物并交付

下载 Release asset 到 `dist/`，校验 zip 有效、包内含 `seal.jpg`、应用名字符串已更新，然后直接把文件交给用户。

```bash
TOK=$(cat E:/workbuddy2/_agent_tmp/gh_token.txt)
AID=$(curl -s --noproxy '*' -H "Authorization: token $TOK" \
  https://api.github.com/repos/fzpaihang/lanlandeku/releases/latest \
  | python -c "import sys,json;print(json.load(sys.stdin)['assets'][0]['id'])")
curl -sL -H "Authorization: token $TOK" -H "Accept: application/octet-stream" \
  "https://api.github.com/repos/fzpaihang/lanlandeku/releases/assets/$AID" \
  -o "dist/霜霜妙妙屋-vXX.apk"
```

### 4.4 安装注意

- 覆盖安装保留 `/data/data/.../files/`（含 `live/`、缓存），热更链路照常；
- **卸载重装**会清空 `live/`、最近查询和 UID 缓存，App 先跑内置代码再自动升到线上最新；
- 重装后首次启动等 10–30 秒做热更检查，正常。

---

## 5. 通道 C：数据与网页（不动 APK）

### 5.1 武学位置表

```bash
python scripts/build_skill_class.py            # 用本地缓存 apk/data/skill.json.gz
python scripts/build_skill_class.py --fetch    # 上游更新才需要
python -m py_compile apk/skill_class.py && python scripts/pack_update.py "更新武学位置表"
```

单条纠错直接改 `apk/skill_class.py` 里的 `CLASS[...]`，别改 `skill_groups.py` 的关键词兜底。`skill_class.py` 在热更包内。

### 5.2 服务端数据（推 main 即可，用户下次打开生效）

| 数据 | 路径 | 生成 |
|---|---|---|
| 昵称索引 | `data/lookup-index.json` | `scripts/build_lookup_index.py` |
| 昵称回写 | `data/extra-names.json` | APK 自己提交 |
| 隐私名单 | `data/hidden.json` | 手改后要重跑 build_lookup_index |
| 榜单 / 经验快照 | `data/servers/<key>/{gaoshoubang,exp-history}.json` | `scripts/fetch.py` / `merge_exp.py`（Actions 定时） |

经验快照有两套口径：11-11 那批是**排行榜浮点值**，之后是 `merge_exp` 合并的**档案整数值**，两者相减会出现假增量。只保留 `src == "profile"` 的快照；`assets/exp.js` 的当前值与基准都取快照，保证同源。

### 5.3 中文字体子集（`fonts/NotoSansSC-Regular.ttf`）

```bash
python scripts/build_font_subset.py            # 源：C:/Windows/Fonts/NotoSansSC-VF.ttf
```

- 做 `instancer` 固定 `wght=400` → 子集化 21637 字 → 单体 ttf（7.1 MB）。
- 字符集：CJK 基本区全量 + ASCII + Latin-1 + CJK 标点 + 全角 + **几何符号 U+25A0–U+25FF**（折叠箭头 `▶` 在这一区，漏了整片变豆腐块 ☒）。
- Kivy 不做字体回退，缺一个字就是豆腐块；MuMu 是 AOSP 一定有系统字体，**这个故障在模拟器上永远复现不出来**。
- `source.include_exts` 里 `.ttf` 有，但热更包 `EXTRA` 不带字体 → 改字体必须重打 APK。调试时把字体推到 `files/live/fonts/` 可临时生效。

### 5.4 网页静态资源缓存戳（必须做）

改完 `assets/*.js` / `style.css` 后：

```bash
python scripts/stamp_assets.py
```

它把 `index.html` / `exp.html` / `lookup.html` 里 `./assets/xxx.js?v=<md5前8>` 刷成新哈希，内容没变则不动文件。

⚠️ **漏跑这一步的现象**：代码推上线了，但 App 内 WebView 继续跑缓存里的旧脚本，页面上完全看不到新功能（转数筛选、移动端排序都踩过）。桌面浏览器硬刷新能看到，App 里看不到，很容易误判成逻辑写错。

---

## 6. 验证工具箱

### 6.1 截图

```bash
"$ADB" $D exec-out screencap -p > E:/workbuddy2/_agent_tmp/x.png 2>/dev/null
```

### 6.2 uiautomator 读真实控件文本（比截图可靠）

MuMu 偶尔画面冻结，截图会误导。`uiautomator dump` 读的是控件树：

```bash
"$ADB" $D shell uiautomator dump /sdcard/u.xml >/dev/null 2>&1
"$ADB" $D shell "cat /sdcard/u.xml" > E:/workbuddy2/_agent_tmp/u.xml 2>/dev/null
python -c "
import re,io
x=io.open('E:/workbuddy2/_agent_tmp/u.xml',encoding='utf-8',errors='ignore').read()
et=[t for t in re.findall(r'<node[^>]*>',x) if 'EditText' in t]
print(re.search(r'text=\"([^\"]*)\"',et[0]).group(1) if et else '（无原生框）')
"
```

v45 的验收就是靠它确认 `123456 → 退格×3 → 123`。

### 6.3 录屏抽帧

ffmpeg 静态版已放在 `E:/workbuddy2/_agent_tmp/ffmpeg.exe`：

```bash
cd E:/workbuddy2/_agent_tmp
./ffmpeg.exe -hide_banner -loglevel error -i QQ20261114-141051.mp4 -vf "fps=2,scale=540:-1" vf%03d.png
```

`adb shell screenrecord` 可录设备操作；逐帧找"水滴/残影"出现和消失的时机。

### 6.4 日志

```bash
"$ADB" $D logcat -d | grep -E "\[launcher\]|\[tls\]|\[inline\]|\[native_input\]|NotImplementedError|Traceback" | tail -20
```

`NotImplementedError` 尤其重要：pyjnius 的 `@java_method` 签名写错时不会在定义处报错，只在 Java 回调时抛，现象会跑到完全无关的地方。

### 6.5 模拟器局限

- MuMu 里只装了**搜狗**输入法（`settings get secure default_input_method` 可查），换不了别的 IME 做对比。
- 早期版本 `adb shell input text` 的字到不了 Kivy；现在有原生 EditText 覆盖层，注入有效。
- 系统低内存杀进程（`lowmemorykiller`），界面突然变桌面不是崩溃，重启即可。
- 截图里出现的"水滴"是系统 `HandleView` 悬浮窗口，不随内容滚动，切页后仍在屏幕固定位置（§8）。

---

## 7. 硬规则与踩过的坑

### 7.1 界面 / Kivy

| 坑 | 正确做法 |
|---|---|
| 宽度重复套 `dp()` | `txt_button(width=104)` 传纯数字，内部已乘 dp |
| 手算列表高度 | 绑 `minimum_height`，别 `dp(35) * len(items)` |
| `add_widget(w, index=0)` 想置顶 | 竖向 BoxLayout 的 children 逆序铺，`index=0` 落到最下面；置顶用 `index=len(children)` |
| BoxLayout 横向子项贴底 | 小胶囊用 `_vcenter()` 包一层 |
| `on_touch_down` 立即触发动作 | ScrollView 里会误触；改「按下记坐标 + 抬手位移 <12dp 才触发」 |
| 弹层/结果页按返回直接退出 | `_on_key` 三级：网页 → 弹层 → 结果页回查询页 → 才退出 |
| `_deny()` / `_web_fail()` 用 `clear_widgets()` | 换成插卡到 `body.children` 末尾，保留表单与返回入口 |
| 禁用态文字变半透明白 | 显式设 `disabled_color` |
| 弱文字对比度 | `C_MUTED` 已压到 `#6E635A`（米底 4.9:1） |
| 依赖系统字体路径 | 字体打包进 APK（§5.3） |
| 拼音 id 参与英文关键词匹配 | 只对含大写的驼峰 id 做英文匹配 |

### 7.2 pyjnius / 输入框

| 坑 | 正确做法 |
|---|---|
| 传 Python str 给 Java `setText` | 显式 `autoclass("java.lang.String")(s)` |
| `getParent()` 静态类型是 `ViewParent` | `cast("android.view.ViewGroup", parent).removeView(root)` |
| `@java_method` 签名参数个数写错 | 必须和 Java 声明逐参数对齐。`beforeTextChanged` 是 `(Ljava/lang/CharSequence;III)V`，写成 `II` 会每次文字变化抛 `NotImplementedError` |
| `setTextSize(unit, px)` 的 unit | **PX=0 / DIP=1 / SP=2**。传 1 会把像素当 dp 再乘密度，字大一倍顶出框 |
| `setSelectAllOnFocus(True)` | 一聚焦就全选 → 出选择手柄；当前 v42 主路径仍有聚焦全选（能直接覆盖输入），这是已知取舍 |
| 新 `addContentView` 的 View 立刻 `showSoftInput` | 还没 attach 完，IME 连不上；需要延迟到下一帧 |
| 用「失焦 + `setInputType(TYPE_NULL)`」消手柄 | **禁止**：会让输入法连不上，退格失效（v43 的教训） |
| 点在输入框自己也先 `hide()` | 收/弹一次会留下手柄；用 `_INLINE_OWNER` 记住归属，点它身上跳过 hide |
| 依赖 Kivy 软键盘 / `keyboard_height` | 见实施记录 §10；SDL2 构建里 `keyboard_height` 恒 0，看 `dumpsys input_method` 的 `mInputShown` |
| WebView 抢走输入法焦点 | 关闭时 `hideSoftInputFromWindow` + `clearFocus` + `removeView` + `destroy()` |

### 7.3 更新包签名与 TLS

- 签名用纯 Python `ed25519.py`（只依赖 hashlib），已对 RFC 8032 向量自测；私钥**只在本地 `.keys/`**，公钥硬编码在 `main.py`。
- 签名覆盖 `version|md5|size|整包字节`，改包体或改版本号都会验签失败。
- 两个 TLS 上下文（`main.py` 更新通道、`fetch.py` 游戏接口）在**找不到内置 CA 时都会降级**到 `CERT_NONE` 并打日志，保证老 APK 不至于完全不能用。区别在于更新通道还有 **Ed25519 签名**兜底：即使证书没校验，包内容被改动也会验签失败被丢弃。改这两处要重装 APK。
- **完整 Mozilla CA 包（163KB）在设备 OpenSSL 上会报 `SSLError(9, '[X509] PEM lib')`**，整包不可用；只能用最小根证书集。

### 7.4 构建与发布

- 不要 `git push --force` 到 main（会顶掉 Actions 抓下来的数据）。
- 不要把 `config.json` / `gh.json` / `.keys/` 提交进仓库。
- CI 缓存 key 必须保持固定（§4.1），否则改 spec 就换签名密钥。
- 发布时 `code.zip` 与 `version.json` 必须同时推。
- 调试用的 `print()` 发布前清掉。
- 每次改完追加 `docs/UI优化-实施记录.md`，并把关键结论写进工作区记忆。

---

## 8. 输入方案专题（当前状态必读）

### 8.1 版本时间线

| 版本 | 做法 | 结果 |
|---|---|---|
| v40 | 修 `setTextSize` 单位（PX=0）、收起顺序 | 字号正常，仍有残影 |
| v41 | 修 `beforeTextChanged` 签名 | 部分改善 |
| **v42** | 点框自身不收（`_INLINE_OWNER`）、`setCursorVisible(False)` | **能正常删除，仅有光标残影** |
| v43 | 收起时 Kivy 输入框失焦 + `setInputType(TYPE_NULL)` + 强制重绘 | 残影没了，**退格失效** |
| v44 | 改系统 AlertDialog 主路径 | **更难用**：弹窗里能删，确定/点外面后主界面仍旧值 |
| v45 | **整体回退到 v42** | 删除与查询恢复正常，残影回来 |
| **v46** | **`RoundInput.use_handles=False`** | **残影彻底消失，其余功能全部正常** |

### 8.1.1 先看结论（v46 已解决）

水滴**不是** Android 的 `HandleView`，是 **Kivy `TextInput` 自己画的光标手柄**
（`use_handles`，贴图 `shape-drop.png`）。它画在 App 的 GL 画布上，所以不进
`dumpsys window`、不是独立图层、杀进程也不消失，**而且会跟着页面滚动**。

修复就一行，见 §8.5。§8.2–§8.4 保留的是当时的（错误）推理过程，作历史记录看，
不要照着做。

### 8.2 为什么会有残影（原理）

- 网页/原生 App：输入框是标准 View 树里的一员，"删字 → `onTextChanged` → `Editor` 收手柄 → `invalidate` → 整棵树重绘"是**同一条事件链**。
- 本 App：Kivy 界面是 SDL 用 OpenGL 画在 Surface 上，Android 不认识它；为了输入中文额外 `addContentView` 了一个原生 EditText。于是"删字"走 Kivy 软件层、"手柄"走 Android `Editor`，中间**没有跨层通知通路**；手柄是独立 `PopupWindow`，底层 Surface 又是独立合成层不会被强制补帧 → 上一帧像素留在屏幕上。

### 8.3 当前状态（v46，已解决）

- 主路径：内联原生 EditText 覆盖层（`inline_input.py`）
- 系统对话框（`native_input.py`）保留为兜底，不做主路径
- **残影已消失**：`RoundInput.use_handles = BooleanProperty(False)`，Kivy 不再生成手柄
- 判断原则：**能用 > 好看**。发现"修 A 坏 B"且 B 更严重时直接回退，不要继续叠加补丁

### 8.4 曾经的"彻底解决路线"（已作废）

v45 曾判断"只能靠完整 `InputConnection` 或换渲染层"，**这个判断是错的** ——
真凶是 Kivy 自己的 `use_handles`，一行就解决了，不需要动 Java 层、不需要重打 APK。

保留此条只为提醒：定性错误会导致方案成本被严重高估。下次遇到"某个像素不消失"，
先按 §8.5 的判定表走一遍，再下结论。

### 8.5 怎么判定一个残影到底是谁画的（可复用）

| 检查 | 命令 | 说明 |
|---|---|---|
| 是不是独立窗口 | `dumpsys window windows` 找 `PopupWindow`/`HandleView` | 有 → 可能是 IME/系统手柄 |
| 是不是独立图层 | `dumpsys SurfaceFlinger --list` 前后对比 | 有差异 → 独立 Surface |
| 杀 App 还留不留 | `am force-stop <pkg>` | 还留 → 已画进帧缓冲，是**旧帧**或**同层残留** |
| 杀 IME 还留不留 | `am force-stop <ime>` | 还留 → 与输入法无关 |
| **跟不跟着页面滚** | 滚动后再截图对比坐标 | **跟着滚 → 画在 App 自己的画布上，是 App/框架画的** |

最后一条最快、最决定性。本次就是靠它翻案的。

定位到"框架画的"之后，直接去查框架源码里对应的 widget 开关（Kivy 的
`use_handles`/`use_bubble`），而不是继续在 Android 侧打补丁。

### 8.6 残影回归用的检测脚本

```bash
python E:/workbuddy2/_agent_tmp/detect.py <screenshot.png>
```

按颜色找那颗浅蓝水滴（`R 100-160 / G 180-220 / B 210-245` 且 `B > R+60`），
输出 `found` / `count` / `bbox` / `center`。比人眼看截图可靠，回归时逐张跑。

⚠️ **MuMu 会画面冻结**：连续 `screencap` 可能拿到完全相同的 PNG（连状态栏时钟都不走）。
判定 UI 状态以 `uiautomator dump` 为准，截图只用于看像素残留。

---

## 9. 常用脚本模板

### 9.1 GitHub API 发布（最常用）

```python
import base64, io, json, urllib.request
TOK = io.open('E:/workbuddy2/_agent_tmp/gh_token.txt', encoding='utf-8').read().strip()
REPO, API = 'fzpaihang/lanlandeku', 'https://api.github.com'
def call(m, p, pl=None):
    d = json.dumps(pl).encode() if pl is not None else None
    r = urllib.request.Request(API + p, data=d, method=m)
    r.add_header('Authorization', 'token ' + TOK)
    r.add_header('Accept', 'application/vnd.github+json')
    r.add_header('Content-Type', 'application/json')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(r, timeout=60) as x:
        return json.loads(x.read().decode())

base = call('GET', '/repos/%s/git/ref/heads/main' % REPO)['object']['sha']
ts = call('GET', '/repos/%s/git/commits/%s' % (REPO, base))['tree']['sha']
files = ['apk/app_ui.py', 'apk/update/code.zip', 'apk/update/version.json']  # 按实际改动
entries = []
for f in files:
    sha = call('POST', '/repos/%s/git/blobs' % REPO,
               {'content': base64.b64encode(open(f, 'rb').read()).decode(),
                'encoding': 'base64'})['sha']
    entries.append({'path': f, 'mode': '100644', 'type': 'blob', 'sha': sha})
tree = call('POST', '/repos/%s/git/trees' % REPO, {'base_tree': ts, 'tree': entries})
new = call('POST', '/repos/%s/git/commits' % REPO,
           {'message': '热更 vXX：xxx', 'tree': tree['sha'], 'parents': [base]})
call('PATCH', '/repos/%s/git/refs/heads/main' % REPO, {'sha': new['sha'], 'force': False})
```

### 9.2 从历史 commit 取回文件（回滚用）

```python
# ref 用 git log 查到的 sha（如 v42 = 7b8c19e1）
r = urllib.request.Request(API + '/repos/%s/contents/%s?ref=%s' % (REPO, 'apk/app_ui.py', SHA))
r.add_header('Authorization', 'token ' + TOK)
with op.open(r, timeout=60) as x:
    data = base64.b64decode(json.loads(x.read().decode())['content'])
io.open('apk/app_ui.py', 'wb').write(data)
```

### 9.3 本地验签自检

```python
import json, io, sys
sys.path.insert(0, 'apk'); import ed25519
m = json.load(io.open('apk/update/version.json', encoding='utf-8'))
b = open('apk/update/code.zip', 'rb').read()
pk = ed25519.public_key(open('.keys/update.key', 'rb').read())
msg = ('%s|%s|%s|' % (m['version'], m['md5'], m['size'])).encode() + b
print(ed25519.verify(pk, msg, bytes.fromhex(m['sig'])))
```

### 9.4 缓存戳重算

```bash
python scripts/stamp_assets.py     # 改完 assets/*.js 或 style.css 必跑
```

---

## 10. 故障排查表

| 现象 | 先查什么 |
|---|---|
| 改了代码界面没变 | `version.txt` vs 线上 `version.json`；号没涨 / md5 不匹配 / Pages 没刷 / **HTML 的 `?v=` 没刷** |
| 热更后打不开 | `logcat \| grep -i python`，看 `is_valid_dir` 报错；启动器会回退内置代码 |
| 验签失败 | `.keys/update.key` 是否换了、公钥是否还对得上、`code.zip` 与 `version.json` 是否同时推 |
| 启动慢十几秒 | `[launcher]` 日志；等 8 秒版本检查 + 25 秒下载，正常 |
| TLS 报错 | `[tls]` 日志；确认 `cacert.pem` 在 `live/` 或 app 目录，且是最小根证书集 |
| 内嵌网页跳浏览器 | `logcat` 找 `JavaException`，多半是 pyjnius 类型转换 |
| 输入框打不了字 / 退格无效 | `uiautomator dump` 看 EditText 是否存在、文本是否变化；查 `NotImplementedError`；对照 §8 |
| 水滴/残影不消失 | v46 已修复（`use_handles=False`）；若复现，先按 §8.5 判定是谁画的，再动代码 |
| 武学全挤在「其他」 | `run-as cat files/live/skill_class.py \| head`，多半热更包漏文件 |
| 查询 `errcode=-1` / 空数据 | 一个 uuid 只保留一个会话，并发互踢；等 2 分钟重试 |
| 线上 404 | 文件是否在 `apk/update/`、是否推上 main；Pages 源是 main 根目录 |
| 覆盖安装报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 签名证书变了：检查 CI 缓存 key 是否被改回带 hash 的写法 |

---

## 11. 不要做的事

- 不要手改 `apk/update/version.json` 的版本号。
- 不要 `git push --force` 到 main。
- 不要提交 `config.json` / `gh.json` / `.keys/`。
- 不要在 `live/` 里放缓存或用户数据。
- 不要把 `dp()` 套在已经是 dp 的参数上。
- 不要为了省一次构建把 `apk/**` 从 workflow 的 `paths` 里去掉。
- 不要改回带 hash 的 CI 缓存 key。
- **不要为了消光标手柄再做「失焦 + `setInputType(TYPE_NULL)`」**（v43 已证明会废掉退格）。
- **不要在没做 §8.5 判定前就假设残影是 Android 的窗口**（v40–v45 因此白改了六版）。
- 不要在修 bug 时夹带架构级改动；遇到需要重打 APK 的改造，先交付可用版本再单独排期。
- 不要只推 `code.zip` 或只推 `version.json`。
- 不要漏跑 `stamp_assets.py`。

---

## 12. 相关文档与约定

| 文档 | 内容 |
|---|---|
| `docs/UI优化-实施记录.md` | v30–v45 逐次改动的背景、推理与验证（§13 起是签名/TLS/输入） |
| `docs/武学分类校对表.md` | 武学分组人工校对 |
| 工作区记忆 `.workbuddy/memory/2026-11-13.md`、`2026-11-14.md` | 跨会话的关键结论与用户偏好 |

**用户约定**：
- 所有产出、脚本、临时文件放 `E:\workbuddy2` 下，不同任务区分目录，尽量不写 C 盘；
- 遇到决策不明确先问，不要自己决定；
- 架构拆分 / 完整 `InputConnection` 这类"要很久"的改造先不动，只留记录；
- 优先保证「能用」，视觉瑕疵可以让步。
