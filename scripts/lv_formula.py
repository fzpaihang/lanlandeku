#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人物等级公式（scripts 侧的单一实现）

游戏里「人物经验 = 0.1 × (人物等级 + 4)³」，也就是 lv 级占据区间
    [0.1*(lv+4)³, 0.1*(lv+5)³)
反算必须落在区间上，不能简单 round / floor 后就算了——立方根有浮点误差，
floor 偶尔会把边界点推低一级，所以这里按候选回代校验。

**为什么单独一个文件**：
  - apk/lookup_core.py 里也有一份（APK 用），但它 import fetch → Crypto，
    CI 里的 merge-exp.yml 只装标准库，不能复用它。
  - scripts/merge_exp.py、build_lookup_index.py、fetch_profiles.py 都要同一口径，
    所以抽成这个零依赖的小模块；scripts/preflight.py 会校验三份实现一致。

改动这个公式时，**四处要一起改**（preflight 会拦）：
  - scripts/lv_formula.py        （本文件）
  - apk/lookup_core.py           （APK 端）
  - worker/src/profile.js        （未上线，仅存档）
  - 文档 docs/网页维护操作手册.md §14.9
"""
LV_BASE = 0.1           # exp = LV_BASE * (lv + LV_OFFSET)³
LV_OFFSET = 4.0


def lv_from_exp(exp):
    """经验 → 人物等级；非法/非正数返回 None。"""
    try:
        exp = float(exp)
    except (TypeError, ValueError):
        return None
    if exp <= 0:
        return None
    guess = int((exp / LV_BASE) ** (1.0 / 3.0) - LV_OFFSET)
    for cand in (guess, guess - 1, guess + 1, guess - 2, guess + 2):
        if cand < 0:
            continue
        lo = LV_BASE * (cand + LV_OFFSET) ** 3
        hi = LV_BASE * (cand + 1 + LV_OFFSET) ** 3
        if lo <= exp < hi:
            return cand
    return max(0, guess)


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        print(arg, "->", lv_from_exp(arg))
