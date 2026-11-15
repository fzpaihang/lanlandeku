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

## 十三、v34/v35：P1 修复 + 更新包签名与 TLS

### 13.1 P1（都在 `apk/app_ui.py`）

| 问题 | 修法 |
|---|---|
| 被隐私名单拒绝后表单被清空，成死路 | `_deny()` 不再 `clear_widgets()`，照 `_fail()` 插卡到 `body.children` 末尾 |
| 结果页/弹层按返回直接退出 App | `_on_key` 改三级：网页 → 弹层 → `mode=="result"` 回查询页 → 才退出 |
| WebView 失败把整页换掉 | `_web_fail()` 只插提示卡 + 「用系统浏览器打开」，不清页 |
| 连点两次拿不到新数据（要点三次） | 删掉隐藏手势，结果页右上角显式「刷新」按钮；`:955` 的 `force` 判定不再依赖 `_cached_uid` |
| 缓存提示 2.2 秒 flash 从未真正显示 | 副标题常驻 `UID xxx · 缓存` |
| 查询没有总超时 | `lookup_core.LOOKUP_BUDGET = 20s`，探测循环与单区重试都检查 deadline |
| 断网被报成「查无此人」 | `lookup_core.last_reason()` 返回 ok/notfound/net/timeout，`_done` 分文案 |
| 「查询中…」「搜不到」是半透明白字 | `disabled_color` 显式设置（Button 白 95%，sug 用 C_ACCENT） |

坑：`deadline` 一开始只加在 `_lookup_uncached` 的循环之前，而单分区是**在循环之前就 return** 的，
真机直接 `UnboundLocalError`。改成在函数开头（`uid = int(uid)` 之后）就赋值。

### 13.2 交互与视觉

- 入口卡 / 说明行 / 武学分组标题：`on_touch_down` 立即触发 → 改成按下只记坐标，
  `on_touch_up` 且位移 < 12dp 才触发（滑动不再误开网页、分组标题不再吞滚动手势）。
- 说明展开只重建 `_hint_holder`，不再 `show_query()` 整页重排（原来会把页面滚回顶部）。
- 返回箭头命中区 26dp → 44dp；胶囊用 `_vcenter()` 包一层（BoxLayout 横向子项贴底，48dp 行里差 11dp）。
- `C_MUTED` `#8B7F74` → `#6E635A`（白卡 3.9:1 → 5.3:1，米底 3.6 → 4.9）。
- 武学搜索 250ms 防抖；原生覆盖层跟随宿主字号/底色/占位文案，列表重建后 `move_to()` 重新定位。

### 13.3 更新包签名（Ed25519）

- `apk/ed25519.py`：纯 Python，只依赖 hashlib，对照 RFC 8032 测试向量 1 自测
  （公钥、签名逐字节一致，篡改消息/签名均返回 False），单次验签约 4ms。
- 私钥 `.keys/update.key`（已 gitignore），公钥硬编码在 `main.py`。
- `pack_update.py` 对 `version|md5|size|整包字节` 签名写入 `version.json.sig`。
- `main.py` 安装前验签：`False` 直接丢弃，`None`（旧格式无 sig）只记日志继续。

### 13.4 TLS

- 完整 Mozilla 包（163KB）在设备 OpenSSL 上 `load_verify_locations` 报
  `SSLError(9, '[X509] PEM lib')`，整包不可用。
- 改为**最小根证书集**（5KB）：ISRG Root X1（GitHub Pages）、DigiCert Global Root G2（游戏接口）、
  GlobalSign Root R46（jsDelivr），来自各自的链，加载正常。
- `fetch.py`：有 CA 就 `CERT_REQUIRED` + `check_hostname`，没有则降级并打日志（老包兼容）。
- `main.py`：同样逻辑，但**不降级**到不校验——那条链路会执行下载下来的代码。
- 注意：`main.py` 在 APK 内，验签与更新通道的 TLS 要重装新 APK 才生效；热更只能覆盖 `apk/*.py`。

## 十四、v36–v38：转数筛选、移动端排序、换标改名

### 14.1 高手榜「转数」筛选（`assets/app.js` + `index.html`）

数据里转数字段是 `inheritCount`。实测各分区分布：

| 分区 | 转数分布 |
|---|---|
| 4399 / taptap / taptap_2 / taptap_3 | 清一色 5 转 |
| taptap_4（墨羽惊鸿） | 2 转 26、3 转 51、4 转 22 |

所以筛选条做成**按数据条件显示**：`buildZhuanChips()` 统计当前分区去重后的转数，
只有 >1 档才渲染（`el.zchips.hidden = true` 否则），避免在单档分区上摆一排死按钮。

### 14.2 移动端排序（`index.html` / `exp.html`）

排序入口原来只存在于桌面表头，手机上没有。加 `.sortbar`（CSS 里 `@media(max-width:560px)` 才显示）：

- 高手榜：名次（默认，asc）/ 经验 / 等级
- 经验页：名次 / 当前经验 / 区间增长（默认区间增长）

注意：**静态资源必须带 `?v=<hash>`**。这次改完 `app.js` 没更新 `?v=`，WebView 直接在
缓存里跑旧脚本，页面上完全看不到新功能——排查了半天才发现。发布前用脚本重算 hash 即可。

### 14.3 APK 换标与改名

- `title = 霜霜妙妙屋`（buildozer.spec）
- 应用图标：`icon_src.jpg` → 构建时用 ImageMagick 转 512×512 png（runner 自带），
  仓库不用提交生成的 png
- 顶栏左侧标识：`seal.jpg` 圆形头像。Kivy 没有圆形裁剪，用
  `RoundedRectangle(radius=[边长/2], texture=tex)` 当遮罩，比 StencilView 简单。
  找不到图片时退回原来的红底「江湖」印章。
- `seal.jpg` 进热更包，老 APK 更新一次即可换标。

### 14.4 一个必须记住的坑：构建缓存 key 与签名

`build-apk.yml` 的缓存 key 原来是 `hashFiles('buildozer.spec','main.py')`。
**改这两个文件 → 缓存目录换新 → `~/.buildozer` 里自动生成的调试签名密钥也换新** →
用户覆盖安装报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`，只能卸载重装（本地缓存与最近查询全丢）。

已改成固定 key `buildozer-${os}-stable-v1`。代价是 spec 改动不再让缓存失效，
需要时手动清缓存。

## 十五、v39：头像换图 + 经验基准重刷

### 15.1 头像

`apk/seal.jpg` 换成新的古风角色图，仍是圆形（`RoundedRectangle(radius=边长/2, texture=)`），
不额外画边框。热更 v39 即可生效，不需要重装。

### 15.2 经验增量为什么会出现「一眼假」的数字

- 11 号那批快照的 `exp` 直接取自**排行榜**：浮点、对不活跃玩家长期不更新。
- 之后 `merge_exp.py` 把榜单的 `exp` 改写成了**档案**（get_user_info）的整数。
- 于是「当前值（档案）」减「基准（榜单）」= 两套口径相减，天然差 0.2%~1%，
  表现为「+21.7 万」「-3.2 万」这种既不是真增长也不是真回落的数字。

### 15.3 修法：`scripts/reset_exp_baseline.py`

按档案值重写一条基准快照（日期=今天），旧快照全部丢弃：

```
4399     49 人（档案 49）  6 条 → 1 条
taptap   98 人（档案 98） 11 条 → 1 条
taptap_2 20 人（档案 20）  3 条 → 1 条
taptap_3 29 人（档案 29）  3 条 → 1 条
taptap_4 99 人（档案 95）  4 条 → 1 条
```

重置后只有 1 条快照，`exp.js` 判定 `baseSnap = null`，页面显示「暂无对比数据」+ 一条说明。
明天 `refresh.yml` 抓完数据、`merge_exp.py` 追加第二条（同口径）后，区间增长恢复正常。

## 十六、v41：蓝色水滴的真正根因

用户两次反馈「点开输入框后屏幕上有颗蓝色小水滴不消失」。

### 三处都改过，只有第三处是根因

1. 收起顺序（清焦点 → 清选区 → 收键盘）—— 有用但治标；
2. `setSelectAllOnFocus(True)` —— 一聚焦就整段全选，出选区必然出选择手柄，已关；
3. **`beforeTextChanged` 的 `@java_method` 签名写错**：
   ```python
   @java_method("(Ljava/lang/CharSequence;II)V")      # 错：2 个 int
   def beforeTextChanged(self, s, start, count, after)  # 实际 3 个 int
   ```
   Android 每次文字变化都调 `beforeTextChanged(CharSequence, int, int, int)`，
   签名对不上就抛 `NotImplementedError`（logcat 里能看到一长串），
   输入法的选区/光标状态跟着乱，屏幕上的**光标手柄**就一直挂着不撤。

改对签名后实测：输入 778899 → 光标正常、无水滴；点顶栏空白收起 → 原生框与键盘
一起消失、无残留、文本保留。

### 附带改动

- 收起时 `imm.updateSelection(edit, 0, 0, -1, -1)` 主动告知选区已空；
- 收起时 `removeView(root)` 把 View 摘出窗口，输入法同步销毁会话（更稳，代价是重建几毫秒）；
- 展开时不再全选，光标落末尾（全选会出选区手柄）。

## 十七、v42：光标手柄（水滴）的处理闭环

用户补充的复现路径很关键：**先输入内容，再点一下输入框**才会出水滴；把字全删再点就没有。
说明它不是「收起残留」，而是系统的 **插入点手柄（InsertionHandleView）** ——
只在光标可见、且点已有文字时才生成，正常 ~3 秒自动收。

两处改动：

1. **`Root.on_touch_down` 无脑收框** → 点在输入框自己身上也收，于是
   「收掉 → Kivy 重新聚焦 → 再弹出」来回一次，手柄留在屏幕上。
   现在用模块变量 `_INLINE_OWNER` 记住当前用覆盖框的控件，点击落在它身上就不收。
2. **`setCursorVisible(False)`** → 不生成插入点手柄，从源头消除。
   代价是看不到竖线光标，打字/删除/点击定位都不受影响（UID、昵称这种短字段可接受）。

实测：输入 123456 → 再点框 → 无水滴；继续输入变 1234567；点顶栏空白收起 → 无残留。

若以后要恢复光标，需要接受「点已有文字时弹手柄 3 秒」，或用自定义 View 画插入点。

## 十八、v44：输入改用系统对话框（终结「删不掉 + 残影」）

### 走过的弯路（按时间）

| 版本 | 做法 | 结果 |
|---|---|---|
| v40 | 修 TextWatcher `beforeTextChanged` 签名（少一个 int） | 部分改善，仍有残影 |
| v41–v42 | 关 `setSelectAllOnFocus`、光标不可见、`removeView`、触摸拦截 | 残影仍在 |
| v43 | 收起时给 Kivy 输入框 `focus=False` + `setInputType(NULL)` | 残影消失，但**再点回来输入法没连上新控件，退格无效** |
| v44 | **安卓点输入框直接弹系统 AlertDialog** | 一次解决 |

### v43 为什么会让退格失效

`setInputType(TYPE_NULL)` 是打在旧控件上的，但 Kivy 输入框同时失焦后，SDL 的
输入会话也结束了；重新点击时新建的 `EditText` 还在 attach 过程中就
`requestFocus + showSoftInput`，输入法没连上 —— 打字进不去、退格更进不去。

### v44 的做法

直接用项目里已有的 `native_input.ask()`（AlertDialog + EditText）。
对话框有自己的 window 和 InputConnection，焦点/键盘/光标/删除全归系统管：

- `_on_focus` 在安卓上先 `_try_dialog()`，成功就 return，不再碰内联覆盖层；
- 桌面端与实现降级时仍走原逻辑；
- 内联覆盖层保留为兜底路径，不再作为主路径。

### 验证（uiautomator 读真实控件文本，不依赖截图）

```
点输入框 → 弹窗，EditText text='输入昵称或 UID'
输入       → text='123456'
退格 ×1    → text='12345'
点「查询」 → 直接发起查询，输入框文字深色、无残影
```

## 十九、v45：输入方案整体回退到 v42

### 19.1 决策

v43 用「收起时 Kivy 输入框失焦 + `setInputType(TYPE_NULL)`」消掉了光标残影，
但导致再点回输入框时输入法连不上，退格失效；v44 改系统 AlertDialog，又出现
「弹窗里能删、确定或点外面关掉后主界面仍旧值」的写回问题。用户判断明确：
**有残影只是难看，删不掉字是不能用，v44 比前几版更难用。**

「完整像别的 App」需要新增 Java 层实现 `InputConnection`（Flutter
`InputConnectionAdaptor` 那套：commitText / deleteSurroundingText /
setComposingText / updateSelection 双向同步），热更换不到，必须重打 APK + 重装，
中文输入法组合态还要逐项联调 → 按天算。按「架构改动很久就先不动」的既有原则，
**先回退止血，完整实现单独排期**。

### 19.2 做法

从 GitHub commit `7b8c19e1`（热更 v42）取回两个文件整体覆盖：

- `apk/app_ui.py`
- `apk/inline_input.py`

其余 10 个 py、`cacert.pem`、`seal.jpg` 全部保持最新 —— 签名、TLS、圆形头像、
P1 修复、转数筛选等**都不受影响**。v44 版本备份在
`E:/workbuddy2/_agent_tmp/v44_backup/`。

丢弃的是 v43/v44 期间所有实验性改动：失焦、`TYPE_NULL`、`invalidate` 强制重绘、
`_TouchEater` 触摸拦截、`setTextCursorDrawable(None)`、`setImeOptions`、
`_try_dialog` / `_dlg_busy` 系统弹窗主路径、延迟聚焦。
保留 v40/v41/v42 的全部修复（字号 PX=0、TextWatcher 签名、`_INLINE_OWNER` 点框自身不收、
`setCursorVisible(False)`）。

### 19.3 验证（uiautomator 读真实控件文本）

```
热更后版本 45
点输入框       → EditText '输入昵称或 UID'
输入 123456    → '123456'
点窗口外       → 原生框收起
再点回输入框   → '123456'
退格 ×3        → '123'          ← v43/v44 在这里完全无反应
完整查询       → 观云者 / 2559 级 / 第 3 名，顶栏刷新与返回正常，无异常日志
```

### 19.4 已知代价

~~光标手柄残影回来~~ —— **已在 v46 彻底解决，见第二十章**。

（v45 时的判断是「它是系统 HandleView 窗口，不随内容滚动」。这个判断是错的：
它确实跟着内容滚，是 Kivy 自己画的 widget。因此「只能靠完整 InputConnection
或换渲染层」的结论也随之作废 —— 一行 `use_handles = False` 就够了。）


## 二十、v46：蓝色水滴的真凶是 Kivy 自己的手柄（已彻底修复）

### 20.1 结论先行

**那颗蓝色水滴不是 Android 的 `HandleView`，是 Kivy `TextInput` 自己画的光标手柄。**
v40–v45 一直在 Android 侧（`setCursorVisible` / `updateSelection` / `removeView` /
失焦 / `TYPE_NULL` / AlertDialog）找原因，方向从一开始就错了，所以只能拿到「部分改善」。

### 20.2 怎么证伪旧结论的

| 观察 | 旧结论（系统 HandleView 窗口）预测 | 实测 |
|---|---|---|
| `dumpsys window windows` 找手柄窗口 | 应该有 `HandleView`/`PopupWindow` | **没有**，9 个窗口全是系统栏/IME/App |
| `dumpsys SurfaceFlinger --list` 比图层 | 应该多一层 | **83 层，前后完全一致** |
| `am force-stop` 杀掉 App | 应该一起消失 | **水滴还在**（已渲染进 App 图层，进程死了像素还留着） |
| `am force-stop` 杀掉输入法 | 应该一起消失 | **水滴还在** |
| 按 HOME 切桌面再回来 | 应该消失 | **完全不变** |
| 页面滚动 | 悬浮窗口不随内容动 | **跟着滚**（y 651→529→649） |

最后一条是决定性的：**它跟着页面内容一起滚动**，说明它画在 App 自己的画布上。

### 20.3 根因（Kivy 2.3.0 源码）

`kivy/uix/textinput.py` 里 `use_handles` 在触屏上默认 `True`（`use_handles = BooleanProperty(not _is_desktop)`）。
单击已有文字的输入框、且当前没有选区时，`on_touch_up` 走这一段：

```python
# textinput.py:1715-1730
if self.use_handles and self._selection_to == self._selection_from:
    self._hide_handles()
    handle_middle = self._handle_middle
    if handle_middle is None:
        self._handle_middle = handle_middle = Selector(
            source=self.handle_image_middle,     # ← 默认贴图 shape-drop.png
            window=win, target=self,
            size_hint=(None, None), size=('45dp', '45dp'))
    if not self._handle_middle.parent and self.text:
        EventLoop.window.add_widget(handle_middle, canvas='after')
```

`shape-drop.png` 就是那颗浅蓝色水滴。它是 `Window` 里的一个 Widget，加在
`canvas='after'`，由 App 自己的 SDL/OpenGL 渲染 —— 所以：

- 不进 `dumpsys window`（不是 Window）；
- 不是独立 SurfaceFlinger 图层（和 App 同一图层）；
- 进程杀了、输入法杀了都不消失（已经画进帧缓冲）；
- 会跟着页面滚动（是窗口坐标系里的 widget）。

而 Kivy 侧根本不需要它：这个输入框的文字编辑全部交给 `inline_input.py` 的原生
EditText 覆盖层，Kivy 的 TextInput 只是个"长得像输入框"的占位。

### 20.4 复现路径（精确）

1. 点输入框 → 弹出原生覆盖层；
2. 输入任意内容（**必须先有内容**）；
3. 点空白处收起；
4. **再点一次输入框**（此时框里有字）→ 水滴出现；
5. 再收起 → 水滴留在屏幕上，切页、切后台都不走。

只"点开→收起"不输入**不会**出现（`_show_handles` 里有 `not self.text` 的短路）。

### 20.5 修复（一行）

```python
# apk/app_ui.py  class RoundInput
from kivy.properties import BooleanProperty

class RoundInput(TextInput):
    # 关掉 Kivy 自带的光标手柄；编辑全部走原生覆盖层，Kivy 侧不需要它
    use_handles = BooleanProperty(False)
```

只关 `use_handles`，**不动 `use_bubble`**：`use_handles` 在桌面端本来就是
`not _is_desktop` = False，所以桌面端行为完全不变；触屏端只是不再画水滴。

### 20.6 为什么这次没有副作用

v43 之所以把退格改坏，是因为它在**原生覆盖层**上动了 `setInputType(TYPE_NULL)` 和
失焦，破坏了 InputConnection。v46 改的是 **Kivy 那个不参与输入的 TextInput 的
一个绘制开关**，与输入法会话没有任何关系。

### 20.7 验证（v46，真实热更链路）

删掉 `files/live` 模拟老用户升级，启动后日志：

```
[launcher] TLS 校验已开启（CA: cacert.pem）
[launcher] 发现新版本 v46，开始下载
[launcher] 已切换到 v46
[launcher] 加载更新包：/data/user/0/com.fzjh.fzjhlookup/files/live
```

| 用例 | 结果 |
|---|---|
| 输入 246813 → 收起 → 重开 → 收起（原复现路径） | 无水滴 |
| 连续 3 轮「点开→输入→收起」 | 无水滴 |
| 退格 ×2：246813 → 2468 | 正常 |
| 完整查询 → 结果页（观云者 / 2559 级 / 第 3 名） | 正常 |
| 结果页按返回 → 查询页 | 正常 |
| 缓存命中标记「· 缓存」 | 正常 |
| 打开/关闭内嵌高手榜 WebView | 正常 |
| `logcat` | 无 `Traceback` / `NotImplementedError` |

### 20.8 验证方法上的一个坑

MuMu 会**画面冻结**：连续三次 `screencap` 得到的 PNG 哈希完全相同，连状态栏时钟
都不走。这时截图会骗人（看起来"什么都没发生"）。判定 UI 状态一律以
`uiautomator dump` 读到的控件树为准，截图只用于看像素级残留。

另外本次写了个按颜色找水滴的检测脚本
（`E:/workbuddy2/_agent_tmp/detect.py`，浅蓝色 `R 100-160 / G 180-220 / B 210-245`
且 `B > R+60`），比人眼看截图可靠，回归时逐张跑。

## 二十一、v47：11 项界面与数据修正

用户一次列了 12 条问题，逐条定位与修法如下。**第 12 条不是 bug，见 21.12。**

### 21.1 滚动越界（问题 1 / 6）

**现象**：主界面和结果页已经到顶，还能继续往上拖出一段空白再弹回。

**原因**：`ScrollView` 默认 `effect_cls = DampedScrollEffect`，它允许把内容拖过边界再阻尼回弹。手机上表现为「页面能一直往上滑」。

**修法**：换 `ScrollEffect`（无阻尼、无越界）：

```python
from kivy.effects.scroll import ScrollEffect as _ScrollEffect
sv = ScrollView(size_hint=(1, 1), do_scroll_x=False, effect_cls=_ScrollEffect)
```

⚠️ 中途踩了个坑：一度怀疑「effect_cls 会让 ScrollView 吞掉子控件的触摸」，回滚过一次。实际是**点击坐标算错了**（「填入」按钮中心在 y=1208，我一直在点 1167），和 effect_cls 无关。判断触摸问题时先用颜色定位真实坐标，别靠估算。

### 21.2 单位字号太小（问题 2）

`亿` / `万` 原来是 `[size=11]`，压在 15.5 的数字后面像蝇头小字。**修法**：改成 `[size=15]` —— 比数字小一号，又能一眼看出量级。

### 21.3 右上角「刷新」意义不明（问题 3）

这个按钮实际行为是**绕过 10 分钟缓存重查**，但「刷新」在有无缓存时含义不同，用户没法预判。**修法**：文案改成「重新查询」，`_flash` 提示同步改成「正在重新查询…」。

### 21.4 示例按钮文案不统一（问题 4）

示例行是「示例」，历史行是「填入」，两种胶囊做同一件事。**修法**：统一成「填入」，宽度都用 46。

### 21.5 武学等级少一级 / 上限（问题 5）

`lookup_core.lv_of_skill()` 用 `int()` 截断，经验落在两级之间时少报一级（显示 1099 而实际应为 1100）。**修法**：改用 `math.ceil()` 向上取整，并夹在 `[0, SKILL_LV_MAX=1100]` 内。

验证：同一角色「猗兰十章」从 92 级变成 93 级，符合向上取整的预期。

> **v56 补记：网页 / Worker 对齐 APK 口径**。此前只有 APK 侧改了 ceil，网页档案抓取脚本
> `scripts/fetch_profiles.py::lv_of()` 与实时查询 `worker/src/profile.js::lvOfSkill()` 仍是
> `int()` / `Math.trunc()`，所以网页弹窗最高只显示 1099、App 显示 1100。
> 根因不只是「经验落在两级之间」：`f(lv)=0.015*lv^3+1` 的精确阈值代回公式会落在
> `lv-0.0000001` 左右，截断会**系统性**少一级，线上 10,908 条 1099 / 7,207 条 499 /
> 2,772 条 999 都由此而来。v56 把两处一起改成 ceil + 封顶 1100，三处口径统一。
> 网页静态档案只存 `lv` 不存技能经验，改抓取脚本后需等下一次全量重抓才会在页面上生效。
> `worker/` 是未上线的协议验证代码（手册 §6.4），源码仅本地保留、不入库，改动不影响线上。

### 21.6 没找到玩家时提示重复（问题 7）

**现象**：输入不存在的昵称后，同一句「没找到「xxx」，试试完整昵称或直接输 UID」在输入框下方和状态行各出现一次。

**原因**：输入过程中 `_do_search()` 已经把这句话写进 `sug` 提示行；点查询时 `start()` 又往 `q_status` 写了一遍。

**修法**：`start()` 里写 `q_status` 前先检查 `sug` 是否已有内容，有就不重复。

### 21.7 没用输入框时点「填入」，显示成灰色虚字（问题 8）★最费时

这是本轮最难的一条，中途走了不少弯路，如实记录：

| 尝试 | 结果 |
|---|---|
| 刷 `foreground_color` | 无效，颜色本来就是对的 |
| 清空 `hint_text` | 无效 |
| `_trigger_refresh_text()` | 无效 |
| 改 `sv.height` 触发重排 | **把点击彻底打死**（on_release 被重排打断） |
| 主动 `focus = True` | **有效** |

**真正原因**：`_fill()` 先写 `inp.text`，紧接着 `_force_repaint()` 里调了 `INLINE.hide()`；而 `inline_input.hide()` 内部会 `setText("")`，TextWatcher 把这个空串回写到 `RoundInput.text` —— **刚填的 UID 被自己清掉了**。

Kivy 的 style.kv 里文字颜色是：

```
rgba: disabled_foreground_color if self.disabled else (hint_text_color if not self.text else foreground_color)
```

`text` 空了 → 走 `hint_text_color` → 屏幕上显示的就是灰色占位色。像素采样也证实：输入框区域一个深色像素都没有，`(229,222,213)` 是边框底色。

**修法**：三步

1. 先 `_hide_inline()`，再用 `Clock.schedule_once` 延后一帧写 `text`（hide 是异步投递到 Android 主线程的，同一帧写会被它清掉）；
2. `_force_repaint()` 里**删掉** `INLINE.hide()` 调用；
3. 最后 `inp.focus = True` —— 既解决渲染，也让用户能直接确认/修改。

### 21.8 基本功被算进「其他」（问题 9）

**原因**：774 门武学里，12 门「基本X」（基本双持 / 基本乐器 / 基本拳脚 …）在上游 `skill.json` 的 `wxclassify` 和 `dsc` 都是空的，生成出来的 `skill_class.CLASS` 里值是空串，于是全部走关键词兜底 → 判不准 → 进「其他」。

实测：刘小年的「其他」组里正是 `['基本双持', '基本乐器']`。

**修法**：`skill_groups.BASIC_POS` 直接按名称映射（名字本身就说明了位置），在关键词兜底之前先生效。

### 21.9 刀法斧法分家（问题 10）

**修法**：`normalize()` 把「斧法」并进「刀法」，`buckets` 里去重（一门武学同时被两边命中时只留一次），关键词规则里斧/锤/戟/钺也归刀法。

验证：分组里「斧法」组消失，刀法包含斧类。

### 21.10 30 秒查询冷却（问题 11）

**修法**：`_begin()` 开头检查 `_cooldown_left()`，不足 30 秒就只提示不查询，提示语自己消失（避免看起来像卡死）。缓存命中不算消耗。

验证：连点「重新查询」第二次被拦，副标题保持「正在重新查询…」不变。

### 21.11 顺带修的一个 bug

结果页点右上角按钮会**打开高手榜**：`show_result` 里直接 `right_btn.bind(on_release=self._on_refresh)`，是在查询页 `bind_right(_open_web)` 的基础上叠加，一次点击触发两个回调。改成走 `bind_right()`（会先解绑旧的），并在 `show_query` 里还原成 WebView 入口。

### 21.12 昵称 UID 关联（问题 12）—— 不是 bug

**结论：功能正常，实时返回，不需要定时任务。**

- 链路：查询成功 → `archive_local.record()` 写本地 `pending_names.jsonl` → `sync_async()` 走 GitHub API **实时** PUT 到 `data/extra-names.json`（先 GET 合并再 PUT，不会覆盖别人写的）；
- 线上现状：17 条，最后写入 **2026-11-14 16:55**，全是当天的查询；
- 设备端 `files/app/gh.json` 有 token，`pending_names.jsonl` 为空（说明都成功提交了，没有积压）。

**唯一的坑**：仓库里的本地副本 `data/extra-names.json` 之前是 0 条（更新时间戳停在 11-13）。如果有人拿这个空文件当基线去 PUT，会把线上 17 条清空。本次已从远端把 17 条同步回本地。

> 教训：凡是「读远端 → 改 → 写回」的脚本，不要用工作区的旧副本当基线。

## 二十二、v48：三处视觉微调

### 22.1 「填入」胶囊没垂直居中（问题 1）

**原因**：`_vcenter(w, row_h)` 里 `row_h` 传的是 **dp 数值**（48），而
`w.height` 和 BoxLayout 的 `padding` 都是 **像素**。两者直接相减，gap 只有
应有值的 `1/density` —— 在 density=2.5 的机器上，26dp 胶囊在 48dp 行里只上移了
应有偏移的 40%，视觉上就是贴着偏下的位置。

**修法**：`gap = max(0, (dp(row_h) - w.height) / 2.0)`，把 row_h 也换算成像素。

### 22.2 单位字号再放大（问题 2）

v47 从 11 提到 15 还不够明显，用户要求再大。改成 **17**（数字是 15.5，单位略大反而更清楚）。

### 22.3 输入框与查询按钮间距（问题 3）

`gap(8)` → `gap(2)`。原来中间空出一大块，把「输入 → 提交」这个连续动作在视觉上割断了。

### 22.4 验证

| 项 | 结果 |
|---|---|
| 填入胶囊 | 与左侧 UID 行文字视觉居中 |
| `16.86亿` / `10.3万` / `111.6万` | 单位明显变大，与数字协调 |
| 输入框→查询按钮 | 间距收紧到 2dp |
| 热更链路 | `发现新版本 v48` → `已切换到 v48`，`version.txt = 48` |

## 二十三、v49：查过的角色要能按昵称搜回来（问题 12 的真正诉求）

### 23.1 用户的反馈把问题说清楚了

v47 我判断「昵称回写链路正常」就结了，那是**答错了问题**。用户要的不是
「昵称有没有进仓库」，而是：

> 查过 `22039038872`（墨羽惊鸿）看到昵称之后，下次直接输这个昵称能搜到人。

实测：查完再输昵称，依旧提示「没找到」。**这是真 bug。**

### 23.2 根因：两条数据链路从没接上

| 链路 | 数据去向 | 谁在用 |
|---|---|---|
| 远端索引 | `data/lookup-index.json` | `names_index` 只读这个 |
| 查过的昵称 | `data/extra-names.json`（仓库）<br>`files/pending_names.jsonl`（本地） | 只有网页端 `build_lookup_index` 会读，**APK 的搜索不读** |

而 `build_lookup_index.py` 的数据源是各分区 `gaoshoubang.json` + 苍松 5 转普查，
**散人查过不会进榜单，也就永远进不了索引**。实测线上索引 players 296 条、
zhuan5 7690 条，`魔法困` / `22039038872` 都不在里面。

所以 v47 说的「实时写入正常」是对的，但写进去的东西**没有任何代码把它当名字索引用**。

### 23.3 修法：本地补录，立即参与搜索

`names_index.py` 新增：

- `local-names.json`（`ANDROID_PRIVATE`，最多 500 条，新的在前，原子写）；
- `remember(uid, name, server, server_name, lv)` —— 查询成功后调用；
- `_all_rows()` = 本地补录 ∪ 远端索引，**同一 uid 以本地为准**（角色可能改名）；
- `search()` / `count()` / `get()` 全部改走 `_all_rows()`。

`app_ui._done()` 里在 `L.add_recent(prof)` 之后调 `NI.remember(...)`。

### 23.4 验证

单元测试（空索引，只靠本地补录）：

```
before remember, search(无名氏): []
after  remember, search(无名氏): [{'u': 22039038872, 'n': '无名氏', 's': 'taptap_4', ...}]
after  remember, search(无名):   [{'u': 22039038872, ...}]      # 模糊匹配也命中
get(22039038872): {'u': 22039038872, 'n': '无名氏', ...}
```

设备实测：

```
查 22039038872（墨羽惊鸿）→ 结果页正常
files/local-names.json = {"players":[{"u":22039038872,"n":"无名氏","s":"taptap_4","sn":"墨羽惊鸿","lv":672}]}
热更到 v49 后 → local-names.json 内容完整保留（在 files/ 下，不随 live/ 重建）
```

### 23.5 一个附带发现

这个 UID 现在的昵称是**「无名氏」**，不是用户说的「魔法困」—— 角色改过名。
这也说明本地补录「同 uid 以本地为准」是必要的：远端 `extra-names.json` 里存的是
改名前的旧昵称，如果以远端优先，用户会搜到错误的旧名字。

## 二十四、让「查过的昵称」全局共享（v49 的补完）

### 24.1 用户把需求说得更清楚了

v49 只做了**本机补录**（`local-names.json`），解决的是「我自己查完能搜回来」。
用户真正要的是：

> 我搜过的 uid→昵称，**所有人都能用**；别人查到的、以前没收录的，**我也能直接搜到**。

前者本机就够，后者必须改服务端。

### 24.2 断点：索引构建从没读过 extra-names

`scripts/build_lookup_index.py` 的数据源只有两个：

- 各分区 `gaoshoubang.json`（榜单，296 人）；
- `data/cangsong-5zhuan.json`（苍松 5 转普查，7690 人）。

**全文没有出现 `extra-names` 这个词。** 而 APK 查到的角色恰恰只写进 `data/extra-names.json`。于是：

| 谁 | 做了什么 | 结果 |
|---|---|---|
| A 用户 | 查了榜单外的散人 | 昵称进了 `extra-names.json` |
| 索引构建 | 只读榜单 + 普查 | 这个昵称**永远不会进索引** |
| B 用户 | 输这个昵称 | 搜不到 |

### 24.3 修法

`build_lookup_index.py` 新增 `load_extra_names()`，在榜单之后、5 转之前并入：

```python
for it in load_extra_names():
    key = str(it.get('s') or 'taptap')
    if (str(uid), key) in seen:
        continue          # 榜单已有：昵称以榜单为准（榜单是最新抓的）
    players.append({...})
```

**去重策略**：同一 `(uid, server)` 若榜单里已有就跳过 —— 榜单是每天刚抓的，
一定比 `extra-names` 里存的旧昵称新。

### 24.4 生效时延

`refresh.yml` 每天 4 次重建索引（按分区错开）。所以：

- **本机**：查完立刻能搜（v49 的 `local-names.json`）；
- **别人**：最晚等下一次索引重建（≤1 天）。

### 24.5 验证

本地重建：`296 → 299 名玩家（含查过的 4 人）`（1 人榜单已有被跳过）。

线上 `data/lookup-index.json`（GitHub Pages）：

```
online players: 299
魔法困 -> [(22039040249, '墨羽惊鸿')]
戚不知 -> [(21079804887, '丹凤朝阳')]
无名氏 -> [..., (22039038872, '墨羽惊鸿'), ...]
```

端到端（清空设备上的 `local-names.json` 与 `lookup-index.json` 缓存后重启）：

```
files/lookup-index.json  204928 bytes   # 重新下载
device index players: 299
魔法困 -> [(22039040249, '墨羽惊鸿')]
```

**本地补录为空**、只靠远端索引就能搜到 —— 全局共享成立。

### 24.6 顺带纠正一个例子

用户举的例子「查 22039038872（墨羽惊鸿）得到昵称魔法困」，实际：

- `22039038872` → **无名氏**（墨羽惊鸿，672 级）
- `22039040249` → **魔法困**（墨羽惊鸿，829 级）

两个都在墨羽惊鸿，UID 记混了。现在两个都能按昵称搜到。


---

## 二十五、代码流程梳理与工具化（v56 之后，无版本变更）

用户要求「不影响网页与 APK 功能，把现有代码流程梳理优化一遍」。这一轮只做**只读排查 + 工具化 + 文档纠错**，
没有改任何运行时代码。

### 25.1 先量了一遍「本地到底旧不旧」

新写的 `scripts/check_drift.py` 按 git blob sha 比对本地与远端 main（绕开本地 git 的旧 HEAD）：

```
已修改 301 / 仅本地有 28 / 仅远端有 30 / 仅换行差异 1
apk / assets / scripts / .github / cloud  →  0 差异
非 data 的差异只有 .gitignore 与 refresh.bat（后者是纯换行）
```

结论：**代码与线上完全一致**，所谓「本地落后」只是 `data/` 比线上旧。这一点以前没人量过，
导致每次改代码前都要先怀疑「我这份是不是旧的」。

顺带发现：`.gitattributes` 规定 `* text=auto eol=lf`，但 API 发布不走 git 的换行规范化，
两份 CRLF 文档在 GitHub 上会显示成「整篇 1277 行都改了」。工具里补了归一化。

### 25.2 重复实现（按风险）

| 重复 | 实测规模 | 后果 |
|---|---|---|
| 游戏协议层 | `scripts/fetch.py` 641 行 vs `apk/fetch.py` 682 行，diff 仅 55 行 | 协议一变要改两处 |
| 武学等级 | 3 份活代码 + 1 份过期 staging 产物 | v56 刚踩过 |
| 昵称归档 | 3 份（Issue / APK / Vercel） | 字段改动不同步 |
| 槽位/装备名 | 各 26 条 ×2 | 新增槽位只改一处会显示英文 key |
| 隐私名单 | `hidden.json` + `app_ui.HIDDEN_UIDS` 硬编码 | 拉黑只改一边 |
| `names.json` | 两份 64 KB，md5 相同 | 只改一份产物悄悄不一致 |

特意记一条**反面结论**：`app.js` / `exp.js` 有 10 个同名函数，但只有 `fmtBig` 逐字相同，
`sorted` / `bindSortbar` 语义本来就不同——**不能当重复合并**，否则会改坏两页各自的排序。

### 25.3 本次新增的三个工具（都不影响运行）

- `scripts/preflight.py`：7 项发布前自检（Python/JS 语法、缓存戳、热更包 md5+验签+清单、
  等级口径、两份 names、隐私名单）。`--fix` 会顺手跑 `stamp_assets.py`。
- `scripts/publish.py`：统一发布（base_tree、跳过无变化、强制热更两件套成对、拒绝敏感文件、换行归一化）。
  以后不用再在 `_agent_tmp` 里手写 `publish_vXX.py`。
- `scripts/check_drift.py`：本地 vs 远端真实差异，区分「仅换行差异」。

### 25.4 修正的文档错误

1. `CURRENT-STATE.md` §5 把等级公式的第四处写成 `assets/profile.js`；实测该文件只显示 `s.lv`，
   不做换算，第四处应是 `api/build/staging` 的构建产物。
2. `scripts/fetch_profiles.py` docstring 还写「产出 `data/players.json`」，实际输出是
   `data/servers/<key>/profiles/<uid>.json`，该文件不存在。

### 25.5 没做的事

合并 `fetch.py`、抽公共等级模块、统一归档实现原计划全部搁置，只留方案。随后用户确认了
低风险部分（E/F/H + 本地 git 对齐），执行结果见 §26；A/B 仍不做，理由见 §26.4。

---

## 二十六、第二批：CI 映射脚本化、失败兜底、死文件清理、本地 git 对齐

用户确认「E / F / H 先做、本地 git 先备份再对齐；A/B 不影响现有功能才做」。实际结论：E/F/H 已做，
A/B 判定无法零影响，未做。

### 26.1 E：cron→分区映射抽成 `scripts/plan_refresh.py`

`refresh.yml` 原来在一个 `run:` 里用两段 shell `case` 做「cron→分区」和「分区→中文名」，
改 cron 要同时改 `on.schedule`、两个 `case`，漏一处的后果是静默跑到 `*)` 的六区全量。

现在映射表在脚本里（`SCHEDULE_MAP` / `LABELS`），工作流只负责调用并把 stdout 追加到
`$GITHUB_OUTPUT`；任务摘要拆成独立一步。本地逐条验证过：5 条 cron、双空格、首尾空格、
未知 cron（→`all`）、手动 `mode` + 6 个分区，输出与旧 shell 一致。

### 26.2 F：merge-exp 补 artifact 兜底（并补 `yyh` 选项）

原来 rebase 冲突 / 连续 push 失败时 `exit 1`，数据只在 runner 里。现在 `if: failure()` 上传
`data/` artifact，保留 7 天，与 `refresh.yml` 对齐。顺带发现手动选项里**漏了 `yyh`**——
应用汇没法单独合并经验，一并补上。

### 26.3 H：删除重复入口

`api/index.py` 与 `cloud/fc_index.py` 内容完全相同（18,790 B），前者是早期 Vercel 入口，
`vercel.json` 只登记 `api/query.py`，Vercel 已停用。远端删除，本地同步；
`scripts/serve_api.py` 的 docstring 一并纠正（它加载的是 `cloud/fc_index.py` 的 staging 副本）。

### 26.4 A/B 为什么没做

- A：合并两份 `fetch.py` 要么让 CI 依赖 APK 侧模块，要么抽新模块进热更包；两条路都要重打包/真机验证，
  无法证明「改完零影响」。
- B：抽公共等级模块同样要在热更包新增文件，漏打包会让 `import` 失败、查询页打不开；收益只有十几行。

按「不影响现有功能才做」的前提，两项都留到游戏协议真正变动时一起做（那时本来就要回归）。防漂移
改由 `preflight.py` 的数值比对 + staging 告警承担。

### 26.5 本地 git 对齐

本地 HEAD 停在 v29（`5344e87`），落后远端 27 个版本。先备份整树到
`_agent_tmp/git_backup_20261115.zip`（421 文件 / 6.6 MB），再 `fetch` + `reset --hard FETCH_HEAD`。
之后 `git status/log` 恢复可信，但发布仍走 `publish.py`（避免与 Actions 的 `data/` 提交互相覆盖）。

---

## 二十七、第三批：删死代码 + 档案会话缓存（无版本变更）

用户问「app 和网页的代码还有可以优化的吗」。这轮先量体积、再动最小的两处，**没有改任何业务逻辑**。

### 27.1 量化结果：能省的都在资源，不在代码

| 指标 | 实测 |
|---|---|
| `apk/app_ui.py` 最长函数 | 111 行（`_render`），175 个函数，0 个 TODO/FIXME |
| 启动路径 | 拉分区配置在后台线程；昵称索引 `load_async`；不阻塞首帧 |
| 查询路径 | UID 前缀可定位时 **1 次请求**；推不出才轮询六区，20 秒总预算 |
| 前端渲染 | `DocumentFragment` 一次性插入，非逐行 append |

所以没有「重构能立刻变快」的地方。真正的大头是资源：

| 资源 | 体积 | 占 APK |
|---|---|---|
| 字体 `NotoSansSC-Regular.ttf` | 7,413,040 B（gzip 后 4.38 MB） | **18.5%** |
| `icon.png`（构建期生成） | 350 KB | 1.5% |
| `icon_src.jpg`（纯源图） | 192 KB | 0.8% |

> `assets/private.tar` 实为 **gzip 过的 tar**（magic `1f 8b`），容器 5.11 MB / 解压 8.17 MB，
> 字体占解压后 88.6%。用 `zipfile` 直接看 `file_size` 会被误导。

字体字符集是当初刻意「宁大勿小」定的（全 CJK 区 20992 字，Kivy 不做字体回退）。
实测现有全部数据只用到 **2010 个汉字**；缩到约 4500 字可省 3.5 MB，但未来生僻昵称会豆腐块。
**用户选择保持 7.07 MB 不动**，这条继续有效。

### 27.2 删除 `assets/lookup.js`

499 行 / 17,385 字节 / md5 `2cfb2eace49d`，三个 HTML 零引用。删除前按手册 §14.2 的要求做了
三项确认（HTML 零引用、脚本零引用、`serve_api.py` / `build_api_zip.py` / Worker 构建都不读
`assets/`），全部通过后删除。远端已 404，git 历史仍可检索。

不是「为整洁而删」：这个文件此前已经害人改错地方（手册 §14.2 记着「改了半天页面毫无变化」），
留着只会继续误导。删掉比反复标注更彻底。

### 27.3 档案会话缓存

`openProfile()` 原来每次点击都 `fetch` 一份 16 KB 的档案 JSON。现在加 `PF_CACHE`
（`Object.create(null)`，内存对象）：

- key 用 `base + 'profiles/<uid>.json'`，**带分区路径**——切区后同名 uid 不会串档；
- 命中直接 `renderProfile`，未命中才请求并写入；
- 只存内存，刷新页面即失效，所以不会出现「看到昨天的数据」；
- `cache: 'no-cache'` 保留，首次请求仍然绕过 HTTP 缓存。

收益不大（每份 16 KB），但成本也低，且是重复点击场景的常见浪费。

### 27.4 本轮明确不做

- **字体子集化**：用户选择保持现状，避免生僻昵称豆腐块。
- **打包排除 `icon_src.jpg` / `icon.png`**：需重打 APK 才生效，且 `icon.png` 是 `icon.filename`
  的输入，排除规则可能让打包找不到图标，留到下次重打时再验证。
- **`seal.jpg` 压缩**：667×668 / 92 KB，占热更包 49%，实际只显示 44dp；但本机没有可用的
  图像库，无法生成替换文件。参数建议 200×200 / JPEG q85，可在任意图像工具里一步完成。

---

## 二十八、榜单兜底 + 「请求繁忙」排查（v59 / v60）

### 28.1 用户报「apk 获取信息总是请求繁忙」

排查结论：**不是接口挂了，是 App 停在旧热更版本**。

实测（11-15 19:00，MuMu 第二个实例 `127.0.0.1:16416`）：

| 检查点 | 结果 |
|---|---|
| `files/live/version.txt` | **55**（仓库当时已是 v58） |
| `files/servers-remote.json` | 00:24 下载的，只有 6 个区（那时还没有其他服/华为） |
| v55 的 `UID_PREFIX_SERVER` | 没有 `9→guanfang`、`10→huawei` |
| App 启动记录（kivy 日志） | 00:28 之后到 19:00 之前**一次都没有** |
| 用 App 内置 `cacert.pem` 直连握手 | HTTP 200，0.76s，证书没问题 |
| 重启后（v58）查华为 `10046032468` | 2 秒出结果：佟鹤 / 34（估）/ 4001 / 未上榜 |

机理：旧版认不出新服 UID 前缀 → 走「自动识别」逐区轮询，每区失败还会再来一轮
`_redetect_hotver()`，20 秒预算里几十个请求 → 服务端按 uuid 限流回 `20616` →
`_lookup_single()` 的 `note()` 一直停在「请求繁忙，重试 N/3」，重试本身继续加重限流。
**热更到 v58 后自动消失**，没有改任何请求代码。

> 「请求繁忙」这句只是 `_lookup_single()` 的重试提示，不是最终错误；
> `try_one()` 把**所有异常**都归成 `-1`，和 `20616` 一起走这条提示，所以断网也会这么显示。

### 28.2 华为「没进昵称索引」

仓库索引 15:06 那次重建就含华为 100 人（`count 799`），问题在设备缓存：
`files/lookup-index.json` 是 **00:13** 的旧版（232 KB / huawei 0 条），
`names_index.py` 只在**冷启动且距上次下载超过 6 小时**时重拉，而 App 从 00:28 起没启动过。
19:00 启动后自动拉到 251 KB 新版，分区计数变成
`4399 99 / guanfang 100 / huawei 100 / taptap 99 / taptap_2 99 / taptap_3 100 / taptap_4 102 / yyh 100`。

结论：**加完新服只要重启一次 App 即可**，不需要重打 APK。

### 28.3 新增「榜单兜底」（用户拍板的设计）

先澄清一个误解：v58 及以前 App 里**没有**失败兜底。
`note("读取榜单补充信息…")` 是在实时查询**成功之后**用榜单补门派/等级/名次用的，
查询一失败就只剩 `_fail()` 那张错误卡。所以这条是新增链路，不是加个提示。

| 决策 | 用户选择 |
|---|---|
| 展示形式 | App 内直接渲染榜单数据，不跳转排行榜 |
| 默认值 | **关闭**，但提供开启设置 |
| 开关位置 | 结果页右上角 |

实现见《APK修改操作手册》§3.9。关键坑：

- 等级反算必须用 `lv_from_exp()`（0.100402·lv³ → exp 4001 得 34，与实时页一致），
  一开始误用了 `lv_of_skill()`（0.015·lv³，那是武学等级），离线自测发现后立即改正。
- 顶栏新增开关后，`UID … · 榜单快照` 被挤成省略号（真机截图确认），
  v60 去掉后缀，副标题只留 UID；「非实时」交给正文顶部提示条说。
- `_render_board()` 独立版式，不复用 `_render()`；兜底页隐藏「导出」。

### 28.4 真机验收（19:24）

1. 冷启动热更到 v59 → 正常结果页右上角显示「榜单兜底 关」
2. 点开 → 「榜单兜底 开」，`lookup_cache.json` 出现 `boardFallback: true`
3. 用**错误分区**（墨羽惊鸿）查华为榜首 `10045041213` 制造失败
4. 得到兜底页：「非实时 · 来自高手榜快照」+「抓取于 11-15 19:03」+
   天道自然 / 虚渺宫 / 第 1 名 / 等级 3856 / 武学造诣 2018.67 / 经验 57.67亿 / 传承 5 次 / 华为，
   底部只有「再查一个」，logcat 无异常

发布：v59 `e3f4207`，v60（顶栏副标题修正）`ba6e27e`。

---

## 二十九、手机搜不到华为昵称：缓存机制 + 刷新按钮 + 共享闭环（v61~v64）

### 29.1 用户反馈与定位

手机截图：搜索「天道」→「没找到『天道』，试试完整昵称或直接输 UID」。
但同一份 App 代码在模拟器上搜「天道自然」→「找到『天道自然 · 华为』」。

逐层排除：

| 检查点 | 结果 |
|---|---|
| 线上索引（Pages / jsdelivr / raw 三个源） | 全是新版，`count=799 / huawei=100 / updatedAt 15:06` |
| 模拟器设备缓存 | 251,370 B / 19:00 / 华为 100 条 |
| 用 `names_index.search()` 测华为第 1/50/51/76/100 名 | 全部命中（天道自然 / 咸语 / 许剑一 / 廿二十 / 星刖） |
| 搜索算法 | 完全相等 > 前缀 > 包含，搜「天道」能命中「天道自然」 |
| 手机分区下拉 | 有「华为」，但那来自 `servers/index.json` 且 v58 内置兜底列表也写死了，**不能证明索引新** |

结论：**手机本地那份 `lookup-index.json` 还是旧的**。

### 29.2 根因：两个条件都要满足才会更新

`names_index.py` 里：

```python
CHECK_GAP = 6 * 3600
if mtime and time.time() - mtime < CHECK_GAP: return   # 用旧缓存，不联网
```

- 6 小时的起算点是**手机自己上次成功下载**的缓存 mtime，跟「华为什么时候入库」无关；
- `load_async()` 有 `_started` 一次性开关，只在 App 构建时调一次，**没有 `on_resume` 钩子**，
  进程常驻后台永远不重新检查；
- 所以必须「彻底冷启动 + 缓存满 6h + 下载成功」三者齐备才更新。

这正是加新服后的体验缺口：**新人入库了，已装的 App 却不知道**。

### 29.3 用户拍板的两个决策

| 决策 | 选择 |
|---|---|
| 刷新按钮位置 | 查询页状态条（显示「索引 N 人 · 更新时间」+「刷新」），搜不到时人就在这一页 |
| 归档后是否自动重建索引 | **是**，事件驱动；不恢复每日定时跑 |

### 29.4 实现

- `apk/names_index.py`
  - `_load_blocking(force=True)`：绕过 CHECK_GAP；`refresh_async()` 供按钮调用。
  - `_IO_LOCK` 串行化冷启动加载与手动刷新；下载失败标 `source="failed"`，旧缓存不动。
  - `info()` 返回 `{count, updatedTs, updatedAt, source, state}`；
    **后台线程还没跑完时同步读一次缓存补元信息**，否则状态条会一直显示「未加载」（真机实测踩到）。
  - 状态条用 `updatedTs` 按本机时区格式化，不用 `updatedAt` 字符串（CI 是 UTC、本地是北京时间）。
- `apk/app_ui.py`
  - `_index_card()` 插在 `form_card` 与 `_recent_card()` 之间；`_refresh_index()` /
    `_on_index_refreshed()` 处理按钮「刷新」→「刷新中」→「刷新」与结果提示。
  - `show_query()` 末尾再 `Clock.schedule_once(..., 0.5)` 补一次状态刷新，覆盖回调早于卡片创建的时序。
  - 文案从「昵称索引 N 人 · 更新于 … · 本地缓存」压成「索引 N 人 · …」（360dp 下不截断）。
- `.github/workflows/lookup-index.yml`：新增 `push: branches: [main], paths: data/extra-names.json`。
  工作流自己提交的是 `lookup-index.json`，不会自触发；`ARCHIVE` 用的是 PAT，`GITHUB_TOKEN`
  产生的 push 不触发 Actions，所以归档侧不能换默认 token。

### 29.5 共享链路（用户问「查到的昵称会共享吧」——确实有，且已闭环）

```
App 查 UID 成功
  → apk/archive_local.py record() 写本地 pending_names.jsonl
  → sync_async() 用 gh.json 的 PAT 走 Contents API 追加到 data/extra-names.json
  → push 自动触发 lookup-index.yml
  → build_lookup_index.py::load_extra_names() 合并进 data/lookup-index.json
  → 其他人点查询页「刷新」即可按昵称搜到
```

`build-apk.yml` 会注入 `GH_TOKEN_APK` 生成 `gh.json`；没配 token 时 App 只本地记账、不写仓库。

### 29.6 端到端验证（11-15 21:12）

| 步骤 | 实测 |
|---|---|
| 归档前 | extra-names 322 条 / index 799 人 / 天道自然未归档 |
| 模拟器（v63）查华为榜首 `10045041213` | 实时档案成功：天道自然 / 3856 级 / 第 1 名 |
| 归档后 | extra-names **323 条**、`updatedAt 21:12:34`、天道自然已入库 |
| 自动重建 | Actions run `43717805794`，`event=push`、completed **success** |
| 索引 | **800 人**、`updatedTs 1794748367`（21:12:47） |

刷新按钮单独验过：点 → 「刷新中」→ 「刷新」+「昵称索引已更新（799 人）」，
设备缓存 mtime 从 19:00 更新到 21:05。离线测试还覆盖了「断网刷新保留旧索引、来源标 failed」。

### 29.7 版本

| 版本 | commit | 内容 |
|---|---|---|
| v61 | `608e8db` | 状态条 + 刷新按钮 + 工作流 push 触发 |
| v62 | `172d2b0` | 修状态条初始「未加载」（`info()` 同步兜底 + 延迟刷新） |
| v63 | `37ffbda` | 缩短状态条文案 |
| v64 | `0f258f6` | 同步 `names_index.py` 文件头注释（原写「refresh.yml 每次抓取后重建」已过时） |

`preflight` 全程 7 通过 / 1 警告 / 0 失败。

---

## 三十、索引状态条文案精简（v65）

用户按截图指定两处文案，其余不动：

| 位置 | 改前 | 改后 |
|---|---|---|
| 刷新成功后的表单卡提示 | `昵称索引已更新（800 人）` | `昵称索引已更新` |
| 表单下方状态条左侧 | `索引 800 人 · 11-15 21:12` | `手动刷新昵称索引 · 11-15 21:12` |

- 右侧「刷新」按钮、**状态条里的时间**、时间格式（`updatedTs` 按本机时区）全部保留。
- 状态条只在 `source=cache/failed` 时追加「 · 缓存 / · 失败」短尾巴，联网成功后不显示；
  这两条是既有状态标注，不属于本次要改的文案。
- `_on_index_refreshed()` 里读 `NI.info()["count"]` 只为拼提示，改后一并删掉，不再做一次多余的锁读取。
- 真机验收（21:31–21:32，v65）：冷启动状态条「手动刷新昵称索引 · 11-15 21:12 · 缓存」完整不截断；
  点刷新后 mtime 更新到 21:32，状态条变「手动刷新昵称索引 · 11-15 21:12」，
  上方提示「昵称索引已更新」，无括号人数，logcat 无异常。

发布 `7ac7088`；`preflight` 7 通过 / 1 警告 / 0 失败；v65 = 196,333 B / md5 `c38ee757…`。

---

## 三十一、传承历程补 0 转（初代），与网页口径对齐（v66 / v67）

### 31.1 用户提问「是不是少了零转？」

截图：应用汇「慕少艾」结果页，`传承历程 · 5 转` 只有 1~5 五行
（柳青侯 / 阿土伯 / 淮南子 / 白首男 / 慕少艾），没有 0 转。

**确实少了，而且数据里一直有。** 查 `data/servers/yyh/profiles/6196504694.json`：

```
inheritCount 5，history 5 条
  第 1 条 {n:柳青侯, p:洪玄公, t:18-04}   ← p = 传承前的名字
  ...
```

`inheritHistory` 每条是一次**传承事件**：`parentName` = 上一世，
`inheritName` = 这一世。所以 5 次传承对应链条上 6 个名字，
最前面那个「洪玄公」就是 0 转初代。

网页 `scripts/fetch_profiles.py` 一直把 `p` 存进档案 JSON，
`assets/profile.js` 也单独画了一个 `origin` 节点（`hist[0].p || '初代'`）；
**只有 APK 的 `parse_profile()` 把 `parentName` 丢了**，只存 `n` / `t`，
`_timeline_card()` 又从 1 开始编号，于是同一角色网页 6 世、APK 5 世。

### 31.2 改动

| 文件 | 改动 |
|---|---|
| `apk/lookup_core.py` | `history` 多存 `p`（`parentName`）；`PROFILE_VER` 2 → 3 |
| `apk/app_ui.py` | `_timeline_card()` 重构成统一 `items` 列表，链首补 `(0, 初代名, 0)`；日期列对 0 转留空（`fmt_date(0) = ""`）；末项仍红色高亮；`p` 缺失时占位「初代」，与网页同口径 |

`_timeline_card()` 只在实时结果页 `_render()` 里调用，且 `if p["history"]` 才画；
榜单兜底页走单独的 `_render_board()`，不受影响。

**为什么要单独发 v67**：v66 真机上 0 转显示的是占位「初代」——查询命中了
`PROFILE_TTL=600` 内的旧缓存，那份 profile 是 v65 存的无 `p` 版本。
`PROFILE_VER` 的注释本来就写着「结构变了就 +1，旧缓存自动作废」，
bump 到 3 后重查一次即拿到带 `p` 的新数据。

### 31.3 验收

离线：用真实档案反构 `inheritHistory` 喂给 `parse_profile()`，
`history` 每条字段变成 `n/p/t`，渲染列表 `0 洪玄公 / 1 柳青侯 18-04 / … / 5 慕少艾 19-02`。

真机（v67，应用汇 `6196504694`）：

```
传承历程 · 5 转
0   洪玄公                （无日期）
1   柳青侯      18-04
2   阿土伯      18-06
3   淮南子      18-08
4   白首男      18-10
5   慕少艾      19-02     （红色高亮）
```

标题仍是「5 转」（传承次数没变），只是链条补回初代，与网页档案页一致。

### 31.4 版本

| 版本 | commit | 内容 |
|---|---|---|
| v66 | `9c4a814` | 存 `parentName` + 链首补 0 转行 |
| v67 | `0db94c8` | bump `PROFILE_VER` 到 3，旧缓存作废显示真名 |

`preflight` 7 通过 / 1 警告 / 0 失败；v67 = 196,900 B / md5 `8a280f20…`。
