#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINKDATA 解包脚本

用法：
    python LINKDATA解包.py 输入文件 输出文件夹

说明：
    输入文件可以是 LINKDATA.BIN 或 LINKDATA.IDX（两者除扩展名外同名），
    脚本会自动查找同目录下同基名的另一个文件作为索引/数据来源。
    IDX 版本（-353 / -354 / -354s360）根据 IDX 文件内容自动识别。
    解包出的文件命名为 <输入文件基名>-1.out, <输入文件基名>-2.out, ..., <输入文件基名>-n.out，
    其中 <输入文件基名> 为输入文件（BIN 或 IDX）去掉扩展名后的部分。
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

BLOCK_SIZE = 0x800
READ_CHUNK_SIZE = 1024 * 1024


def usage() -> None:
    print(
        "用法: python LINKDATA解包.py 输入文件 输出文件夹\n"
        "示例: python LINKDATA解包.py ./LINKDATA.BIN ./unpacked\n"
        "示例: python LINKDATA解包.py ./LINKDATA.IDX ./unpacked"
    )


def parse_args(argv: list[str]) -> tuple[Path, Path]:
    if len(argv) != 2:
        usage()
        raise ValueError("参数数量不正确：需要 2 个参数")
    input_file = Path(argv[0]).expanduser()
    out_dir = Path(argv[1]).expanduser()
    return input_file, out_dir


def _find_sibling(p: Path, *suffixes: str) -> Path:
    stem = p.with_suffix("")
    for suf in suffixes:
        candidate = Path(str(stem) + suf)
        if candidate.exists():
            return candidate
    tried = ", ".join(str(Path(str(stem) + suf)) for suf in suffixes)
    raise ValueError(f"未找到配套文件：{p} -> 尝试过 {tried}")


def resolve_paths(input_arg: Path) -> tuple[Path, Path]:
    if not input_arg.exists():
        raise ValueError(f"输入文件不存在: {input_arg}")
    if not input_arg.is_file():
        raise ValueError(f"输入路径不是文件: {input_arg}")

    suffix = input_arg.suffix.lower()
    if suffix == ".idx":
        idx_path = input_arg
        bin_path = _find_sibling(input_arg, ".BIN", ".bin")
    elif suffix == ".bin":
        bin_path = input_arg
        idx_path = _find_sibling(input_arg, ".IDX", ".idx")
    else:
        bin_path = input_arg
        idx_path = _find_sibling(input_arg, ".IDX", ".idx")

    return bin_path, idx_path


def detect_version(idx_data: bytes) -> tuple[str, str]:
    """
    返回 (版本标识, 字节序符号)。
    版本标识为 "353"、"354" 或 "354s360"；字节序符号为 "<" 或 ">"。
    """
    size = len(idx_data)
    if size < 16:
        raise ValueError("IDX 文件小于 16 字节，不是有效的 IDX 文件")
    if (size - 16) % 16 != 0:
        raise ValueError(
            f"IDX 文件大小 {size} 不是 16 + 16*n 形式，无法解析"
        )

    magic = idx_data[0:4]

    if magic == b"SM4L":
        n_le = struct.unpack("<I", idx_data[4:8])[0]
        n_be = struct.unpack(">I", idx_data[4:8])[0]

        if 16 + 16 * n_le == size and 16 + 16 * n_be != size:
            return "354", "<"
        if 16 + 16 * n_be == size and 16 + 16 * n_le != size:
            return "354s360", ">"
        if 16 + 16 * n_le == size and 16 + 16 * n_be == size:
            return "354", "<"
        raise ValueError(
            f"无法识别 IDX 版本：文件头为 SM4L，但根据文件大小 {size} 计算的"
            f"文件数不匹配（小端序={n_le}，大端序={n_be}）"
        )

    n_le = struct.unpack("<I", idx_data[0:4])[0]
    if 16 + 16 * n_le == size:
        return "353", "<"
    raise ValueError(
        f"无法识别 IDX 版本：文件头不是 SM4L，且根据文件大小 {size} 计算的"
        f"文件数不匹配（小端序文件数={n_le}）"
    )


def parse_idx(
    idx_data: bytes, version: str, endian: str
) -> tuple[int, int, list[tuple[int, int, int]]]:
    """
    解析 IDX 文件。
    返回 (文件数, BIN 总块数, [(start_block, blocks, size), ...])。
    """
    if version == "353":
        file_count = struct.unpack("<I", idx_data[0:4])[0]
        total_blocks = struct.unpack("<I", idx_data[4:8])[0]
    else:
        file_count = struct.unpack(endian + "I", idx_data[4:8])[0]
        total_blocks = struct.unpack(endian + "I", idx_data[8:12])[0]

    entries: list[tuple[int, int, int]] = []
    for i in range(file_count):
        base = 16 + i * 16
        start_block, blocks, size = struct.unpack(
            endian + "III", idx_data[base : base + 12]
        )
        entries.append((start_block, blocks, size))

    return file_count, total_blocks, entries


def extract(
    bin_path: Path,
    idx_path: Path,
    out_dir: Path,
    prefix: str,
) -> tuple[str, int, int]:
    idx_data = idx_path.read_bytes()
    version, endian = detect_version(idx_data)

    file_count, total_blocks, entries = parse_idx(idx_data, version, endian)

    bin_size = bin_path.stat().st_size
    expected_bin_size = total_blocks * BLOCK_SIZE
    if bin_size != expected_bin_size:
        raise ValueError(
            f"BIN 文件大小与 IDX 不一致：IDX 总块数={total_blocks}，"
            f"应为 {expected_bin_size} 字节，实际 {bin_size} 字节"
        )

    for i, (start_block, blocks, size) in enumerate(entries, start=1):
        if blocks * BLOCK_SIZE < size:
            raise ValueError(
                f"第 {i} 项：占位字节数 {blocks * BLOCK_SIZE} 小于文件字节数 {size}"
            )
        end = start_block * BLOCK_SIZE + size
        if end > bin_size:
            raise ValueError(
                f"第 {i} 项：结束位置 {end} 超出 BIN 文件大小 {bin_size}"
            )

    out_dir.mkdir(parents=True, exist_ok=True)

    with bin_path.open("rb") as fbin:
        for i, (start_block, blocks, size) in enumerate(entries, start=1):
            offset = start_block * BLOCK_SIZE
            fbin.seek(offset)

            out_path = out_dir / f"{prefix}-{i}.out"
            with out_path.open("wb") as fout:
                remaining = size
                while remaining > 0:
                    chunk = fbin.read(min(READ_CHUNK_SIZE, remaining))
                    if not chunk:
                        raise IOError(
                            f"读取第 {i} 项时提前结束：offset=0x{offset:X}, "
                            f"size={size}, 剩余={remaining}"
                        )
                    fout.write(chunk)
                    remaining -= len(chunk)

    return version, file_count, total_blocks


def run(argv: list[str]) -> int:
    input_arg, out_dir = parse_args(argv)
    bin_path, idx_path = resolve_paths(input_arg)

    # 输入文件去掉扩展名后的部分作为解包文件名前缀。
    prefix = input_arg.stem

    print(f"BIN: {bin_path}")
    print(f"IDX: {idx_path}")
    print(f"解包文件前缀: {prefix}")

    version, file_count, total_blocks = extract(
        bin_path, idx_path, out_dir, prefix
    )

    version_label = {
        "353": "-353",
        "354": "-354",
        "354s360": "-354s360",
    }[version]

    print(f"识别 IDX 版本: {version_label}")
    print(f"文件数: {file_count}")
    print(f"BIN 总块数: {total_blocks} (0x{total_blocks:X})")
    print(f"输出文件夹: {out_dir}")
    print("解包完成。")

    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())