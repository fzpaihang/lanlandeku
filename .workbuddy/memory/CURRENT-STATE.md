# 项目当前状态（交接用）

> 这份文件代替「翻聊天记录」。**新会话先读它，再按需读具体文档**。
> 最后更新：2026-11-20 23:10（**名人堂上线：新静态页 hall.html + 抓取层支持 board=4**——游戏「名人堂」（boardType=4，指标=**江湖阅历** yueli）第一次接入网页端。<br>**新页面** `hall.html`（3985 B）+ `assets/hall.js`（13901 B，独立 IIFE，**不引 app.js**）：5 列「名次 / 昵称 / 门派 / 等级 / 江湖阅历」，`#sortbar` 三个 chip（名次 / 江湖阅历 / 等级），点任意一行弹 `profile.js` 档案弹窗（`PF_CACHE`+`PF_SEQ` 丢弃迟到回调、`history.replaceState` 同步 `?uid=`）。**默认按 rank 升序、绝不按 yueli 自排**——11 区里有 4 个区（huawei/ios2/taptap_2/taptap_4）游戏原始名次与阅历不是严格倒序（`yueli_desc=False`），自己重排会造出假名次。全程零 innerHTML。`index.html`/`exp.html`/`hall.html` 三页互加入口。<br>**抓取层**：`scripts/fetch.py` 新增 `BOARD_FILE = {1: "gaoshoubang.json", 4: "hall.json"}`，**board≠1 时 maxRank/indexRank 置空、不写 index-extra.json、不更新 exp-history.json、不碰 data/shadow.json**（这四样都是高手榜专属，混进去会污染）；排名变化对比上一版 hall.json。`scripts/fetch_profiles.py` 把同目录 `hall.json` 的行并入 targets（`setdefault` ⇒ 同 uid 高手榜行优先，档案名次仍按高手榜），且**在 maxRank 截断之后追加**——名人堂每区只有 9–10 人，页内详情依赖档案，不能被截掉。`scripts/plan_refresh.py` 新增 `HALL_TARGET="hall11"` + `plan_full()` 返回 `(target, label, board, servers)`；`refresh.yml` 新增 `0 12 * * *`（北京 20:00）、手动触发选项 `hall11`，并把各步的 `T` 从 `steps.t.outputs.target` 改成 **`servers`**（target 是任务标记，servers 才是能喂给 `--server` 的分区串），抓榜步按 `B` 追加 `--board 4 --max-pages 1`（该榜每区只 10 人，翻页返回同样的 10 人）。<br>**隐藏口径**：名人堂与高手榜**同一套**隐藏剔除——`hidden.json` 全部 5 人（含 2 个 shadow 玩家）都从 hall.json 剔除，剔除后 `rank` 重排成 1..N（**名人堂不做影子豁免**，影子榜 `data/shadow.json` 仍只属于高手榜）。<br>**数据**：11 区 `data/servers/*/hall.json` 共 **108 行**（4399 9 / taptap_3 9 / 其余各 10），`rank == 1..N` 全连续、无隐藏残留（4399 剔的是玲珑望月 4047491326，taptap_3 剔的是咸味桃酥 21079748748）。<br>**测试**：`hall_web_test.js` **35 项 PASS / 0 FAIL**（默认不重排、浮点阅历取整、chip 与表头双向切换、点行拉 `profiles/<uid>.json`、二次点走缓存、404 显示「读取失败」、移动端卡片、空数据、hall.json 404 不白屏）、`hall_all_servers_smoke.js` **11 区 PASS 33/0**、`hall_web_smoke.js` 7/0、`hall_profile_smoke.js` 3/0；`preflight` **13 通过 / 2 警告 / 0 失败**。**Edge headless 真实渲染已验**（本地 `serve.py 8791`，桌面 1200×1100 + 移动 420×1400），5 列与千分位正常。<br>**发布**：`publish.py` 提交 **`e1488429a0a8`**（22 个文件：hall.html + hall.js + 11 个 hall.json + style.css + 3 个 html + 4 个脚本 + refresh.yml）。**APK 热更包未动（仍 v87）**——本功能只做网页端。<br>上一条 2026-11-20 08:45（**经验变化页新增「排名趋势」列**——按日均推算「多久后超过上一名 / 被下一名超过」。用户问「能不能根据日均数据判断多久之后排名提升/下降」。<br>**口径**：`assets/exp.js` 新增 `etaText(d)` / `computeEta(rows)` / `etaSpans(r)`。关键点是**不能拿游戏 rank±1 当邻居**——taptap 98 行里 rank 与经验值有 33/97 对逆序（游戏名次是分批刷新缓存），所以按 `expN` 降序自建经验序 `ord`，取 `ord[i-1]` / `ord[i+1]` 当上家下家。<br>**公式**：`relUp = me.perDay - up.perDay`，>0 时 `etaUp = max(0, up.expN - me.expN) / relUp`；`relDn = dn.perDay - me.perDay`，>0 时 `etaDn = max(0, me.expN - dn.expN) / relDn`；两边都没有就不显示。`etaText`：<1小时 / N小时 / N.N天（<30）/ N天（<365）/ >1年。<br>**UI**：桌面表格在「日均」和「增幅」之间插第 8 列 `th.c-eta[data-key=eta]`「排名趋势」（`td.c-eta` 内 `div.eta` 两个 `span.eta-i.up/.dn`，↑红 ↓绿，无值显示 `span.eta none` '—'）；移动端卡片第 3 行同款 `div.eta`（`flex-direction:row`）；`#sortbar` 加第 4 个 chip「排名趋势」（null 沉底、默认 asc），表头点击也支持。<br>**实测**（taptap 真实快照，98 行 × 8 列）：eta 非 '—' **75 行**，例 `35 我要验牌 ↑98天` / `37 无瑕玉 ↑4.9天` / `31 连城璧 ↑54天↓98天`。<br>**测试**：`E:\workbuddy2\_agent_tmp\exp_grow_test.js` 扩到 **17 项 ALL PASS**（新增⑫–⑰：第 1 名只显示 ↓、第 2 名只显示 ↑、最后一名 '—'、列数=8 且 pct 在最后、名次倒挂时仍按经验序取邻居、移动端卡片第 3 子节点是趋势行）；`shadow_exp_smoke.js` 10 项、`shadow_web_test.js` 48 项、`test_expN_sort.js` 全 PASS。<br>**发布**：`stamp_assets.py` → `style.css=6ba815ea servers.js=ea1c2f78 exp.js=9072d485`；`preflight` 13 通过 / 2 警告 / 0 失败；`publish.py` 提交 **`de99ce987eff`**；线上 `exp.html` 已指向 `exp.js?v=9072d485`、`assets/exp.js` 17392 B 含 `computeEta`。<br>上一条 2026-11-20 08:05（**APK 口令框文案「影子榜」→「隐藏榜」**，v87，提交 `99617b989922`。用户要求与网页端统一。改的是纯文案 + 注释，逻辑零改动：`apk/app_ui.py:2107` 对话框标题 `NATIVE.ask("网页口令：打开网页会自动进隐藏榜", ...)`、`:2176` 保存成功提示 `self._web_key_tip("口令已保存，打开网页即可看到隐藏榜", C_ACCENT)`；另外 4 处注释同步（`app_ui.py:2051`/`:2071`/`:2077`/`:2300`、`lookup_core.py:56`/`:421`）。改后 `grep 影子 apk/` = 0。测试：`webbialog_test.py:74-75` 里写死的提示文案断言同步改「隐藏榜」（否则该用例必 FAIL），改后 **20 项 ALL PASS**；`webkey_test.py` 25 项、`appbar_touch_test.py` 23 项全 PASS。`pack_update.py` → **v87** / 12 文件 / 205.6 KB / md5 `bbd1e27deb3db6a4ef7bf86144e5bd6d` / size 210550 / 签名 `e9c9930148149ac2…`；`zipver2.py` 14 项全 MATCH bad:0。`preflight` **13 通过 / 2 警告 / 0 失败**（WARN 照旧）。`publish.py` 提交 **`99617b989922`**（app_ui.py / lookup_core.py / code.zip / version.json）。上一条 2026-11-20 01:55（**经验变化页：基准快照缺人时按 uid 逐行回退**——用户问「经验增长页面的苍松区翱翔天际怎么没有经验变化」。<br>**根因（数据 + 前端各一半）**：`data/servers/taptap/exp-history.json` 里 **2026-11-16 06:30 那条快照的 `exp` 字典没有 6479440（翱翔天际）**。那一轮 `git show 31dddaf:data/servers/taptap/profiles/6479440.json` = **MISSING**（档案文件当时不存在），且他那一轮也不在榜单上（`31dddaf` 的 gaoshoubang 里搜不到 6479440，下一轮 `470e79a` 才回来 rank=25），于是 `merge_exp.py` 的 exp_map 三轮规则（本轮 fresh / 沿用 prev_map / 掉榜继承）全都没命中，他就从这条快照里消失了。前端 `assets/exp.js` 的 3 天窗口只取**一条全局基准快照**（`cutoff = latest.ts - 3*86400` 后从后往前找第一条 `ts <= cutoff`），11-19 22:02 的最新快照反查正好落在 11-16 06:30 这条 → `baseExp = undefined` → 该行 grow/perDay/pct 全 null → 页面显示「—」。<br>**修法（只改前端，不动历史数据）**：`assets/exp.js` 新增 `baseCache` + `baseSnapFor(uid)`——先用全局基准快照；若它缺这个 uid，就**按 uid 再往回找一条「`ts <= cutoff` 且含该 uid」的快照**兜底，仍要求 `bSnap !== latest`（绝不拿最新快照自比出假 0）。行级区间天数用 `rowDays = (latest.ts - bSnap.ts)/86400`，日均分母 `max(WINDOW_DAYS, rowDays)`，避免回退到更早快照后日均被系统性高估。<br>**影响面**：最新快照里缺在基准中的只有 3 个 uid——6479440 翱翔天际、4168426 微生念、6622657 微生梦（后两个是影子玩家，本来就只从 11-19 那条才进快照，属预期）。修后实测翱翔天际 增长 `+794.9万` / 日均 `+181.9万` / 增幅 `+0.14%`（基准退到 11-15 13:10，区间 4.0 天），**全榜 98 行再无一行是「—」**。<br>测试：新建 `E:\workbuddy2\_agent_tmp\exp_grow_test.js`（vm 加载 exp.js + DOM 桩，**11 项 ALL PASS**：逐 uid 回退、区间天数、日均分母、更早快照也没有时仍显示「—」、移动端卡片一致、真实 taptap 数据回归）；`shadow_exp_smoke.js` 里两处写死 `'影子'` 的徽章断言改成 `'隐藏'`（**10 项 ALL PASS**）；`shadow_web_test.js` 48 项、`test_expN_sort.js`、`test_snap.js` 全 PASS。<br>发布：`stamp_assets.py` → `exp.html` 更新 `exp.js=e99b3931`；`preflight` **13 通过 / 2 警告 / 0 失败**；`publish.py` 提交 **`61d2d72f36f2`**（assets/exp.js + exp.html）。<br>**注意**：GitHub Pages 有缓存，发布后立刻拉 `https://fzpaihang.github.io/lanlandeku/assets/exp.js` 仍可能是旧内容（本次实测 Pages 侧还是 13419 B 的旧文件、戳仍是 `exp.js?v=30c79641`），而 **raw 源已生效**（`https://raw.githubusercontent.com/fzpaihang/lanlandeku/main/assets/exp.js` = 14426 B、含 `baseSnapFor`/`rowDays`、`exp.html` 里戳是 `exp.js?v=e99b3931`）——核查要以 raw 为准，Pages 等 30–90 秒缓存。上一条 2026-11-20 01:50（**热更 v86：点底部入口卡不再误弹口令框 + 口令框改回普通键盘**——用户三条诉求之二「点底部『全服高手榜』卡也弹口令框」与之一「口令框唤起的是不是安全键盘」。<br>①**误弹框根因**：`apk/app_ui.py` 的 `_right_down()` 只判 `_right_cb/_right_long_cb` 非空和按钮可见，**没判触摸点是否落在「网页」按钮上**——Kivy 的 `bind(on_touch_down=...)` 是事件栈回调，事件从 `Root→ScrollView→inner→appbar` 一路派发下来只要父级 collide 就会调它，于是**页面任意位置按下都会起 0.6 秒长按计时器**，滚到底点「全服高手榜」卡时手指停留稍久就命中 `_right_timeout` 弹口令框（卡片本身的 `_entry_release` 只开内嵌 WebView，没有任何口令逻辑）。修法：新增 `_right_on_btn(self, touch)` 用 `right_btn.collide_point(touch.x, touch.y)` 做命中判断，`_right_down` 里 `if not self._right_on_btn(touch): return False`。<br>**踩坑**：第一版用 `btn.to_window(btn.x, btn.y)` 求窗口矩形，真机长按「网页」也不弹了——插桩 logcat 打出 `touch=(794.1,2194.0) btn.y=2120.0 h=145`，说明 Kivy 派发到 AppBar 的 touch 坐标**已经和 `right_btn.pos` 同一套内容坐标系**，不该再 `to_window`。改用 `collide_point` 后长按/短按互不干扰。<br>②**安全键盘**：`apk/native_input.py` 的 password 分支原来设 `TYPE_CLASS_TEXT | TYPE_TEXT_VARIATION_PASSWORD`，搜狗等输入法一看到 password 标志就切「安全键盘」。改为**一律 `setInputType(TYPE_CLASS_TEXT)`**（输入法看不到密码标志 → 用平时的普通键盘），遮字改由 `et.setTransformationMethod(PasswordTransformationMethod.getInstance())` 负责；拿不到 PTM 时才兜底回 VARIATION_PASSWORD。<br>真机验证（MuMu `127.0.0.1:16416`，包名 **`com.fzjh.fzjhlookup`**，Activity `org.kivy.android.PythonActivity`）：点卡片只开内嵌 WebView（uiautomator 只有 Button「关闭」+ WebView，`dumpsys window` 无 AlertDialog，`mInputShown=false`）；滚回顶部再长按「网页」口令框正常弹出（EditText `password="true"`、显示「••••••」、inputType 取证 `0x1` 不带 `0x80`）。<br>测试：`appbar_touch_test.py` 扩到 **23 项 ALL PASS**（新增按钮内/外/右边界/异常/误按后可再长按），`webkey_test.py` 25 + `openweb_test.py` 10 + `webbialog_test.py` 20 + `inline_test` 全 PASS。热更包 **v86 / 12 文件 / 205.6 KB / md5 `334447206af8b139ea74655904c60e7f` / size 210553**，`preflight` **13 通过 / 2 警告 / 0 失败**，提交 **`0a6110f338e9`**。<br>**注意**：MuMu 上搜狗 IME 窗口高度是 0（`mFrame=[0,1600][900,1600]`），键盘**在模拟器里根本渲染不出来**，所以「键盘外观」只能靠 `dumpsys input_method` 的 `inputType=0x1` 取证，截图看不到。上一条 2026-11-20 00:40（**网页：徽章「影子」改「隐藏」+ 浏览器明文口令自动转 sha256**——用户三条诉求之一「排行榜上影子两个字改成隐藏」与之一「直接打开 ?me 网页还是没有微生梦微生念」。徽章文案：`assets/app.js:153` / `assets/app.js:230` / `assets/exp.js:124` / `assets/exp.js:216` 的 `'影子'` 全改 `'隐藏'`，`assets/app.js:612` 的 `' · 影子榜'` 改 `' · 隐藏榜'`（其余「影子」字样都是注释，未动）。明文口令：`assets/servers.js` 新增 `looksUid()` / `sha256Hex()` / `plainCandidates()` / `resolvePlainKey()`，`FZJH.init()` 拆出 `fetchShadow(cb)`，先比 URL 里现成的哈希（`?me=<hash>` / `?k=<hash>`），没命中才把「不像 uid 的 me / 任何 k」逐个 `crypto.subtle.digest('SHA-256')` 后比对 `SHADOW_HASH`——用户之前是把明文口令直接敲进地址栏（`?me=shuanghaha22`），旧代码只做字符串相等所以永远不命中；仓库仍然只存哈希、明文一个字节都不进代码（`preflight` 的「影子榜 未发现口令明文」会校验，写注释时也**不能把明文样本写进去**，我第一次就踩了这个坑导致 preflight FAIL）。纯数字 me（`?me=4168426`）直接跳过不算哈希。无 WebCrypto（老 WebView / 非安全上下文）静默降级、不崩。`keepParams()` 与 `app.js`/`exp.js` 的 `boot()` 同步：**明文口令不往站内链接里传**，改带 `k=<hash>`；但 `me=<uid>`（APK 的「高亮我自己」；APK 就是 `me=uid` + `k=hash`）必须原样保留。验证：`shadow_web_test.js` 从 41 项扩到 **48 项全 PASS**（新增 `?me=明文` / `?k=明文` 命中、大小写不宽容、错误口令不请求 shadow.json、纯数字 uid 不算哈希、无 WebCrypto 降级、明文不进链接、`me=uid`+`k` 保留 等）；`shadow_data_test.py` 41 项 PASS。真机 Chrome（`adb forward tcp:9333 localabstract:chrome_devtools_remote` + CDP `Runtime.evaluate`）实测线上 `https://fzpaihang.github.io/lanlandeku/?me=shuanghaha22`：`shadowKey` 命中、`shadowMode:true`、标题「11月19日 22:02 更新 · 隐藏榜」、「100 / 100 人」、#15 微生念 / #42 微生梦 均带「隐藏」徽章、名次连续；`exp.html?me=明文` 同样生效。`stamp_assets.py` → `index.html`/`exp.html` 版本戳 `servers.js=ea1c2f78 app.js=30728671 exp.js=30c79641`，`preflight` **13 通过 / 2 警告 / 0 失败**，提交 **`ceab07a4402f`**，`check_drift` 已修改 0。**APK 热更包这次没动**（还是 v85）。上一条 2026-11-19 23:40（**热更 v85：网页口令框改用系统原生对话框**——v84 的口令框是 Kivy `Popup` 里放 `RoundInput(password=True, use_native=False)`，inline 原生 EditText 覆盖层与 Popup 抢焦点，结果**点开不出键盘 / 按钮点不动 / 整屏卡死**，webKey 存不进去、网页不带 `k=`、影子榜永远看不到自己。v85 把口令框整体换成系统 `AlertDialog`：`apk/app_ui.py` 的 `_web_key_dialog()` 重写（不再 import `Popup`，改为 `self.inp.focus=False` → `self._hide_inline()` + `self._web_key_hide_ime()` 清残留覆盖层 → `NATIVE.ask(..., password=True, on_ok=self._web_key_apply, on_dismiss=self._web_key_closed)`，重入保护用新标记 `_web_dlg`——**不能复用 `_pop`**，那是导出菜单 Popup 的）、新增 `_web_key_closed()` 由 OnDismissListener 复位 `_web_dlg`、`_web_key_apply(self, pw)` / `_web_key_clear(self)` **去掉 pop 参数**且不再自己 dismiss（系统关窗）、**留空点确定＝清除口令**（省掉第三个按钮，第三按钮在 v84 的窄弹窗里最容易被裁掉）。`apk/native_input.py` 的 `ask()` 新增 `on_dismiss` 参数 + `_Dismiss(PythonJavaClass)` 实现 `DialogInterface$OnDismissListener`，在 `dialog.show()` 之前 `setOnDismissListener`，`_keep(...)` 一并保活（确定/取消/返回键/点窗外都会回调）。`apk/inline_input.py` 每次 `show()` 重设 inputType 走 `TYPE_TEXT_VARIATION_PASSWORD` 遮字。真机（MuMu 127.0.0.1:16416）全链路验过：长按「网页」弹系统框 → 输口令显示圆点 → 确定后进程存活、红字「口令已保存」、`webKey` 计数 1；取消不写；错误口令提示「口令不对」；留空确定→「已清除口令」、计数 0；取消/保存后都能再次弹出（`_web_dlg` 复位正确）；打开内嵌网页顶部「· 影子榜」「100 / 100 人」，滚到 #15 微生念带红底「影子」徽章、名次连续无跳号。测试：重写 `webbialog_test.py` 20 项（AST 只取 `_web_key_dialog` 函数体做结构断言，避免误判导出菜单的 Popup）+ `webkey_test.py` 25 项 + `appbar_touch_test.py` 17 项 + `openweb_test.py` 10 项全 PASS。`preflight` **13 通过 / 2 警告 / 0 失败**，热更包 **v85 / 12 文件 / 205.0 KB / md5 `1192bcd0119b734447b367f42fb758d8`**，提交 **`850ab4e83d4f`**。上一条 22:20（**影子榜 v84：隐藏玩家用口令在公开网页看到自己**——`data/hidden.json` 新增 `"shadow": true` 标记（微生念 4168426 / 微生梦 6622657，同在苍松迎客），这 2 人被剔除**之前**由 `scripts/fetch.py` 把原始行（含游戏真实名次）抄进新文件 `data/shadow.json`（`write_shadow_server()` / `read_shadow()` / `drop_shadow_server()` / `load_shadow()` / `shadow_uids_for()`），`scripts/merge_exp.py` 抽出 `merge_row()` 让影子行与公开行**同一口径**用档案 exp 覆盖并把影子 exp 写进经验快照（不参与 `fresh` 计数），`scripts/fetch_profiles.py` 的 `hidden_uids` 先减去 `shadow_uids` 使影子玩家档案照抓、掉榜时用 shadow 行补进 targets（不会被 `KEEP_DAYS=30` 误删）。网页侧只在 URL 带口令时 `fetch('./data/shadow.json')`：`?me=<sha256>`（或 APK 用的 `?k=`），`assets/servers.js` 新增 `SHADOW_HASH` / `isShadowParam()` / `mergeShadow()`（纯函数，按原始名次插回并重排 1..N；公开行 `delta=prevRank-原rank`、`prevRank=新rank+delta` 保证不出假箭头；影子行 prevRank/delta 置 null + `_shadow` 标记 + 「影子」徽章），`app.js`/`exp.js` 接线 `meRaw`/`shadowKey` 透传，`keepParams()` 保留 `k`；APK 侧 `apk/lookup_core.py` 新增 `SHADOW_HASH` / `web_key()` / `set_web_key()` / `check_web_key()` / `has_web_key()`（只存 sha256 到 `lookup_cache.json` 的 `webKey`），`apk/app_ui.py` 顶栏「网页」按钮支持**长按**输入口令（`bind_right_long` + 手势号去重，避免长按连带触发短按）、`_open_web()` 自动带 `k=`、新增 `_web_key_dialog()`（`use_native=False` 防明文）。只做微生念/微生梦 2 人，玲珑望月/咸味桃酥/药乐 3 人保持完全隐藏，魔渊字段级隐藏不动，索引与 APK 查询继续全剔。校验：`scripts/preflight.py` 新增 `check_shadow()`（shadow.json 名单不得越界 / 两处 SHADOW_HASH 一致 / 6 个文件不得有口令明文），现 **13 通过 / 2 警告 / 0 失败**。测试：数据侧 41 项、网页 38+21+10 项、APK 侧 25+17+10+13 项全 PASS。包 = 208,599 B / md5 `8d79e75d2546…`，提交 `a735fa73f9b0`；CI run 44539360084 已产出首份 `data/shadow.json`（taptap boardTotal=100 / 2 行，微生念 rank 15、微生梦 rank 42），提交 `c6aa0e5`。上一条 19:05（**热更 v83：请求繁忙不再误报为「该分区未找到」**——`apk/lookup_core.py` 的 `_lookup_single()` 三次重试全被 20616 限流后只 `break` 却**从不写 `_LAST["reason"]`**，界面于是读到上一次的原因（可能是 `unknown`）而落到「该分区未找到」分支；自动识别分支同样把限流区当 `clean_miss=False` 后统一写 `net`。修法：新增 `_reason_of(ec)`（0→notfound / 20616→busy / 其余→net）、`_lookup_uncached()` 开头先把 `reason` 重置为 `unknown`、`_finish()` 命中时写 `ok`、单区分支失败后先落原因再决定要不要探版本号（全程只被限流时直接返回 busy，不白探）、自动识别分支遇到 busy/timeout 原样返回不覆盖成 notfound、轮询里新增 `saw_busy`/`other_err` 早退。`apk/app_ui.py:_done()` 新增 `busy` 分支提示「请求繁忙，请稍后再试」。包 = 203,491 B / md5 `13d821a6a6ff…`，提交 `8ff4a69d3fc2`。上一条 16:12（**数据链路：索引每轮重建 + 掉榜数据保留**——①`refresh.yml` 在 merge_exp 之后新增「重建昵称索引」step（`if: schedule || inputs.mode == 'full'`），新上榜的人当轮就能按昵称搜到，不再等周一；②`scripts/fetch_profiles.py` 新增 `prune_profiles()`（`KEEP_DAYS = 30`），掉榜档案保留 30 天、超期才删，回归后仍可查；③`scripts/merge_exp.py` 快照 exp_map 追加「继承掉榜」段（`prev_map` 里本轮不在榜、且档案仍在的 uid 原值带入，`carried` 计数），回归后 3 天基准不再缺值；④本地重建索引 956→**957**，并补回墨羽惊鸿 5 个掉榜者档案 + 最新快照 exp。提交 `f6afa3e9aee4`。上一条 15:50（**热更 v81：APK 收藏功能**——结果页底栏「收藏/已收藏」、查询页「我的收藏」卡（最多 50 人，点行填入、点「移除」删除），只存 uid/name/server/serverName/at 四字段到 `lookup_cache.json` 的 `favorites`，隐私名单拦截；**修经验快照污染**——`scripts/merge_exp.py:129` 的 `prev_map` 原来取 `snaps[-1]`，而 `scripts/fetch.py` 会先写一条 `src="board"` 的本轮榜单快照，导致未刷新者被回填成榜单旧值（taptap_4 11-18 12:50 那条 100 人里 65 人被污染、30 人经验倒退、11-21 当天 61 人增幅合计虚高 +1889 万），改成倒序取第一条 `src` 为 None 或 `profile` 的快照，并把那 65 个值里可从 11-17 快照回填的 61 个修正（另 4 个是 11-18 新进榜者，保留首个榜单值）；顺带清掉 5 个已下线但磁盘残留的墨羽惊鸿孤儿档案。包 = 202,552 B / md5 `f3b38d8fed4c…`，提交 `279e2360735d`。上一条 12:52（网页文案：`lookup.html` 下载按钮包体 22.6→**23.6 MB**，与 release 资产 24,728,132 字节实际一致；提交 `5bed56da9b02`。上一条 11:05：校准：索引人数 955→**956**，与 `data/lookup-index.json` 实际 count 对齐；数据已对齐远端 `8f72d82`，清掉 4 个下榜残留档案。上一条 11-18 18:40，热更 v80：多昵称索引 `aliases`（改名后旧名照样搜得到）、昵称候选上限 8→20、iOS 三区榜单/档案/快照只跑前 50（索引 1104→956）。上一条 v79：榜单等级 `lv` 改为按实时经验反算（原始榜单值存 `lvBoard`），并去掉手动的「等级」排序——等级由经验唯一决定。另有 v78：人物等级反算改用游戏原式 `exp = 0.1×(lv+4)³`，按整数区间回代——11 区 715 条榜单样本 100% 命中、最大偏差 0 级，preflight 第 6 项因此从「99.0%」收紧到「<99% 即 FAIL」）

---

## 一分钟速览

| 项 | 值 |
|---|---|
| 仓库 | `fzpaihang/lanlandeku`（唯一分支 main） |
| 正式站 | `https://fzpaihang.github.io/lanlandeku/`（Pages，源=main 根目录，30–90 秒缓存） |
| APK 热更版本 | **v87** |
| 分区数 | **11**（苍松/白鹤/丹凤/墨羽/4399/应用汇/其他服/华为/**老马识途**/**野马分鬃**/**仙人指路**） |
| 索引人数 | **957**（iOS 三区自 v80 起各 50；每轮抓取后自动重建） |
| 网页页面 | `index.html` 高手榜 / `exp.html` 经验变化 / `lookup.html` 下载 / **`hall.html` 名人堂（2026-11-20 新增）** |
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
| `0 2 * * *` | 当日 **10:00** | **仙人指路**（iOS 三区） |
| `0 12 * * *` | 当日 **20:00** | **名人堂（11 区一次抓全，board=4 → hall.json）** |

- `timeout-minutes: 60`（十一区全量约 60 分钟）
- `concurrency: fzjh-data`，`cancel-in-progress: false`
- 手动触发：`mode=probe|board|full`，`server=all|<key>|hall11`
- **`target` 与 `servers` 不是一回事**：`plan_refresh.py` 输出 `target`（任务标记，`hall11` 这类不能当分区名）+ `servers`（真正喂给 `--server` 的逗号串）+ `board`（1=高手榜 / 4=名人堂）。workflow 各步一律用 `servers`，别改回 `target`。

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

### 4.0 基准缺人时按 uid 逐行回退（2026-11-20 起）

前端 `assets/exp.js` 的 3 天窗口原来只认**一条全局基准快照**（`cutoff = latest.ts - 3*86400`，
从后往前找第一条 `ts <= cutoff`）。只要那条快照的 `exp` 字典里没有某个 uid，
这个人整行就永远是「—」。

实际事故：`data/servers/taptap/exp-history.json` 的 **2026-11-16 06:30 那条缺 6479440（翱翔天际）**。
那一轮 `git show 31dddaf:data/servers/taptap/profiles/6479440.json` 是 **MISSING**（档案不存在），
且当轮榜单里也没有他（`470e79a` 才回到 rank=25），于是 `merge_exp.py` 的三条规则（本轮 fresh /
沿用 prev_map / 掉榜继承）全落空。3 天窗口正好落在这一条上，他的经验变化就一直显示「—」。

现在 `exp.js` 有 `baseCache` + `baseSnapFor(uid)`：全局基准缺该 uid 时，**按 uid 再往回找一条
「`ts <= cutoff` 且含该 uid」的快照**兜底；仍禁止 `bSnap === latest`（自比会出假 0）。
行级区间天数独立算 `rowDays = (latest.ts - bSnap.ts)/86400`，日均分母 `max(WINDOW_DAYS, rowDays)`。

回归测试：`E:\workbuddy2\_agent_tmp\exp_grow_test.js`（11 项）。
**别改历史快照补数据**——回退逻辑更稳，且补数据会被下一轮抓取覆盖。

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

### 4.3 排名趋势（日均推算多久升降，2026-11-20 起）

经验变化页（`assets/exp.js`）在「日均」后面多一列「排名趋势」，回答「按当前日均，多久后超过上一名 / 被下一名超过」。

**铁律：不能拿游戏 rank ± 1 当邻居。** `data/servers/<key>/gaoshoubang.json` 里的 `rank` 是游戏分批刷新出来的缓存快照，
taptap 98 行里有 **33/97 对 rank 与 exp 逆序**（`expBoard` 同样 33/97），最大位移 37 位。所以必须按 `expN` 降序自建经验序：

```
ord = rows 按 expN 降序（相等按 rank）
up = ord[i-1]   // 经验更高、名次在我前面的那位
dn = ord[i+1]   // 经验更低、跟在我后面的那位
etaUp = (up.expN - me.expN) / (me.perDay - up.perDay)   // 仅当 me.perDay > up.perDay
etaDn = (me.expN - dn.expN) / (dn.perDay - me.perDay)   // 仅当 dn.perDay > me.perDay
```

`perDay === null`（基准缺人 / 刚上榜）或追不上（分母 ≤ 0）时对应箭头不显示；两个都没有就显示 `—`。
`etaText` 格式化：`<1小时` / `N小时` / `N.N天`（<30 天）/ `N天`（<365）/ `>1年`。

排序：`#sortbar` 的「排名趋势」chip 与表头点击都支持，**null 视为 Infinity 沉底**（和数值列相反），默认升序。

回归测试：`E:\workbuddy2\_agent_tmp\exp_grow_test.js`（17 项，其中⑯专测「名次倒挂时仍按经验序取邻居」）。

### 4.4 名人堂（board=4，2026-11-20 起）
游戏「名人堂」= `boardType 4`，榜头指标是**江湖阅历 yueli**（不是武学/经验），每区固定 **9–10 人**。
网页端独立静态页 `hall.html` + `assets/hall.js`，**不引 app.js**（和 exp.html 同构的独立 IIFE）。

**数据侧三条铁律**：
1. `scripts/fetch.py` 的 `BOARD_FILE = {1: "gaoshoubang.json", 4: "hall.json"}`。**board≠1 时这四样一个都不能碰**：`maxRank`/`indexRank` 截断（会把 10 人截得更少）、`index-extra.json`（高手榜专属索引名单，写了会清空高手榜那份）、`exp-history.json` 快照（会把同一批人的经验按阅历名次重写）、`data/shadow.json` 影子榜。
2. `scripts/fetch_profiles.py` 要把同目录 `hall.json` 的行并进抓取目标，且**在 maxRank 截断之后追加**——每区只有 9–10 人，页内详情依赖档案，不能被截掉；用 `rows.setdefault(uid, r)` 让**同一 uid 时高手榜那行优先**（档案里的名次/门派仍按高手榜算，与以前完全一致）。
3. **隐藏剔除与高手榜同一套**：`hidden.json` 全部 5 人（含 2 个 `shadow:true`）都从 hall.json 剔除，剔除后 `rank` 重排 1..N。**名人堂不做影子豁免**——影子榜只属于高手榜。

**前端铁律**：`hall.js` 默认按 `rank` 升序，**绝不自建阅历序重排**。11 区里有 4 个区（huawei / ios2 / taptap_2 / taptap_4）游戏原始名次与阅历不是严格倒序，自己排序会造出假名次。
`fmtYueli()` 必须 `Math.round` 后加千分位（阅历是 7 位整数，原始值是浮点如 2639341.0875）。

**定时任务**：`refresh.yml` 的 `0 12 * * *`（北京 20:00），`plan_refresh.py` 输出 `target=hall11 / board=4 / servers=<11 区逗号串>`。

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

### 6.1 影子榜（v84 起，只对带口令的人生效）

上面 5 人里有 **2 人带 `"shadow": true`**：微生念 `4168426` / 微生梦 `6622657`（同在苍松迎客 `taptap`）。
他们要「自己能查到自己、别人查不到」，其余 3 人（玲珑望月 / 咸味桃酥 / 药乐）保持完全隐藏，**别给他们加 shadow**。

**数据侧三条铁律**（改 `fetch.py` / `fetch_profiles.py` 前必看）：

1. 影子行必须在**隐私剔除之前**抄（`scripts/fetch.py` 里 `shadow_uids`/`shadow_rows`/`board_total_all` 三行紧跟 `hidden = load_hidden()` 之后），
   因为剔除后 `for i, x in enumerate(out_rows, 1): x["rank"] = i` 会把 rank 重排，重排过就不是游戏真实名次了。
2. `scripts/fetch_profiles.py` 的 `hidden_uids` 必须写成 `F.hidden_uids_for(...) - shadow_uids`，否则影子玩家被跳过 + 档案被 `os.remove`。
   影子掉出真榜时用 shadow 行补进 `rows`（`slim()` 的 `menpai/fuyuan/rank` 兜底取自 board_row）并追加进 `targets`，
   这样 `prune_profiles()` 的 `KEEP_DAYS = 30` 不会误删他们的档案。
3. 快照侧 `update_history(board_rows, t, out_dir, drop - shadow_uids)`，`scripts/merge_exp.py` 里 `merge_row()` 公开行与影子行**共用**，
   影子 exp 也进 `exp_map`（否则经验曲线从被隐藏那天起永久断档），但**不参与 `fresh` 计数**。

**前端侧**：口令只以 sha256 存在两处，必须一致（`preflight` 的 `check_shadow()` 会校验）——
`assets/servers.js` 的 `SHADOW_HASH` 与 `apk/lookup_core.py` 的 `SHADOW_HASH`，
当前值 `601260b1695f7625078effee02d36dd9e8aebe4c4d688fd61f8ef77ac53f8db5`（明文只在用户手里，**任何文件里都不许出现**）。
URL 形态：`?me=<sha256>`（网页手填）或 `?k=<sha256>`（APK 用的，因为 `me` 已被 uid 占用）。

**明文口令直接敲进地址栏也行**（2026-11-20 起，m04710）：`assets/servers.js` 的 `FZJH.init()` 先比 URL 里现成的哈希，
没命中再对「不像 uid 的 `me` / 任何 `k`」逐个算 `crypto.subtle.digest('SHA-256')` 后比对 `SHADOW_HASH`（`sha256Hex()` / `resolvePlainKey()`）。
用户当初就是 `?me=<明文>` 打不开——旧代码只做字符串相等，明文永远不命中。要点：
- **仓库里一个字节明文都不许有**，连注释举例都不行（`preflight` 的 `check_shadow()` 会扫 `assets/servers.js`）；
- 纯数字 `me`（`?me=4168426`）当 uid 高亮，跳过哈希；
- 无 WebCrypto（老 WebView / 非安全上下文）静默降级，公开页面不受影响；
- 命中之后站内链接只透传 `k=<hash>`，**明文不再往下传**；但 `me=<uid>` 必须原样保留（APK 形态是 `me=uid` + `k=hash`）。
- 徽章文案是「隐藏」不是「影子」（`app.js:153/230`、`exp.js:124/216`，标题后缀 `app.js:612` 是「 · 隐藏榜」）。
不带口令时`servers.js` 根本不 fetch `data/shadow.json`，公开页面表现一字不差（38 项前端单测里有专门用例）。
`data/shadow.json` 放公开仓库、Pages 直读——名单本身在 `hidden.json` 里已经公开，新增暴露面只是「真实名次与经验」，用户明确接受（m03302）。

**APK 入口**：查询页顶栏「网页」按钮**长按**开口令框（`_web_key_dialog()`），
口令校验通过后只把 sha256 存进 `lookup_cache.json` 的 `webKey`，之后 `_open_web()` 自动带 `k=`。
结果页那颗按钮是「重新查询」，`bind_right_long(None)` 特意摘掉长按。

**v85 起口令框是系统原生 `AlertDialog`**（`NATIVE.ask(..., password=True)`），不再是 Kivy Popup
——v84 那种「Popup 里塞 inline 原生 EditText」会因为覆盖层抢焦点导致**点开不出键盘、按钮全失效、整屏卡死**。
两条行为要记住：
- **留空点「确定」＝清除口令**（没有第三个按钮），保存成功提示「口令已保存，打开网页即可看到隐藏榜」。
- 重入保护是 `self._web_dlg` + `native_input` 的 `on_dismiss` 回调（`_web_key_closed()`）——**不能改用 `_pop`**，那是导出菜单 Popup 的标记。
- `_web_key_apply(self, pw)` / `_web_key_clear(self)` **不带 pop 参数**，也不自己 `dismiss()`，关窗交给系统。
- 回归测试看 `E:\workbuddy2\_agent_tmp\webbialog_test.py`（20 项，用 AST 只抽函数体断言，别判全文件——导出菜单里还有 Popup）。

**v86 两处修正**（提交 `0a6110f338e9`）：
- **口令框只在「网页」按钮命中时才弹**：`app_ui.py` 新增 `_right_on_btn(self, touch)`，用 `right_btn.collide_point(touch.x, touch.y)` 判命中，`_right_down` 首行 `if not self._right_on_btn(touch): return False`。
  原来 Kivy 的 `bind(on_touch_down=...)` 不做碰撞过滤，页面**任意位置**按下都会起 0.6 秒长按计时器，
  滚到底点「全服高手榜」卡（手指停留稍久）就会误弹口令框——入口卡本身只调 `_open_web()`，没有任何口令逻辑。
  **别再用 `to_window()` 换算**：派发到 AppBar 的 touch 坐标已经和 `right_btn.pos` 同一套内容坐标系（插桩实测 `touch.y=2194` vs `btn.y=2120 h=145`）。
- **口令框用普通键盘**：`native_input.py` 一律 `et.setInputType(InputType.TYPE_CLASS_TEXT)`，
  遮字改 `et.setTransformationMethod(PasswordTransformationMethod.getInstance())`。
  带 `VARIATION_PASSWORD` 会让搜狗等输入法切「安全键盘」，用户要的是平时的键盘。
- 回归测试：`appbar_touch_test.py` **23 项**（按钮内/外/右边界/异常/误按后可再长按），`webkey_test.py` 25 + `openweb_test.py` 10 + `webbialog_test.py` 20 全 PASS。
- 模拟器限制：MuMu 上搜狗 IME 窗口高度 0（`mFrame=[0,1600][900,1600]`），键盘渲染不出来，只能靠 `dumpsys input_method` 里 `inputType=0x1`（不带 `0x80`）取证。

**v87 文案统一**（提交 `99617b989922`）：APK 里所有面向用户的「影子榜」改成「隐藏榜」，与网页端一致。
对话框标题 `apk/app_ui.py:2107` → 「网页口令：打开网页会自动进隐藏榜」；保存成功提示 `:2176` → 「口令已保存，打开网页即可看到隐藏榜」。
**改了文案必须同步改 `E:\workbuddy2\_agent_tmp\webbialog_test.py:74-75` 里写死的断言**，否则 20 项单测直接 FAIL。

---

## 改动后的必做步骤

| 改了什么 | 必须做什么 |
|---|---|
| 任何改动 | `python scripts/preflight.py`（**13 项**：语法/JS 语法/缓存戳/热更包/等级/等级(人物)/names/隐私/隐私三副本/字段级隐藏/**影子榜 3 项**/经验快照窗口） |
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
| 网页 | **2026-11-20 23:10 名人堂上线：新静态页 hall.html + 抓取层支持 board=4**（m06650 起，用户要求「名人堂」接入网页端）。<br>**新页面**：`hall.html`（3985 B）+ `assets/hall.js`（13901 B，独立 IIFE，**不引 app.js**）；5 列「名次 / 昵称 / 门派 / 等级 / 江湖阅历」，`#sortbar` 三 chip，点行弹 `profile.js` 档案（`PF_CACHE`+`PF_SEQ` 丢弃迟到回调、`replaceState` 同步 `?uid=`）。**默认按 rank 升序、绝不按 yueli 自排**（4 个区原始名次与阅历不是严格倒序）。全程零 innerHTML。index/exp/hall 三页互加入口。<br>**抓取层**：`fetch.py` 加 `BOARD_FILE`，board≠1 时**不碰** maxRank 截断 / index-extra.json / exp-history.json / data/shadow.json；`fetch_profiles.py` 把 hall.json 行并在截断之后追加（setdefault ⇒ 高手榜行优先）；`plan_refresh.py` 加 `HALL_TARGET="hall11"` + `plan_full()`；`refresh.yml` 加 `0 12 * * *`（北京 20:00）+ 手动 `hall11`，各步 `T` 改 `servers`（不是 `target`），抓榜步加 `--board 4 --max-pages 1`。<br>**隐藏口径**：与高手榜同一套，5 人全剔（含 2 个 shadow），剔后 rank 重排 1..N，**名人堂不做影子豁免**。<br>**数据**：11 区 `hall.json` 共 108 行（4399 9 / taptap_3 9 / 其余 10），rank 全连续、无隐藏残留。<br>**测试**：`hall_web_test.js` 35 项 PASS/0 FAIL、`hall_all_servers_smoke.js` 11 区 33/0、`hall_web_smoke.js` 7/0、`hall_profile_smoke.js` 3/0；`preflight` 13 通过 / 2 警告 / 0 失败；Edge headless 桌面 1200×1100 + 移动 420×1400 真实渲染已验。<br>**发布**：`publish.py` 提交 `e1488429a0a8`（22 文件）。**APK 热更包未动（仍 v87）**。 |
| 网页 | **2026-11-20 08:45 经验变化页新增「排名趋势」列**（m06259，用户问「根据日均数据判断多久之后排名提升/下降」）。<br>**口径**：`assets/exp.js` 新增 `etaText(d)` / `computeEta(rows)` / `etaSpans(r)`。**不能拿游戏 rank±1 当邻居**——taptap 98 行里 rank 与经验值 33/97 对逆序（游戏名次是分批刷新缓存），必须按 `expN` 降序自建经验序。<br>**公式**：`etaUp = max(0, up.expN - me.expN) / (me.perDay - up.perDay)`（仅分母 >0）、`etaDn = max(0, me.expN - dn.expN) / (dn.perDay - me.perDay)`（仅分母 >0）。`etaText`：<1小时 / N小时 / N.N天（<30）/ N天（<365）/ >1年。<br>**UI**：桌面插第 8 列 `c-eta`「排名趋势」（`span.eta-i.up`↑红 / `.dn`↓绿，无值 '—'）；移动端卡片第 3 行同款；`#sortbar` 加「排名趋势」chip（null 沉底、默认 asc），表头点击同步。<br>**实测**：98 行 × 8 列，eta 非 '—' 75 行。<br>**测试**：`exp_grow_test.js` 扩到 17 项 ALL PASS（新增⑫–⑰），`shadow_exp_smoke.js` 10 项、`shadow_web_test.js` 48 项、`test_expN_sort.js` 全 PASS。<br>**发布**：`publish.py` 提交 `de99ce987eff`（`exp.js` / `style.css` / `exp.html` / `index.html` / `lookup.html`），线上 `exp.js?v=9072d485`。 |
| 网页 | **2026-11-20 01:55 经验变化页基准缺人回退**（m05997，用户问「经验增长页面的苍松区翱翔天际怎么没有经验变化」）。<br>**根因**：`data/servers/taptap/exp-history.json` 的 **2026-11-16 06:30 快照缺 6479440（翱翔天际）**——`git show 31dddaf:data/servers/taptap/profiles/6479440.json` = MISSING（档案不存在）且当轮不在榜，`merge_exp.py` 的 fresh/沿用 prev_map/掉榜继承三条规则全落空；而 `assets/exp.js` 原先只取**一条全局基准快照**（`cutoff = latest.ts - 3*86400`），最新快照 11-19 22:02 反查正好落到这一条 → `baseExp = undefined` → 该行显示「—」。真人只影响他 1 个（另 2 个是影子玩家，属预期）。<br>**修法（只改前端）**：`assets/exp.js` 新增 `baseCache` + `baseSnapFor(uid)`——全局基准缺该 uid 时按 uid 再往回找一条「`ts <= cutoff` 且含该 uid」的快照兜底，禁止 `bSnap === latest`（自比出假 0）；行级 `rowDays = (latest.ts - bSnap.ts)/86400`，日均分母 `max(WINDOW_DAYS, rowDays)`。**别改历史快照补数据**（会被下一轮抓取覆盖）。<br>**验证**：新建 `E:\workbuddy2\_agent_tmp\exp_grow_test.js` 11 项 ALL PASS；`shadow_exp_smoke.js` 修好两处旧「影子」断言后 10 项 PASS；`shadow_web_test.js` 48 项、`test_expN_sort.js`、`test_snap.js` 全 PASS。真实数据实测翱翔天际 `+794.9万` / `+181.9万/天` / `+0.14%`（基准退回 11-15 13:10，区间 4.0 天），**全榜 98 行不再有「—」**。<br>**发布**：`exp.html` 戳 `exp.js=e99b3931`；`preflight` 13 通过 / 2 警告 / 0 失败；`publish.py` 提交 **`61d2d72f36f2`**。Pages 有缓存，立即核查会看到旧 13419 B（raw 源已 14426 B 含 `baseSnapFor`），等 30–90 秒。<br> |
| 网页 | **2026-11-20 徽章「影子」→「隐藏」+ 浏览器明文口令自动转 sha256**（m04710）：<br>①文案：`assets/app.js:153`/`:230`、`assets/exp.js:124`/`:216` 四处 `'影子'` 改 `'隐藏'`，`assets/app.js:612` 的 `' · 影子榜'` 改 `' · 隐藏榜'`。<br>②`assets/servers.js` 新增 `looksUid()`/`sha256Hex()`/`plainCandidates()`/`resolvePlainKey()`，`FZJH.init()` 拆出 `fetchShadow(cb)`：URL 里没有现成哈希时，把「不像 uid 的 `me` / 任何 `k`」逐个 `crypto.subtle.digest('SHA-256')` 后比对 `SHADOW_HASH`。用户一直是 `?me=<明文>` 打不开——旧代码只做字符串相等。仓库仍只存哈希（`preflight` 的「影子榜 未发现口令明文」会扫 `assets/servers.js`，**注释里也不能写明文样本**）。<br>③`keepParams()` 与 `app.js`/`exp.js` 的 `boot()`：明文不往站内链接传，改带 `k=<hash>`；`me=<uid>`（APK 形态 `me=uid`+`k=hash`）原样保留。<br>验证：`shadow_web_test.js` **48 项全 PASS**（原 41 项 + 7 新增）、`shadow_data_test.py` 41 项 PASS；真机 Chrome 经 CDP 实测线上 `?me=<明文>`：`shadowMode:true`、「11月19日 22:02 更新 · 隐藏榜」、「100 / 100 人」、#15 微生念 / #42 微生梦 带「隐藏」徽章；`exp.html?me=<明文>` 同样生效。`stamp_assets.py`（`servers.js=ea1c2f78 app.js=30728671 exp.js=30c79641`）→ `preflight` 13 通过 / 2 警告 / 0 失败 → 提交 **`ceab07a4402f`**。**APK 热更包未动（仍 v85）**。 |
| v87 | **文案：APK 口令框「影子榜」→「隐藏榜」**（用户要求与网页端统一）。纯文案 + 注释，逻辑零改动：`apk/app_ui.py:2107` 对话框标题改「网页口令：打开网页会自动进隐藏榜」、`:2176` 保存提示改「口令已保存，打开网页即可看到隐藏榜」，另 4 处注释（`app_ui.py:2051`/`:2071`/`:2077`/`:2300`）+ `lookup_core.py:56`/`:421` 同步，改后 `grep 影子 apk/` = 0。`webbialog_test.py:74-75` 写死的文案断言已同步，**20 项 ALL PASS**；`webkey_test.py` 25 项、`appbar_touch_test.py` 23 项全 PASS。`pack_update.py` → v87 / 12 文件 / 205.6 KB / md5 `bbd1e27deb3db6a4ef7bf86144e5bd6d` / size 210550 / 签名 `e9c9930148149ac2…`；`preflight` 13 通过 / 2 警告 / 0 失败；`publish.py` 提交 **`99617b989922`**。<br> |
| v86 | **修「点底部全服高手榜入口卡误弹口令框」+ 口令框改回普通键盘**（m05226）。<br>**①误弹框根因**：`apk/app_ui.py` 的 `_right_down()` 只判 `_right_hit()`（回调非空 + 按钮 `opacity>0 and width>0`），**从不判断触摸点是否落在「网页」按钮上**。Kivy 的 `bind(on_touch_down=...)` 是事件栈回调，事件 `Root→ScrollView→inner→appbar` 逐级派发，只要父级 collide 就会调用它 → **页面任意位置按下都会起 0.6 秒长按计时器**，滚到底点「全服高手榜」卡（手指停留稍久）就触发 `_right_timeout` → `_web_key_dialog()`。入口卡 `_entry_release()` 本身只调 `_open_web()`，**没有任何口令逻辑**。<br>**②改法**：`app_ui.py` 新增 `_right_on_btn(self, touch)`，`return bool(self.right_btn.collide_point(touch.x, touch.y))`（异常时 return False），`_right_down` 首行 `if not self._right_on_btn(touch): return False`。<br>**踩坑**：第一版用 `btn.to_window(btn.x, btn.y)` 求窗口矩形 —— 真机长按「网页」也不弹了（误杀）。插桩 logcat 得到 `wsize=(900,1540) touch=(794.1,2194.0) btn.x=720.0 btn.y=2120.0 w=140 h=145`：**派发到 AppBar 的 touch 坐标已经和 `right_btn.pos` 同一套内容坐标系**，`to_window` 反而把按钮挪到窗口系（y≈560）导致真实长按判不中。改用 `collide_point` 后短按/长按互不干扰。<br>**③安全键盘**：`apk/native_input.py` 的 password 分支原来设 `TYPE_CLASS_TEXT | TYPE_TEXT_VARIATION_PASSWORD`，搜狗等输入法见到 password 标志就切「安全键盘」。改为**一律 `et.setInputType(InputType.TYPE_CLASS_TEXT)`**，遮字改 `et.setTransformationMethod(PasswordTransformationMethod.getInstance())`；只有拿不到 PTM 时才兜底回 `VARIATION_PASSWORD`。<br>**④真机验证**（MuMu `127.0.0.1:16416`，**包名 `com.fzjh.fzjhlookup`**，Activity `org.kivy.android.PythonActivity`，`wm size` 900x1600）：点卡片（450,1385）→ 只开内嵌 WebView（uiautomator 只有 Button「关闭」+ WebView），`dumpsys window windows` 无 AlertDialog、`dumpsys input_method` `mInputShown=false`；关 WebView（835,122）滚回顶部再长按「网页」（`input swipe 795 130 795 130 900`）→ 口令框正常弹出（uiautomator：`EditText password="true" text="••••••"` bounds `[52,751][852,871]`，按钮「确定」「取消」）；`dumpsys input_method` editorInfo 里 `inputType=0x1`（不带 `0x80`）→ 输入法不会切安全键盘，遮字由 transformation method 保住。<br>**⑤限制**：MuMu 上搜狗 IME 窗口 `Requested w=900 h=0`、`mFrame=[0,1600][900,1600]` → **键盘在模拟器里渲染不出来**，截图 q1–q4 看不到键盘，键盘外观只能靠 `dumpsys input_method` 的 inputType 取证。<br>**⑥测试与发布**：`appbar_touch_test.py` 扩到 **23 项 ALL PASS**（FakeButton 实现 Kivy 语义 `collide_point`，新增 不在按钮上不长按 / 按钮内命中 / 右边界不命中 / collide_point 抛异常不崩 / 误按后仍能长按；**坑**：不能替换 `bar.right_btn` 对象否则事件绑定全丢，只能改 pos）；`webkey_test.py` 25 + `openweb_test.py` 10 + `webbialog_test.py` 20 全 PASS。热更包 **v86 / 12 文件 / 205.6 KB / size 210553 / md5 `334447206af8b139ea74655904c60e7f` / 签名 `769bf35ffc45fd77…`**，`code.zip` 14 项逐文件 md5 与工作区一致，`preflight` **13 通过 / 2 警告 / 0 失败**（WARN 照旧），提交 **`0a6110f338e9`**。 |
| v85 | **修「网页口令框打不开 / 按钮点不动 / 整屏卡死」**（承接 v84 的影子榜口令入口，m04065）。<br>**根因**：v84 的 `_web_key_dialog()` 是 Kivy `Popup` 里放 `RoundInput(password=True, use_native=False)`，而 `use_native=False` 走的是 `inline_input` 的**原生 EditText 覆盖层**——覆盖层会抢焦点并盖在 Popup 之上，导致键盘不出、Popup 内所有按钮 `on_release` 全失活、严重时整屏无响应。webKey 因此永远存不进去，网页不带 `k=`，影子榜对本人永远不显示。<br>**改法（3 个文件）**：<br>①`apk/app_ui.py:_web_key_dialog()`（现 :2054-2113）**整体重写**——不再 `from kivy.uix.popup import Popup`、不再建 Card/RoundInput/三按钮；改为 `self.inp.focus=False` → `self._hide_inline()` + `self._web_key_hide_ime()`（清残留覆盖层，否则会盖在系统对话框上）→ `NATIVE is None` 时提示「当前环境不支持口令输入」→ 置 `self._web_dlg = True` → `NATIVE.ask("网页口令：打开网页会自动进影子榜", initial="", hint="口令（留空确定＝清除）", ok_text="确定", on_ok=self._web_key_apply, on_dismiss=self._web_key_closed, password=True)`；`ask()` 返回 False 则 `self._web_dlg = False` + 提示「口令框打不开，请重试」。重入标记用新的 `_web_dlg`——**不能复用 `_pop`**（那是导出菜单 Popup 的）。<br>②新增 `_web_key_closed(self)`：只做 `self._web_dlg = False`，由 OnDismissListener 触发（确定/取消/返回键/点窗外都会来，所以之后再长按一定能再弹）。<br>③`_web_key_apply(self, pw)` **签名去掉 pop 参数**：`pw=(pw or "").strip()`；空 → 调 `_web_key_clear()`（**留空点确定＝清除**，省掉第三个按钮——那个按钮在窄弹窗里最容易被裁掉）；否则 `L.check_web_key(pw)` 失败提示「口令不对」、成功 `L.set_web_key(L.SHADOW_HASH)` 后提示「口令已保存，打开网页即可看到影子榜」。**不再自己 `dismiss()`**，关窗交给系统。`_web_key_clear(self)` 同步去掉 pop 参数。<br>④`apk/native_input.py` 的 `ask(title, initial="", hint="", ok_text="确定", on_ok=None, on_cancel=None, password=False, on_dismiss=None)` 新增 `on_dismiss`；`build()` 内新增 `class _Dismiss(PythonJavaClass)` 实现 `android/content/DialogInterface$OnDismissListener`（`@java_method("(Landroid/content/DialogInterface;)V") def onDismiss(self, _dlg): _dispatch(on_dismiss)`），`dialog.setOnDismissListener(dismiss_l)` 放在 `dialog.show()` **之前**，`_keep(dialog, ok_l, cancel_l, dismiss_l, focus_l)` 一并保活。password 分支 `et.setInputType(TYPE_CLASS_TEXT | TYPE_TEXT_VARIATION_PASSWORD)`。<br>⑤`apk/inline_input.py` 的 `show()` 每次重设 inputType（`RoundInput._inline_style()` 返回 `"password": bool(self.password)`），保证其它地方的 inline 输入仍能遮字。<br>**真机验证（MuMu `127.0.0.1:16416`，adb 已 root）**：长按「网页」(795,130) 0.9s → 系统 AlertDialog 弹出（黑标题 + 灰底输入框占位「口令（留空确定＝清除）」+「确定」/「取消」）；`input text` 后显示 13 个圆点，遮字正常；点「确定」→ 对话框关闭、**进程存活 pid 4864**、页面红字「口令已保存，打开网页即可看到影子榜」、`grep -c webKey` = 1；点「取消」→ webKey 仍 0；错误口令 → 提示「口令不对」且不写缓存；留空确定 → 「已清除口令」、`grep -c webKey` = 0；取消后/保存后再长按**都能再弹**；最后点「网页」→ 内嵌 WebView 顶部「11月19日 22:02 更新 · 影子榜」「100 / 100 人」，滚到 14–17 行见 **#15 微生念带红底「影子」徽章**、问情宫 / 等级 3731 / 经验 52.14亿 / 福缘 269，名次连续无跳号。<br>**测试**：重写 `E:\workbuddy2\_agent_tmp\webbialog_test.py`（20 项：正确口令写 hash / 提示文案 / 错误口令不改缓存 / 带空白通过 / 留空确定=清除 / 全空白=清除 / `None` 不崩 / `_web_key_clear` / 写缓存失败不崩且旧值不动 / 结果页走 `_flash` / 结构断言）——**踩坑**：结构断言若判全局源码会误报 FAIL（导出菜单里还有 `Popup(`），必须用 `ast.get_source_segment` 只取 `_web_key_dialog` 函数体。`webkey_test.py` 25 项、`appbar_touch_test.py` 17 项、`openweb_test.py` 10 项全 PASS。<br>**打包发布**：`preflight` **13 通过 / 2 警告 / 0 失败**（WARN 照旧 = 云函数 staging 旧 int() 副本、经验快照窗口 4399/guanfang/taptap_4 各 4.0 天 + taptap 3.6 天）；热更包 **v85 / 12 文件 / 205.0 KB / size 209960 / md5 `1192bcd0119b734447b367f42fb758d8` / 签名 `c4439dc62c2a3cd5…` / builtAt 2026-11-19 23:35:15**；`code.zip` 14 项逐文件 md5 与工作区一致；提交 **`850ab4e83d4f`**。<br>**注意**：设备上的 v85 是手推的（14 个文件 push+cp+chown u0_a51+chmod 600、`version.txt` 写 85、删 `__pycache__`），正式生效需要重启 App 走热更下载。 |
| v84 | **影子榜：隐藏玩家用口令在公开网页看到自己**（m03219/m03302/m03338/m03368 定稿，只做微生念 `4168426` / 微生梦 `6622657`，同在苍松迎客）。<br>**数据侧**：`data/hidden.json` 这 2 人加 `"shadow": true`（其余 3 人不动）；`scripts/fetch.py` 新增 `load_shadow()` / `shadow_uids_for()` / `SHADOW_PATH` / `read_shadow()` / `drop_shadow_server()` / `write_shadow_server()`，在隐私剔除**之前**抄 `shadow_rows`（此时 rank 才是游戏真实名次），写 `data/shadow.json`（`{servers:{key:{boardTotal,rows}},updatedAt,updatedTs}`，其它分区原样保留）；`update_history(board_rows, t, out_dir, drop - shadow_uids)` 保住影子玩家历史经验。<br>**档案侧**：`scripts/fetch_profiles.py` 的 `hidden_uids` 改成 `hidden_uids_for(...) - shadow_uids`（否则影子玩家被跳过 + `os.remove` 删档），掉榜时用 shadow 行补进 `rows`/`targets`，故 `KEEP_DAYS=30` 不会误删。<br>**经验侧**：`scripts/merge_exp.py` 抽出 `merge_row(r, prof_dir, board_ts)`，公开榜与影子榜共用（口径必须一致，否则本人看到的自己经验比旁边人旧一轮）；写 board 后合并影子段并写回 `mergedAt`；影子 exp 追加进 `exp_map`（不进 `fresh` 计数）。<br>**网页侧**：`assets/servers.js` 新增 `SHADOW_URL` / `SHADOW_HASH` / `FZJH.isShadowParam()` / `copyRow()` / `shadowRanks()` / `origRank()` / `FZJH.mergeShadow()`（纯函数：按原始名次插回、重排 1..N、同 rank 影子排后；公开行 `delta = prevRank - 原rank`、`prevRank = 新rank + delta`——**不能**用合并后名次减旧名次，那会把插入造成的整体后移算成跌、出 -2 这类假箭头；影子行 `prevRank/delta = null` + `_shadow`）/ `shadowServer()` 自动切到有影子行的分区，`keepParams()` 保留 `k`；`app.js`/`exp.js` 加 `meRaw`/`shadowKey` 透传 + `mergeShadow` 接线 + 「影子」徽章（NEW 徽章排除影子行），`el.updated` 尾部只在实际插入时才加「· 影子榜」。<br>**APK 侧**：`apk/lookup_core.py` 加 `SHADOW_HASH` / `web_key()` / `set_web_key()` / `check_web_key()` / `has_web_key()`（只把 sha256 存 `lookup_cache.json` 的 `webKey`）；`app_ui.py` 顶栏「网页」支持长按（`bind_right_long` + `_right_short` 用「手势号」`_right_consumed_gid` 去重，**修掉长按后还触发短按**；`show_query()` 的 `right=""` 改 `"网页"`——原来宽度被压成 0、查询页根本没这颗按钮）、`_open_web()` 自动补 `k=`、新增 `_web_key_dialog()`（`RoundInput(password=True, use_native=False)`——原生覆盖层把 inputType 写死普通文本会明文显示）。<br>**校验**：`scripts/preflight.py` 新增 `check_shadow()` 三项（名单不得越界 / 两处 SHADOW_HASH 一致 / 6 文件无口令明文），现 **13 通过 / 2 警告 / 0 失败**。测试：数据侧 `shadow_data_test.py` 41 项、网页 `shadow_web_test.js` 38 + `shadow_app_smoke.js` 21 + `shadow_exp_smoke.js` 10 项、APK `webkey_test.py` 25 + `appbar_touch_test.py` 17 + `openweb_test.py` 10 + `webbialog_test.py` 13 项全 PASS；端到端跑真实 `merge_exp.py` 15 项 PASS。<br>**上线**：包 208,599 B / md5 `8d79e75d2546…`，提交 `a735fa73f9b0`；CI run `44539360084` 产出首份 `data/shadow.json`（提交 `c6aa0e5`）：taptap `boardTotal=100`、2 行，微生念 `rank=15 exp=5214148838` / 微生梦 `rank=42 exp=4138060232`，公开榜仍 98 行、索引仍 957 且不含这 2 人、两份档案 9677 B / 8026 B、最新快照 `n=100 fresh=98` 已含两人经验 |
| v83 | **修「请求繁忙被误报为该分区未找到」**：`apk/lookup_core.py` 新增 `_reason_of(ec)`（`0`→`notfound`／`20616`→`busy`／其余→`net`）、`last_reason()` 文档补 `busy` 与 `unknown`。根因两处：①`_lookup_single()` 三次重试全被 20616 限流后只 `break`，**从不写 `_LAST["reason"]`**，界面读到上一次的 `unknown` 就落到 else 分支说「该分区未找到」；②`_lookup_uncached()` 自动识别分支把限流区也记成 `clean_miss=False`，末尾统一写 `net`。改法：`_lookup_uncached()` 开头把 `reason` 重置为 `unknown`（每轮从干净状态开始）、`_finish()` 命中写 `ok`、单区分支失败后**先落原因**再决定要不要探版本号（`all_busy` 时直接返回 `busy`，不白探版本号免得继续撞限流；混着别的错误码反而要探，那可能是版本号过期）、自动识别前缀命中区遇 `busy`/`timeout` 原样返回不再落回轮询覆盖、轮询第一轮超时 `break`→`return`、新增 `saw_busy`/`other_err` 两个标志（全 busy 无其他错误才早退）。`apk/app_ui.py:_done()` 在 timeout 与 net 之间加 `elif reason == "busy"` → 提示「请求繁忙，请稍后再试 ／ 游戏接口限流（同一时间查的人太多），过一会儿再查就行」（没写具体秒数：失败那次也计入 `QUERY_COOLDOWN` 30 秒，写 10 秒会与紧接着的「操作太快了」矛盾）。回归测试 `E:\workbuddy2\_agent_tmp\busy_test.py` 14 项全 PASS（单区全限流=busy 且请求数 3 / 前两次失败第三次成功=ok / 查无此人=notfound / 自动识别前缀区限流=busy / 轮询全限流=busy / 轮询全查无=notfound / 握手异常=net / 命中=ok / 全限流探测次数 0 / 混合错误探测次数 1 / 自动识别混合错误不落 notfound / 映射 5 例）。`code.zip` 12 py + 2 资源共 14 项与工作区逐文件 md5 一致。`preflight` 10 通过 / 2 警告 / 0 失败。包 = 203,491 B / md5 `13d821a6a6ffdf3707386b949a583b27`，提交 `8ff4a69d3fc2` |
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
