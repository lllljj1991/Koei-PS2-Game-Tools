#!/usr/bin/env python3
"""
TM2 打包脚本 - PNG 转回 TM2（尺寸与调色板数量自动识别）

尺寸：
  0x24-0x25  宽度（小端 uint16）
  0x26-0x27  高度（小端 uint16）

调色板数量：
  PAL_COUNT = (文件大小 - 0x40 - W*H/2) / 64

策略：
  以模板 TM2 的头部和全部调色板为蓝本，仅替换像素数据区。
  如果模板尾部有填充（文件大小与推算结构不整除），填充部分原样保留。
"""

import argparse
import struct
import sys
from PIL import Image

HEADER_SIZE = 0x40
W_OFF = 0x24
H_OFF = 0x26
PAL_ENTRY = 64


# ---------------------------------------------------------------- 布局

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
    """返回 (w, h, pix_off, pix_size, pal_off, pal_count, pal_bytes_end)"""
    w, h = read_size(buf)
    row_bytes = w // 2
    pix_size = row_bytes * h
    pix_off = HEADER_SIZE
    pal_off = pix_off + pix_size
    tail = len(buf) - pal_off
    if tail < PAL_ENTRY:
        raise ValueError(f"文件过小：调色板区仅 {tail} 字节")
    if tail % PAL_ENTRY != 0:
        print(f"警告：调色板区长度 {tail} 不是 {PAL_ENTRY} 的整数倍，"
              f"尾部 {tail % PAL_ENTRY} 字节将作为填充保留", file=sys.stderr)
    pal_count = tail // PAL_ENTRY
    if pal_count % 2 != 0:
        print(f"警告：调色板数量 {pal_count} 为奇数（预期偶数）",
              file=sys.stderr)
    pal_bytes_end = pal_off + pal_count * PAL_ENTRY
    return w, h, pix_off, pix_size, pal_off, pal_count, pal_bytes_end


# ---------------------------------------------------------------- 颜色

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


def color_dist(c1, c2):
    if c1[3] == 0 and c2[3] == 0:
        return 0
    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]
    da = c1[3] - c2[3]
    return dr * dr + dg * dg + db * db + 2 * da * da


def best_index(pixel, palette):
    bi, bd = 0, float("inf")
    for i, c in enumerate(palette):
        d = color_dist(pixel, c)
        if d < bd:
            bd, bi = d, i
            if d == 0:
                break
    return bi, bd


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="PNG 转回 TM2（尺寸与调色板数量自动识别）")
    ap.add_argument("--template", required=True,
                    help="模板 TM2（提供头部和全部调色板）")
    ap.add_argument("--layer-a", required=True, help="A 层 PNG 路径")
    ap.add_argument("--layer-b", required=True, help="B 层 PNG 路径")
    ap.add_argument("-o", "--output", required=True, help="输出 TM2 路径")
    ap.add_argument("--palette-a", type=int, default=0,
                    help="A 层使用的调色板编号（默认 0）")
    ap.add_argument("--palette-b", type=int, default=1,
                    help="B 层使用的调色板编号（默认 1）")
    ap.add_argument("--alpha-max", type=int, default=128,
                    help="alpha 上限：128=TM2标准，255=不缩放")
    ap.add_argument("--threshold", type=float, default=2000.0,
                    help="不匹配阈值（平方距离，默认 2000）")
    ap.add_argument("--strict", action="store_true",
                    help="存在不匹配像素时直接失败")
    args = ap.parse_args()

    tmpl = open(args.template, "rb").read()
    try:
        w, h, pix_off, pix_size, pal_off, pal_count, pal_bytes_end = \
            compute_layout(tmpl)
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

    print(f"模板尺寸：{w}×{h}")
    print(f"像素区：0x{pix_off:X} - 0x{pix_off + pix_size - 1:X}（{pix_size} 字节）")
    print(f"调色板：0x{pal_off:X} 起，共 {pal_count} 张"
          f"（{pal_count * PAL_ENTRY} 字节）")
    if pal_bytes_end < len(tmpl):
        print(f"尾部填充：{len(tmpl) - pal_bytes_end} 字节（原样保留）")

    pal_a = load_pal_a(tmpl, pal_off, args.palette_a, args.alpha_max)
    pal_b = load_pal_b(tmpl, pal_off, args.palette_b, args.alpha_max)

    print(f"A 调色板（模板 palette {args.palette_a} 索引 0-3）：")
    for i, c in enumerate(pal_a):
        print(f"  [{i}] RGBA={c}")
    print(f"B 调色板（模板 palette {args.palette_b} 索引 0/4/8/12）：")
    for i, c in enumerate(pal_b):
        print(f"  [{i}] RGBA={c}")

    img_a = Image.open(args.layer_a).convert("RGBA")
    img_b = Image.open(args.layer_b).convert("RGBA")
    if img_a.size != (w, h) or img_b.size != (w, h):
        print(f"错误：图层尺寸必须是 {w}×{h}，"
              f"实际 A={img_a.size}, B={img_b.size}", file=sys.stderr)
        sys.exit(1)

    pa, pb = img_a.load(), img_b.load()

    out = bytearray(tmpl)  # 保留头部、调色板、尾部填充

    row_bytes = w // 2
    bad_count = 0
    bad_samples = []
    max_d = 0.0

    for y in range(h):
        row_off = HEADER_SIZE + y * row_bytes
        for bx in range(row_bytes):
            x0, x1 = bx * 2, bx * 2 + 1
            a0, d0 = best_index(pa[x0, y], pal_a)
            b0, d1 = best_index(pb[x0, y], pal_b)
            a1, d2 = best_index(pa[x1, y], pal_a)
            b1, d3 = best_index(pb[x1, y], pal_b)

            for d, pt in ((d0, (x0, y)), (d1, (x0, y)),
                          (d2, (x1, y)), (d3, (x1, y))):
                if d > max_d:
                    max_d = d
                if d > args.threshold:
                    bad_count += 1
                    if len(bad_samples) < 10:
                        bad_samples.append((pt, d))

            out[row_off + bx] = a0 | (b0 << 2) | (a1 << 4) | (b1 << 6)

    if bad_count:
        print(f"警告：{bad_count} 个像素无法精确匹配调色板"
              f"（max 平方距离 = {max_d:.0f}）", file=sys.stderr)
        for pt, d in bad_samples:
            print(f"  例：(x={pt[0]}, y={pt[1]}) 平方距离={d:.0f}",
                  file=sys.stderr)
        if args.strict:
            sys.exit(1)
    else:
        print("所有像素均精确匹配调色板 ✓")

    with open(args.output, "wb") as f:
        f.write(out)
    print(f"已生成：{args.output}（{len(out)} 字节）")


if __name__ == "__main__":
    main()