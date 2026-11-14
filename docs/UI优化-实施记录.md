# 玩家查询 App · UI 优化实施记录（v19）

> 对应方案：`玩家查询App-UI优化方案-v1.md`（v1 文档）
> 落地版本：热更 v18（P0）、v19（P1+P2）
> 验证环境：MuMu 模拟器（900×1600，density 240），查询角色「刘小年 / 21079729670」206 门武学

## 一、已完成

| 阶段 | 内容 | 版本 | 状态 |
|---|---|---|---|
| P0 | 修「武学 N 门」竖排溢出、「展开全部」被裁、副标题折行；`lab()` 加 `shorten` | v18 | 已上线 |
| P0 | Kivy 开启 `keyboard_mode=system`（原来日志报 virtual keyboard not allowed） | v18 | 已上线 |
| P1 | 查询页：删印章、顺序改「分区→输入→查询」、三段说明并一行、版本号进「?」、列表加「填入」 | v19 | 已上线 |
| P1 | 结果页：顶栏只留摘要+修改、榜单入口移入内容区、指标分级 20sp/16sp、准备位改键值对行（6 条 + 展开全部，带等级）、装备保留胶囊修对齐、底栏只留「再查一个」主按钮 | v19 | 已上线 |
| P2 | 武学 206 门按类型分 7 组折叠、组内等级降序、展开 8 条 +「显示更多」、搜索跨组平铺 | v19 | 已上线 |
| P2 | `apk/skill_groups.py` 分类表（774 门自动初判）+ `docs/武学分类校对表.md` | v19 | 待你校对 |

## 二、P0 的真实病根（和方案推测不同）

方案里判断是「flex 子项被压到 0 宽度」——方向对，但具体原因是**宽度重复套了 dp**：

```python
self.skill_toggle = txt_button("", width=dp(150), ...)   # 旧代码
```

`txt_button` 内部会执行 `width = dp(width)`，外面再套一层 `dp()` → 实际 337px，
比整行可用宽度（约 292dp）还宽，标题的 `text_size` 被压到 0，于是每个汉字各占一行、
`height=dp(32)` 装不下、多出来的字直接画到控件外盖住列表。改成纯数字 `width=104` 即解决。

同一类坑在 `_render_skill_list` 里：`height = dp(35) * len(items)` 是估算值，
搜索过滤后条数与真实高度错位，已改回 `minimum_height` 绑定。

## 三、数据层改动

`lookup_core.parse_profile` 里 `prepared` 由 `{槽位: 技能名}` 改成
`{槽位: {"n": 名称, "lv": 等级}}`，等级在解析时从 `skills` 一次带出，
界面不用再反查。旧字段兼容：`_render` 里用 `isinstance(v, dict)` 判断。

## 四、武学分类：改用网页数据（v20）

最初按名称关键词猜（内功/轻功/拳脚/兵器/招架/学识/其他 7 组），用户指出应按
https://whfie.github.io/fzjhskill/ 的分类来，且**一门武学可以同时准备在多个位置**
（太玄经 = 拳脚 + 内功 + 招架）。已改为直接用该站的原始表：

- 数据：`public/data/skill.json.gz`（仓库 `whfie/fzjhskill`），774 门武学，id 与我们
  `apk/names.json` **完全一致**；
- 字段：`wxclassify`（neigong/jian/zhang/quan/zhi…，可逗号分隔）+
  描述里的「可准备为:拳脚、内功、招架」；
- 生成：`scripts/build_skill_class.py` → `apk/skill_class.py`（774 条 id→位置，26.7 KB）；
- 分组：15 个位置组（内功/轻功/拳脚/招架/剑法/刀法/棍法/枪法/鞭法/斧法/暗器/双持/
  乐器/学识/其他），**多对多**：同一门出现在它所有可准备的位置里，各组门数之和
  大于角色武学总数是正常的；
- 覆盖：774 门里 421 门是多位置，只有 19 门查不到位置（进「其他」）；
- 实测（刘小年 206 门）：内功 31 / 轻功 33 / 拳脚 45 / **招架 113** / 剑法 20 / 刀法 18 /
  棍法 14 / 枪法 7 / 鞭法 6 / 斧法 5 / 暗器 6 / 双持 3 / 乐器 8 / 学识 24 / 其他 2，
  合计 335 —— 多位置重复计入的结果；太玄经同时出现在内功与招架里。

## 五、待办 / 已知小问题

1. **输入框失焦时文字偏灰**（像占位符），聚焦后变深。试过 `foreground_color` / `disabled_foreground_color` 均不生效，`_trigger_refresh_text()` 也无效，怀疑是 Kivy 2.3 在失焦态使用另一套颜色，暂未定位。
2. 武学组的「搜索命中词标朱砂」没做（Kivy markup 与长文本折行冲突，收益低）。
3. 榜单页仍是独立网页（App 内 WebView），没有做「分段控件」式内嵌切换。

---

## 六、v21：结构层改造（顶栏 / 卡片 / 固定底栏）

> 状态：**已在 MuMu 模拟器验证，未发布热更**（代码在工作区，`version.json` 未动）

v19/v20 解决的是「东西放不放得下」，v21 解决的是「页面有没有骨架」。
三张图对比下来，高手榜之所以好看，是因为它有顶栏 / 筛选区 / 卡片列表三层结构；
另外两页没有这层结构，所以怎么调字号间距都像「一堆控件平铺」。

### 6.1 统一顶栏（`AppBar`）

| 改动 | 说明 |
|---|---|
| 新增 `AppBar` 组件 | 深绛红底、50dp 高，左侧返回 + 标题 + 副标题，右侧动作文字 |
| 查询页 | 原来没有顶栏，22sp 大标题直接贴在状态栏下；现在进顶栏（标题 15.5 / 副标题 10.5） |
| 结果页 | 原来是一条浅色摘要条 + 分割线；现在顶栏给「‹ 分区 / UID / 修改」 |
| 返回键 | 顶栏「‹」和安卓返回键都回查询页 |

### 6.2 查询页：表单卡片化

- 表单（分区 / 昵称 UID / 查询按钮 / 说明）收进一张白卡；label 从「和内框并排」改成**上置 12sp 灰字**，组间距 12、组内 5。
- 输入框加 1px 描边 + 聚焦变主色，高度 52 → 46，字号 17 → 16。
- 「最近查询」独立成卡：行高 48、线用 `C_LINE`、右侧「填入」改成**浅粉胶囊按钮**（原来是无背景红字，点击区只有文字大小）。
- 历史不足 3 条时用示例补齐，并给示例行标「示例」胶囊——否则查过一两次之后下半屏又是一片空。
- 查询页底部本来约 40% 纯空白，现在补了「全服高手榜」入口卡（浅粉底），把榜单入口从顶栏角落挪到明确位置。

### 6.3 结果页：一张大卡 → 六张卡

原来所有内容塞在一张白卡里靠 `HLine` 分隔，一屏能数出十条线，反而成了没有分块的表格。现在：

| 卡 | 内容 |
|---|---|
| ① 身份 | 名字 22sp 宋体 + 「第 N 名 ›」胶囊（点击进榜单）+ 门派/性别/年龄/容貌 |
| ② 数据 | 主指标 19sp 粗体（等级 / 武学造诣）+ 浅线分档 + 次指标 15.5sp 两列 |
| ③ 准备位 | 6 行 + 展开全部（行高 44 → 40，槽位列宽 56 → 44） |
| ④ 装备 | 双列胶囊（38 高，槽位宽 42 → 36） |
| ⑤ 传承 | 行高 36，末项深红加粗；**去掉末项下面那条贯通整屏的深红横线** |
| ⑥ 武学 | 标题 + 搜索框 + 15 个分组折叠 |

其他：
- **搜索框原来完全看不见**——`background_color=(0,0,0,0)` 且没有自绘背景，放在白卡上只剩一行漂浮的字。改用 `RoundInput(bg=C_SOFT)`，浅灰底 + 描边 + 聚焦态。
- 武学组标题之间不再画线（15 组 = 15 条，整块像 Excel），行高 42 → 46 靠留白分组；组内子项之间保留细线。
- **底部操作条改成固定底栏**（「再查一个」主按钮 + 复制 UID + 保存），不用滚到页面最底才看得见。
- `Chip` 名次徽章和「榜单 ›」原本上下堆叠在右侧，重心全压在右边；合成一个「第 N 名 ›」胶囊。

### 6.4 色板统一

主色从 `#8C2F28`（偏橙）统一成 `#7B2D26`（高手榜顶栏那种绛红），暖黑 `#2A2522` 替代原来的冷黑 `#1F2328`，米底 `#F8F5F1`。详情页原来那条亮红顶栏一并收掉，全站只有一个强调色。

### 6.5 Kivy 上踩到的新坑

| 坑 | 现象 | 正解 |
|---|---|---|
| `Card(spacing=dp(12))` | 间距变成 40px，卡片被撑开 | `Card` 内部已经 `dp()` 过，必须传纯数字 `spacing=12` |
| `TextInput` 失焦掉色（待办 1） | 填入的 UID 是浅灰，像占位符 | `on_focus` 里每次都 `self.foreground_color = C_INK` 刷回，实测生效 |
| 透明背景 + 白卡 | 输入框「隐身」，只剩一行字 | 必须自绘 `RoundedRectangle` 背景，或换浅灰底 |
| `_set_body_card(False)` 顺手改 padding | 卡片左右边距被重置成 0，卡片贴边 | 复位时只管 canvas，padding 交给调用方 |

### 6.6 配色二轮调整（v22）

v21 里顶栏和主按钮是同一个 `#7B2D26`，整页看起来像一大块暗红，而且都偏深。v22 拆成四层：

| 用途 | 色值 | 白字对比度 |
|---|---|---|
| 顶栏 | `#8C4A3E` 浅绛棕 | 6.6 : 1 |
| 主按钮 | `#C25A3A` 朱砂 | 4.3 : 1 |
| 强调文字 / 聚焦描边 | `#A8482C` | 5.0 : 1（在浅粉底上） |
| 强调浅底（胶囊/徽章） | `#F9E4DB` | — |

两条经验：

- **强调文字不能跟按钮一起变浅**。浅粉底上的红字要 ≥ 4.5:1，如果直接用按钮色 `#C25A3A` 只有 3.4:1，字会发虚。所以按钮可以亮，红字必须单独留深色。
- **浅底第一版调得太白（`#FBEDE7`），装备胶囊和名次胶囊在白卡上直接消失**，退回 `#F9E4DB` 才看得出来。改主色时连带浅底要一起核对，不能只算主色。

`#C25A3A` 基本是「再浅一档」的上限：再往上白字对比度会掉到 3.5:1 以下。

### 6.8 字体修复（v23）

用户反馈：「门」字明显不正常、「入」字很僵硬，整体字体不好看。

**根因**：`_CN_CANDIDATES` 第一位是 `DroidSansFallback.ttf`，但新安卓（Android 9+）已经没有这个文件，于是命中第二位 `NotoSansCJK-Regular.ttc`。`.ttc` 是**字体集合**，Kivy / FreeType 只能取第 0 个 face，而 `NotoSansCJK-Regular.ttc` 的第 0 个 face 是**日文**：

- 简体「门」在日文字体里不存在（只有「門」），直接掉成豆腐块或回退到别的字体；
- 「入」用的是日文字形，笔画本来就僵；
- 其余汉字也全是日文字形骨架，所以整体「不好看」。

**试错记录**（这一步很关键，别走回头路）：

| 方案 | 结果 |
|---|---|
| `NotoSansSC-Regular.otf` + `NotoSansSC-Bold.otf` | 中文正常，但**拉丁全变方块**——它是纯 CJK 子集，不含 UID / 数字 / `/` / `·` |
| `NotoSansCJKsc-Regular.ttf` | ✅ 完整族（拉丁 + 简体），单体，中文和 ASCII 都正常 |

最终候选顺序：`NotoSansCJKsc-Regular.ttf` → `DroidSansFallback.ttf`（老设备）→ `NotoSansCJK-Regular.ttc`（末位兜底）。

**连带影响**：系统里没有「单体中文宋体」（`NotoSerifCJK` 同样是 `.ttc`，也是日文字形），所以标题的宋体被迫回退黑体。这是刻意选择——宁可标题少一点「江湖味」，也不能让字形出错。

**教训**：选系统中文字体不能只看文件名里有没有 `CJK`，要看两点：

1. 是不是 `.ttc`（集合，face 0 往往是日文）；
2. 是不是纯 CJK 子集（`.otf` 常见，缺拉丁会导致 UID、数字、标点全变方块）。

启动日志里打 `[font] FONT=... SERIF=...`，出问题先看这一行。

### 6.9 顶栏改版：复刻高手榜头部（v24）

用户要求：顶栏别再和内容各自成块，改成高手榜那种「印章 + 文字」的头部；同时**去掉「玩家查询」主标题**，只留一行说明。

| 项 | 改法 |
|---|---|
| 底色 | `#8C4A3E` 深绛红 → 与页面同色 `C_BG #F8F5F1`，靠底部 1px `C_LINE` 分隔 |
| 印章 | 44×44、圆角 10、`C_SEAL #7B2D26` 底，白字竖排「江湖」，衬线体 |
| 文字 | 只有一行 `放置江湖 · 多平台自助查询`，13sp `C_INK2`，与印章垂直居中 |
| 详情页 | 同步改浅底：`‹` 返回、分区名、UID、`修改` 全部改深色字，高度统一 58dp |

**印章字体**：`江湖` 用 `NotoSerifCJK-Regular.ttc`（就是那个 face 0 是日文的集合字体）。之所以敢用，是因为这两个字的日文与简体字形完全一致，不会出现「门」那种缺字。它也是全 App 唯一的衬线元素，负责撑住国风感。

`C_BAR` 这个常量暂时保留（当前无引用），后续如果要恢复深色顶栏可以直接用。

### 6.10 屏幕适配：模拟器 ≠ 真机（v25）

**病根**：MuMu 是 `900×1600 @ 240dpi`，换算逻辑宽度 **600dp**；真机普遍 **360~412dp**。同一套写死的 dp 值，在 600dp 上宽松，到 360dp 就挤——不是「手机 UI 变形」，是预览环境压根不是手机的宽度。

| 措施 | 实现 |
|---|---|
| 按逻辑宽度取留白 | `hp()`：≥520dp 时把内容收窄到 520 居中；<340dp 收到 10dp；其余 16dp |
| 视口日志 | 启动打印 `[ui] viewport 360 x 640 dp · density 3.00 · fontscale 1.00 · hpad 16` |
| 字体限幅 | `sp()` 把系统字体缩放钳在 1.0~1.12（真机常见 1.3，会把固定行高顶破） |
| 旋转/分屏 | `Window.on_resize` → 重算 `hp()` 并重排底栏 |
| 底栏尺寸 | 左右留白跟随 `hp()`，按钮边缘与卡片边对齐 |

**验证方式**（不用改代码，改模拟器密度即可）：

```bash
bash _agent_tmp/vp.sh 360    # 900px / 400dpi = 360dp，主流安卓
bash _agent_tmp/vp.sh 412    # 一般大屏
bash _agent_tmp/vp.sh reset  # 回到 MuMu 默认 600dp
```

已在 360dp 与 320dp 两档实拍验证：查询页、详情页、装备胶囊、传承行、武学分组均无截断重叠。

### 6.11 底栏瘦身（v25）

用户反馈：手机上「再查一个」显得过大，把右边的两个文字按钮挤成一坨。两个动作本身也都不重要：

- **复制 UID**：删掉，改成**点顶栏的 UID 直接复制**（`AppBar.bind_sub`），顶栏闪一句「已复制 UID · xxx」。
- **保存**：删掉。它只是把当前角色档案写成 JSON 丢进 `App.get_running_app().user_data_dir`（安卓私有目录 `/data/user/0/<包名>/files/`），用户既看不到也读不回来，属于写完就消失的功能。

现在底栏只有一个通栏主按钮（46dp 高），左右留白跟卡片对齐。

**顶栏的「修改」也一起去掉**：左边的 `‹` 就是回查询页，同一动作不占两个位置，也把标题行空间让给分区名。

### 6.12 剩余待办

1. 状态栏仍是白底黑字；`Window.setStatusBarColor` 需要 runOnUiThread，热更风险待评估。
2. 装备 5 件时最后一格空半行，若允许跨列可再优化。
3. 准备位展开/收起会整体重建 `_render`，滚动位置会回到顶部。
4. 武学 17 个分组各占一行（48dp），光分组头就接近一屏；可考虑并成两列或默认只显示前 6 组。
5. 若要「保存」真实可用，应改成导出到公共「下载」目录或走系统分享（需要 `jnius` 调 Intent，热更风险较高）。



## 七、v26：顶栏不再固定 + 中文字体打包

### 7.1 顶栏随页面滚动

原来 `AppBar` 挂在 `root` 上（固定），滚动时内容从顶栏下面穿过去，印章像一张贴在窗口上的贴纸，
和页面完全脱开。现在改成：

```
root ── sv(ScrollView) ── inner(BoxLayout)
                             ├── appbar
                             └── body
        └── foot（固定底栏，保留）
```

`inner` 用 `size_hint_y=None` + `minimum_height` 撑高，顶栏就成了"页面自己的头部"，
往下滚会一起滚走。代价是结果页滚到中段时返回箭头不可见，靠系统返回键（`_on_key` 已处理）。

### 7.2 字体打包进 APK

判定：**不再赌系统字体**。原因见 `docs/APK修改操作手册.md` §5.3 ——
三条系统路径都不保证存在，全落空会退回不含中文的 Roboto，而 MuMu 是 AOSP 永远测不出来。

- 生成脚本 `scripts/build_font_subset.py`：`NotoSansSC-VF.ttf` → 固定 wght=400 → 子集 21637 字 → 7.1 MB
- 字符集：CJK 基本区全量 + ASCII + Latin-1 + CJK 标点 + 全角 + 几何符号整段
- 探测顺序：`_local_font()`（打包子集）→ 系统指定路径 → 厂商字体（MiSans/HarmonyOS/OPPO/vivo）
  → `NotoSansCJK-Regular.ttc` → 扫 `/system/fonts`
- 老 APK 上 `_local_font()` 返回空 → 自动回退系统字体，热更不会把老用户搞成豆腐块
- `buildozer.spec` 的 `source.include_exts` 加 `ttf,otf`
- 启动日志：`[font] FONT=CN(打包子集) SERIF=CN SEAL=CNSeal`

**坑**：第一版字符集只挑了 `▲▼■□`，漏了折叠箭头 `▶`（U+25B6），武学分组全变 ☒。
Kivy 没有字体回退，所以改成按区段整段收（U+25A0–U+25FF）。

### 7.3 仍然存在的两件事

1. **标题的宋体**：`SERIF` 候选（`NotoSerifSC-*.otf`）在真机几乎不存在，实际是黑体。
   要做真宋体得再打包一个衬线子集（约 +5 MB）。
2. **「保存」功能**：原实现是把档案 JSON 写到 `App.user_data_dir`
   （安卓 `/data/user/0/com.fzjh.fzjhlookup/files/昵称_uid.json`），普通用户看不到，
   App 也没有读回入口，等于写了个隐藏文件。v25 已移除按钮；若要恢复，应改成导出到
   公共「下载」目录或系统分享，需要 `jnius` 调 `Intent`/`MediaStore`。

## 八、v27 / v28：导出分享 + 查询缓存

### 8.1 导出 / 分享（v27）

底栏从「一个主按钮」变成「导出 + 再查一个」，导出占 84dp，主按钮拿剩下的宽度。

- **保存到「下载」**：Android 10+ 用 `MediaStore.Downloads`，不需要存储权限
  （10 以下提示改用分享，不为一个 json 申请读写权限）。实测导出 19.5 KB，
  路径 `/sdcard/Download/昵称_uid.json`，重名自动生成 `(1)` 副本。
- **分享文本**：`ACTION_SEND` + `text/plain`，完整 JSON 交给系统面板。
- pyjnius 两个必须 cast 的地方：`ContentValues.put` 和 `Intent.putExtra`，
  都有 Integer/Long/byte[]/CharSequence 多个重载，不 cast 就抛
  `No methods called put`。与 `setText` 那个坑同源。
- Popup 默认背景图在这套主题里是半透明的，深色字压上去看不见 →
  用 `Card` 自绘白底，`background_color=(0,0,0,0)`。

### 8.2 查询缓存（v28）

| 项 | 值 |
|---|---|
| TTL | 600 秒 |
| 容量 | 12 份（单份约 20 KB） |
| key | `uid|server`（换区不串） |
| 失效 | 结构版本号 `_v`，改字段时 +1 即可全量作废 |
| 隔离 | 出缓存前 `json.loads(json.dumps(...))` 深拷贝，界面改字段不回写 |

命中时给结果打 `_cached`，界面 flash「10 分钟内的结果 · 再查一次可刷新」。
**强制刷新的交互是「同一个 UID 连点两次查询」**，不再往右上角加按钮
（那个位置已经被删过两次，用户明确不想放操作）。

逻辑用 6 个场景的本地单测验证：首次、命中、强制、过期、换区、深拷贝隔离。
**未在模拟器做端到端点击验证**——MuMu 在 density 400 下 `input tap`
只有部分区域生效（点输入框能聚焦、点「填入」无反应），不是应用问题。

### 8.3 数据链三处隐患（同步修）

1. `refresh.yml` / `merge-exp.yml` 的 concurrency 合并为 `fzjh-data`：
   两者都写 `data/servers/*`，原来分属两组，同时跑时后 push 的失败，那轮合并白做。
2. `merge_exp` 的 `exp-history` 快照只写**本轮真正刷新过档案**的玩家，
   未刷新的沿用上一条快照值；新增 `fresh` 字段记录本轮更新人数。
   否则三天没更新的玩家会在第四天被算成「日增 = 三天累积」。
3. `build_lookup_index` 加人数熔断：新索引 < 上一版 70% 直接失败，
   写入改成 `tmp + os.replace`。实测把上游文件移走后，7985 → 295 会被拒绝。

## 九、v29：输入框改用安卓原生文本框

### 9.1 为什么放弃 Kivy 的软键盘

真机反馈：点输入框不弹键盘，长按只有「粘贴」，一个字符都进不来。模拟器里
`dumpsys input_method` 显示 Kivy 从未真正拿到安卓的文本输入通道：
`[Window] virtual keyboard not allowed, single mode, not docked`。

Kivy 的链路是 `TextInput.request_keyboard → SDL_StartTextInput → SDLActivity 的
InputConnection`，而 `keyboard_mode` 只在 `Window` 创建时读一次配置，运行中再
`Config.set` 已经晚了；即便设成 `system`，部分 ROM 仍把这个通道掐掉。
之前那些补丁（`rekeyboard()`、ctypes 调 `SDL_StartTextInput`）都只是在这一层打转。

### 9.2 现在的做法

`apk/native_input.py`：点输入框直接弹系统的 `AlertDialog + EditText`。

| 能力 | 由谁负责 |
|---|---|
| 弹键盘 | 系统 IME（`showSoftInput` + `requestFocus`） |
| 中文输入 | 系统 IME（`TYPE_CLASS_TEXT`，不锁数字键盘） |
| 长按粘贴 / 全选 | `EditText` 自带 |
| 取值 | `getText()` → 兼容 `str` 与 `Editable` 两种返回（pyjnius 版本差异） |

`RoundInput` 里 `_native_ready()` 判断平台与 jnius；不成立时自动退回原来的
Kivy 行为，所以桌面调试与老版本都不受影响。查询框的确认按钮直接叫「查询」，
省掉一次点击；武学搜索框共用同一套。

**验证**（这次能端到端，因为原生控件吃 adb 注入）：
点框 → 弹窗 → `input text 7257325` → 点「查询」→ 日志
`[native_input] ok which=-1 txt='7257325'` → 真的发出了查询请求。

### 9.3 顺手修：失败态把表单吃掉了

`_fail()` 原来 `clear_widgets()` 重建「错误卡 + 示例」，输入框一起消失，用户
看到「该分区未找到」后没有任何输入入口。现在先 `show_query()` 还原表单，再把
错误卡插到 `body.children` **末尾**。

坑：Kivy 的 `add_widget` 默认 `index=0`，而 `vertical` 布局是**逆序铺**的——
`children` 末尾才是视觉第一行。所以「置顶」要写
`add_widget(w, index=len(children))`，写 `index=0` 反而落到最下面（先踩了一次，
用 `[dbg] fail-order` 打印每个子控件的 `y` 才确认）。

## 十、v30/v31：输入框终于能直接打字（真机 adb 定位）

### 10.1 真机实测结论

一加 Ace 6T / Android 17 / 搜狗输入法，`dumpsys input_method` 与 `logcat` 交叉验证：

```
mServedView=org.libsdl.app.DummyEdit    mInputShown=true
mServedInputConnection=org.libsdl.app.SDLInputConnection
```

**键盘其实弹出来过**，问题在三处叠加：

1. `WindowSDL` 每 0.2 秒轮询 `is_keyboard_shown()`，安卓上该值不可靠，
   一为 False 就 `release_keyboard()`，键盘一秒内被收走 → 「闪一下就没了」；
2. `keyboard_mode='system'` 时 `allow_vkeyboard=False`，而
   `WindowBase.request_keyboard` 里「把 `Window.on_textinput` 转给 Keyboard」的绑定
   写在 `if self.allow_vkeyboard and self.use_syskeyboard:` 里 → 直接跳过，
   **键盘弹得出来，字一个都送不到控件**；
3. Kivy 2.3 的 `TextInput` 在 system 模式下聚焦**根本不走 `_bind_keyboard()`**
   （用 `ime.log` 验证：只有 `focus=True`，没有 bind），所以重写 `_bind_keyboard()`
   或 `show_keyboard()` 都没用。

顺带纠正两个此前写错的判断：

- `keyboard_height` 在 SDL2 构建里恒为 0（`_get_android_kheight()` 直接 `return 0`，
  源码注明 SDL2 bootstrap 未实现），不能拿它判断键盘是否可见；
- 那句 `virtual keyboard not allowed, single mode, not docked` 是 `WindowBase.__init__`
  打的常规日志，`system` 模式和默认模式打出来一模一样，**不是报错**，之前误读了。

### 10.2 最终改法（apk/app_ui.py RoundInput）

```
_on_focus(True)
  ├─ _bind_ime(): Window.bind(on_textinput, on_key_down)
  │                + SDL_StartTextInput()   ← 自己弹键盘，绕开 Kivy 的 request_keyboard
  └─ select_all()                            ← 点一下就能覆盖输入
_on_focus(False)
  └─ _unbind_ime(): Window.unbind + SDL_StopTextInput()

_ime_text(win, text)  → insert_text(text)          # IME 中文 commitText 走同一通道
_ime_key(...)         → 退格 8 / 回车 13 / ESC 27   # 可打印字符不重复插（否则变 11）
```

`_bind_keyboard / _unbind_keyboard / show_keyboard / hide_keyboard` 全部转调这两个实现，
因为 Kivy 内部可能从任意一个入口触发。

双击输入框仍然弹原生 EditText（`apk/native_input.py`），作为 IME 彻底失效时的兜底。

### 10.3 验证

真机 adb 注入（原生输入框与内联都能测）：

| 操作 | 结果 |
|---|---|
| 点输入框 → `input text 12345` | 输入框显示 `12345` |
| 连续两次退格 | `123` |
| 重构后再测 `6789` + 一次退格 | `678` |
| 点输入框全选后再输入 | 覆盖旧内容，不追加 |
| 输入 `21079729670` → 点查询 | 结果页：刘小年 / 2707 级 / 第 1 名 |

热更链路：删 `files/live` 重启 → launcher 自动升到 v31，输入照常。

### 10.4 发布插曲

本时段 `github.com:443` 直连被 reset、代理 502，`git push` 全失败。
改用 **GitHub Git Data API**（token 取自 APK 内 `gh.json`，`admin` 权限）直接建
blob → tree → commit → 更新 `refs/heads/main`，等价于一次推送，Pages 正常构建。

## 十一、v32：输入框换原生内联 EditText + 结果页朱砂色带

### 11.1 输入框：安全键盘的根因

真机（一加 Ace 6T / Android 17 / 搜狗）`dumpsys input_method` 里能看到：

```
curEditorInfo:  inputType=0x91  imeOptions=0x12000000
```

`0x91` = `TYPE_CLASS_TEXT | TYPE_TEXT_VARIATION_VISIBLE_PASSWORD`。对输入法来说这是
「密码框」，所以必切安全键盘（没有中文）。这个值写在 SDL 的
`DummyEdit.onCreateInputConnection()` 里，`DummyEdit` 又是 `View` 子类 —— Python 侧
既改不了字段也覆盖不了该方法（试过反射，pyjnius 的 `Field` 没有 `setAccessible`；
`SDLActivity.showTextInput` 是 `(int,int,int,int)`，参数是键盘矩形 x/y/w/h，不是 inputType）。

**所以换成自己 new 的 EditText**（`apk/inline_input.py`）：

```
show(rect, text, on_text, on_done)
  └─ addContentView(FrameLayout > EditText)，绝对定位到 Kivy 控件的位置
     inputType=TYPE_CLASS_TEXT，白底 + 朱砂描边 + 12dp 圆角
     TextWatcher → on_text(文字) 回写 Kivy
     OnEditorActionListener → on_done()（当作回车）
hide() → 断开 TextWatcher → hideSoftInput → setSelection(0) → setText("") → clearFocus → GONE
```

四条踩过的坑：

1. **必须在 UI 线程建 View**。Python 跑在 SDLThread，直接 `addContentView` 抛
   `CalledFromWrongThreadException`，日志里是一长串 `Only the original thread that
   created a view hierarchy can touch its views`。做法：`runOnUiThread` + `threading.Event` 等待。
2. **只建一次**。每次点击都 add/remove 会在屏幕上留下输入法的选区拖柄（蓝色水滴），
   切页后还挂在原位。改成建一次，之后 `VISIBLE` / `GONE`。
3. **收起前先断开 TextWatcher**，否则清空输入框会把 `""` 回写给 Kivy，输入框内容被抹掉。
4. **不要改 App locale**。`res.updateConfiguration(conf)` 会触发配置变更，p4a 的
   Activity 直接 finish（真机表现为「点图标闪一下就回桌面」，logcat 无 traceback）。
   系统文本菜单本来就跟随系统语言，中文机自动是「全选 / 选择」。

### 11.2 结果页顶部：从红底白字到朱砂色带

```
v32 初版：顶栏整块 #7B2D26 + 白字
  ↓（用户：字别放在红色块里）
14dp 色带 → 24dp + 底部圆角 → 36dp 直角（#B45A3E）
```

最终结构：`inner = ToneBar(36dp) + AppBar + body`，色带是纯色块不含文字，
分区名与 UID 在其下方的米色底上用深色字。`ToneBar` 只在结果页有高度，查询页 `height=0`。

**坑**：`AppBar` 画布里 `Color(*C_BG)` 原来没存成属性，`_set_tone()` 访问 `self._bgc`
直接 `AttributeError` → Kivy 在 build 阶段崩溃 → 真机表现为「点了没反应」，logcat 里
没有任何 Python traceback。给两个画布块都补上 `self._bgc = Color(...)` 才正常。

## 十二、v33：昵称多命中弹窗重做

原实现是 `Popup` + 一排 `C_SOFT` 灰块 Button，昵称、分区、等级挤在同一行，
没有层次也没有按下反馈。重做后的结构：

```
Popup(background="", background_color 见下)
└─ 白底圆角卡 (radius 18)
   ├─ 标题区 62dp：「选择角色」(13sp 加粗) + 「找到 N 个匹配，点击选择」
   ├─ HLine
   ├─ ScrollView（超过 5 条才滚动）
   │   └─ PickRow 52dp：昵称(加粗) + 分区(灰) + 等级(右对齐)，行间 1px 细线
   ├─ HLine
   └─ 取消 48dp（文字按钮）
```

`PickRow(ButtonBehavior, BoxLayout)`：整行可点，`state == "down"` 时底色变
`C_SOFT`，替代原来靠 Button 背景色撑出来的假交互。

### 两个坑

1. **卡片外圈的黑框**：`Popup` 默认会把主题图 `atlas://.../popup` 按弹窗矩形缩放
   绘制，白卡之外就露出一圈深色。`background=""` 才能不画它。
2. **`background_color` 传构造参数无效**：`ModalView.__init__` 在应用 kwargs 之后
   又写了一次默认值 `(0,0,0,0.7)`，所以遮罩一直是 70% 黑。必须在弹窗建好之后
   `self._popup.background_color = (...)` 单独赋值。
3. 高度要手动加上 `Popup` 自带的内边距（约 48dp），否则最后一行会被裁掉。
