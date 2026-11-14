# -*- coding: utf-8 -*-
"""Ed25519 签名 / 验签（纯 Python，只依赖 hashlib）。

为什么自己写：
  热更新通道是「下载一段 Python 代码并执行」，只靠 md5 和同一个通道取回的
  version.json 做校验，等于没有校验——能劫持 TLS 的人也能同时改 md5。
  机器上既没有 cryptography 也没有 nacl，p4a 环境更不会有，所以用纯 Python
  实现（校验用，一次启动约几十毫秒，可以接受）。

实现按 RFC 8032，点用扩展坐标（x, y, z, t）。对外只暴露三个函数：
  public_key(seed)  -> 32 字节公钥
  sign(seed, msg)   -> 64 字节签名
  verify(pk, msg, sig) -> bool
"""

import hashlib

_B = 256
_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _sha512(data):
    return hashlib.sha512(data).digest()


def _inv(x):
    return pow(x, _Q - 2, _Q)


_D = (-121665 * _inv(121666)) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = (4 * _inv(5)) % _Q
_BX = _xrecover(_BY)
_BASE = (_BX % _Q, _BY % _Q, 1, (_BX * _BY) % _Q)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _Q
    b = (y1 + x1) * (y2 + x2) % _Q
    c = t1 * 2 * _D * t2 % _Q
    dd = z1 * 2 * z2 % _Q
    e = b - a
    f = dd - c
    g = dd + c
    h = b + a
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _mul(p, e):
    """标量乘（迭代版双倍-加），避免 252 层递归。"""
    result = (0, 1, 1, 0)
    while e > 0:
        if e & 1:
            result = _add(result, p)
        p = _add(p, p)
        e >>= 1
    return result


def _encode_point(p):
    x, y, z, _t = p
    zi = _inv(z)
    x = x * zi % _Q
    y = y * zi % _Q
    bits = [(y >> i) & 1 for i in range(_B - 1)] + [x & 1]
    n = 0
    for i in range(_B):
        n |= bits[i] << i
    return n.to_bytes(32, "little")


def _decode_point(s):
    if len(s) != 32:
        raise ValueError("point must be 32 bytes")
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    if y >= _Q:
        raise ValueError("bad point")
    x = _xrecover(y)
    if x & 1 != (s[31] >> 7) & 1:
        x = _Q - x
    p = (x, y, 1, x * y % _Q)
    if _encode_point(p) != s:
        raise ValueError("point not on curve")
    return p


def _hint(seed):
    h = _sha512(seed)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    """由 32 字节私钥种子导出公钥。"""
    a, _prefix = _hint(seed)
    return _encode_point(_mul(_BASE, a))


def sign(seed, msg):
    """用 32 字节私钥种子对 msg 签名，返回 64 字节签名。"""
    a, prefix = _hint(seed)
    pk = _encode_point(_mul(_BASE, a))
    r = int.from_bytes(_sha512(prefix + msg), "little") % _L
    r_point = _encode_point(_mul(_BASE, r))
    k = int.from_bytes(_sha512(r_point + pk + msg), "little") % _L
    s = (r + k * a) % _L
    return r_point + s.to_bytes(32, "little")


def verify(pk, msg, sig):
    """校验签名。任何异常都按「验签失败」处理，调用方只看布尔值。"""
    try:
        if len(pk) != 32 or len(sig) != 64:
            return False
        r_point = _decode_point(sig[:32])
        a_point = _decode_point(pk)
        s = int.from_bytes(sig[32:], "little")
        if s >= _L:
            return False
        k = int.from_bytes(_sha512(sig[:32] + pk + msg), "little") % _L
        # 校验 S*B == R + k*A
        left = _mul(_BASE, s)
        right = _add(r_point, _mul(a_point, k))
        return _encode_point(left) == _encode_point(right)
    except Exception:
        return False
