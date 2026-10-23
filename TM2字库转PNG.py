#!/usr/bin/env python3
"""
TM2 双层 2bpp 解包脚本（尺寸与调色板数量自动识别）

尺寸：
  0x24-0x25  宽度（小端 uint16）
  0x26-0x27  高度（小端 uint16）

布局：
  0x00-0x3F            文件头（64 字节）
  0x40 起              像素数据，长 W*H/2 字节
  像素数据之后         N 个调色板，每个 64 字节（N 为偶数）
  N = (文件大小 - 0x40 - W*H/2) / 64

位布局（每字节覆盖偶/奇 x 两个像素位置）：
  bit7-6  b1  -> 奇数 x 的 B 层索引
  bit5-4  a1  -> 奇数 x 的 A 层索引
  bit3-2  b0  -> 偶数 x 的 B 层索引
  bit1-0  a0  -> 偶数 x 的 A 层索引

调色板：
  A 层：索引 0-3（前 16 字节）
  B 层：索引 0/4/8/12（偏移 0/16/32/48）
  alpha 范围 0-128，可按 --alpha-max 调整

输出：
  默认只输出 <prefix>_a.png 和 <prefix>_b.png
  加 --composite 才会额外输出 <prefix>_composite.png
"""

import argparse
import struct
import sys
from collections import Counter
from PIL import Image

HEADER_SIZE = 0x40
W_OFF = 0x24
H_OFF = 0x26
PAL_ENTRY = 64


def read_size(buf):
    if len(buf) < H_OFF + 2:
        raise ValueError(f"文件过小（{len(buf)} 字节），无法读取尺寸")
    w = struct.unpack_from("<H", buf, W_OFF)[0]
    h = struct.unpack_from("<H", buf, H_OFF)[0]
    if w == 0 or h == 0:
        raise ValueError(f"读到的尺寸为 0：{w}x{h}")
    if w % 2 != 0:
        raise ValueError(f"宽度必须为偶数，读到 {w}")
    return w, h


def compute_layout(buf):
    """返回 (w, h, pix_off, pix_size, pal_off, pal_count)"""
    w, h = read_size(buf)
    row_bytes = w // 2
    pix_size = row_bytes * h
    pix_off = HEADER_SIZE
    pal_off = pix_off + pix_size
    tail = len(buf) - pal_off
    if tail < 0:
        raise ValueError(f"文件过小：像素区需要 {pix_size} 字节，"
                         f"实际剩余 {tail + pix_size}")
    if tail % PAL_ENTRY != 0:
        print(f"警告：调色板区长度 {tail} 不是 {PAL_ENTRY} 的整数倍，"
              f"可能含尾部填充", file=sys.stderr)
    pal_count = tail // PAL_ENTRY
    if pal_count == 0:
        raise ValueError("调色板数量为 0")
    if pal_count % 2 != 0:
        print(f"警告：调色板数量 {pal_count} 为奇数（预期偶数）",
              file=sys.stderr)
    return w, h, pix_off, pix_size, pal_off, pal_count


def scale_alpha(a, alpha_max):
    if alpha_max <= 0:
        return 255
    v = a * 255 // alpha_max
    return 255 if v > 255 else v


def read_color(buf, off, alpha_max):
    r, g, b, a = buf[off:off + 4]
    return (r, g, b, scale_alpha(a, alpha_max))


def load_pal_a(buf, pal_off, pal_index, alpha_max=128):
    base = pal_off + pal_index * PAL_ENTRY
    return [read_color(buf, base + i * 4, alpha_max) for i in range(4)]


def load_pal_b(buf, pal_off, pal_index, alpha_max=128):
    base = pal_off + pal_index * PAL_ENTRY
    return [read_color(buf, base + i * 16, alpha_max) for i in range(4)]


def unpack_byte(byte):
    a0 = byte & 0x03
    b0 = (byte >> 2) & 0x03
    a1 = (byte >> 4) & 0x03
    b1 = (byte >> 6) & 0x03
    return a0, b0, a1, b1


def diagnose(buf, w, h, pix_off, pix_size, pal_off, pal_count):
    row_bytes = w // 2
    pix = buf[pix_off:pix_off + pix_size]
    ca, cb = Counter(), Counter()
    sample_rows = min(h, 8)
    for byte in pix[:row_bytes * sample_rows]:
        a0, b0, a1, b1 = unpack_byte(byte)
        ca[a0] += 1; ca[a1] += 1
        cb[b0] += 1; cb[b1] += 1
    print(f"尺寸：{w}×{h}")
    print(f"像素区：0x{pix_off:X} - 0x{pix_off + pix_size - 1:X}（{pix_size} 字节）")
    print(f"调色板：0x{pal_off:X} 起，共 {pal_count} 张"
          f"（{pal_count * PAL_ENTRY} 字节）")
    print(f"A 层索引分布（前 {sample_rows} 行采样）:", dict(sorted(ca.items())))
    print(f"B 层索引分布（前 {sample_rows} 行采样）:", dict(sorted(cb.items())))
    for p in range(pal_count):
        base = pal_off + p * PAL_ENTRY
        a = [tuple(buf[base + i * 4:base + i * 4 + 4]) for i in range(4)]
        b = [tuple(buf[base + i * 16:base + i * 16 + 4]) for i in range(4)]
        print(f"Palette {p:2d}: A[0-3]={a}  B[0,4,8,12]={b}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--palette-a", type=int, default=0)
    ap.add_argument("--palette-b", type=int, default=1)
    ap.add_argument("--alpha-max", type=int, default=128,
                    help="alpha 上限：128=TM2 标准，255=不缩放，0=忽略alpha")
    ap.add_argument("--flip-y", action="store_true")
    ap.add_argument("--swap", action="store_true")
    ap.add_argument("--out-prefix", default="layer")
    ap.add_argument("--composite", action="store_true",
                    help="额外输出 <prefix>_composite.png（默认不输出）")
    ap.add_argument("--diagnose", action="store_true")
    args = ap.parse_args()

    buf = open(args.input, "rb").read()
    try:
        w, h, pix_off, pix_size, pal_off, pal_count = compute_layout(buf)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

    if not (0 <= args.palette_a < pal_count):
        print(f"错误：--palette-a={args.palette_a} 超出范围 "
              f"(0..{pal_count - 1})", file=sys.stderr)
        sys.exit(1)
    if not (0 <= args.palette_b < pal_count):
        print(f"错误：--palette-b={args.palette_b} 超出范围 "
              f"(0..{pal_count - 1})", file=sys.stderr)
        sys.exit(1)

    if args.diagnose:
        diagnose(buf, w, h, pix_off, pix_size, pal_off, pal_count)

    pal_a = load_pal_a(buf, pal_off, args.palette_a, args.alpha_max)
    pal_b = load_pal_b(buf, pal_off, args.palette_b, args.alpha_max)
    if args.swap:
        pal_a, pal_b = pal_b, pal_a

    row_bytes = w // 2
    pix = buf[pix_off:pix_off + pix_size]
    layer_a = Image.new("RGBA", (w, h))
    layer_b = Image.new("RGBA", (w, h))
    pa = layer_a.load()
    pb = layer_b.load()

    for y in range(h):
        row = pix[y * row_bytes:(y + 1) * row_bytes]
        for bx, byte in enumerate(row):
            a0, b0, a1, b1 = unpack_byte(byte)
            if args.swap:
                a0, b0 = b0, a0
                a1, b1 = b1, a1
            x0 = bx * 2
            pa[x0, y] = pal_a[a0]
            pb[x0, y] = pal_b[b0]
            pa[x0 + 1, y] = pal_a[a1]
            pb[x0 + 1, y] = pal_b[b1]

    if args.flip_y:
        layer_a = layer_a.transpose(Image.FLIP_TOP_BOTTOM)
        layer_b = layer_b.transpose(Image.FLIP_TOP_BOTTOM)

    out_a = f"{args.out_prefix}_a.png"
    out_b = f"{args.out_prefix}_b.png"
    layer_a.save(out_a)
    layer_b.save(out_b)
    outputs = [out_a, out_b]

    if args.composite:
        out_c = f"{args.out_prefix}_composite.png"
        Image.alpha_composite(layer_a, layer_b).save(out_c)
        outputs.append(out_c)

    print(f"尺寸 {w}×{h}，调色板 {pal_count} 张，已生成：")
    for p in outputs:
        print(f"  {p}")


if __name__ == "__main__":
    main()