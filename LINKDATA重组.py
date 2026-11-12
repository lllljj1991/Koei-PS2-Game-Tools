#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINKDATA.BIN / LINKDATA.IDX 重建脚本

用法：
    python LINKDATA重组.py -353 输入文件夹 [输出文件基名]
    python LINKDATA重组.py -354 输入文件夹 [输出文件基名]
    python LINKDATA重组.py -354s360 输入文件夹 [输出文件基名]

说明：
    -353      使用三国无双3版本的 IDX 头（小端序）
    -354      使用三国无双4版本的 IDX 头（小端序）
    -354s360  使用三国无双4版本的 IDX 头，但除文件头前 4 字节外全部使用大端序
    输出文件基名不包含扩展名；省略时默认使用 LINKDATA，并保存到输入文件夹。
    实际输出为：<输出文件基名>.BIN 和 <输出文件基名>.IDX
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

BLOCK_SIZE = 0x800
COPY_CHUNK_SIZE = 1024 * 1024
ZERO_CHUNK_SIZE = 1024 * 1024


def usage() -> None:
    print(
        "用法: python LINKDATA重组.py -353|-354|-354s360 输入文件夹 [输出文件基名]\n"
        "示例: python LINKDATA重组.py -353 ./unpacked\n"
        "示例: python LINKDATA重组.py -354 ./unpacked D:/game/LINKDATA\n"
        "示例: python LINKDATA重组.py -354s360 ./unpacked"
    )


def parse_args(argv: list[str]) -> tuple[str, Path, str | None]:
    if len(argv) < 2 or len(argv) > 3:
        usage()
        raise ValueError("参数数量不正确")

    version_arg = argv[0]
    if version_arg == "-353":
        version = "353"
    elif version_arg == "-354":
        version = "354"
    elif version_arg == "-354s360":
        version = "354s360"
    else:
        usage()
        raise ValueError("IDX 版本必须是 -353、-354 或 -354s360")

    input_dir = Path(argv[1]).expanduser()
    output_arg = argv[2] if len(argv) == 3 else None

    return version, input_dir, output_arg


def collect_out_files(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise ValueError(f"输入文件夹不存在或不是文件夹: {input_dir}")

    by_number: dict[int, Path] = {}
    invalid_names: list[str] = []

    for path in input_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() != ".out":
            continue

        match = re.match(r"^(.*?)(\d+)$", path.stem)
        if not match:
            invalid_names.append(path.name)
            continue

        number = int(match.group(2))
        if number in by_number:
            raise ValueError(
                f"文件编号重复：编号 {number} 同时对应 "
                f"{by_number[number].name} 和 {path.name}"
            )
        by_number[number] = path

    if invalid_names:
        raise ValueError(
            "以下 .out 文件无法从文件名末尾提取编号：\n"
            + "\n".join(f"  {name}" for name in sorted(invalid_names))
        )

    if not by_number:
        raise ValueError(f"输入文件夹中没有找到 .out 文件: {input_dir}")

    numbers = sorted(by_number)
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        missing = sorted(set(expected) - set(numbers))
        extra = sorted(set(numbers) - set(expected))
        message = f"文件编号必须从 1 连续到 n。当前编号: {numbers}"
        if missing:
            message += f"；缺失: {missing}"
        if extra:
            message += f"；超出/不连续: {extra}"
        raise ValueError(message)

    return [by_number[i] for i in expected]


def build_entries(files: list[Path]) -> tuple[list[dict], int, int]:
    entries: list[dict] = []
    offset = 0

    for path in files:
        size = path.stat().st_size
        blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
        padded_size = blocks * BLOCK_SIZE

        entries.append(
            {
                "path": path,
                "size": size,
                "blocks": blocks,
                "padded_size": padded_size,
                "offset": offset,
            }
        )
        offset += padded_size

    total_bytes = offset
    total_blocks = total_bytes // BLOCK_SIZE
    return entries, total_bytes, total_blocks


def check_u32(value: int, name: str) -> int:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{name} 超出 uint32 范围: {value}")
    return value


def resolve_output_base(input_dir: Path, output_arg: str | None) -> Path:
    if output_arg is None:
        return input_dir / "LINKDATA"

    output_path = Path(output_arg).expanduser()

    # 如果只给了文件名、没有目录部分，则默认保存到输入文件夹。
    if output_path.parent == Path(".") and not output_path.is_absolute():
        base = input_dir / output_path.name
    else:
        base = output_path

    if not base.name:
        raise ValueError("输出文件基名不能为空")

    return base


def write_bin(
    entries: list[dict],
    total_bytes: int,
    bin_path: Path,
) -> None:
    bin_path.parent.mkdir(parents=True, exist_ok=True)

    with bin_path.open("wb") as fout:
        for entry in entries:
            source: Path = entry["path"]
            size: int = entry["size"]

            with source.open("rb") as fin:
                remaining = size
                while remaining > 0:
                    chunk = fin.read(min(COPY_CHUNK_SIZE, remaining))
                    if not chunk:
                        raise IOError(f"读取文件时提前结束: {source}")
                    fout.write(chunk)
                    remaining -= len(chunk)

            padding = entry["padded_size"] - entry["size"]
            while padding > 0:
                n = min(padding, ZERO_CHUNK_SIZE)
                fout.write(b"\x00" * n)
                padding -= n

        actual_size = fout.tell()
        if actual_size != total_bytes:
            raise IOError(
                f"BIN 写入大小校验失败：期望 {total_bytes} 字节，实际 {actual_size} 字节"
            )


def write_idx(
    entries: list[dict],
    total_blocks: int,
    version: str,
    idx_path: Path,
) -> None:
    idx_path.parent.mkdir(parents=True, exist_ok=True)

    file_count = len(entries)

    if version == "353":
        endian = "<"
        header = (
            struct.pack(
                endian + "II",
                check_u32(file_count, "文件数"),
                check_u32(total_blocks, "BIN 总块数"),
            )
            + b"\x00" * 8
        )
    elif version == "354":
        endian = "<"
        header = (
            b"SM4L"
            + struct.pack(
                endian + "II",
                check_u32(file_count, "文件数"),
                check_u32(total_blocks, "BIN 总块数"),
            )
            + b"\x00" * 4
        )
    elif version == "354s360":
        # 文件头前 4 字节固定为 SM4L，其余字段使用大端序。
        endian = ">"
        header = (
            b"SM4L"
            + struct.pack(
                endian + "II",
                check_u32(file_count, "文件数"),
                check_u32(total_blocks, "BIN 总块数"),
            )
            + b"\x00" * 4
        )
    else:
        raise ValueError(f"未知 IDX 版本: {version}")

    if len(header) != 16:
        raise AssertionError("IDX 文件头长度不是 16 字节")

    with idx_path.open("wb") as fidx:
        fidx.write(header)

        for entry in entries:
            start_block = entry["offset"] // BLOCK_SIZE
            blocks = entry["padded_size"] // BLOCK_SIZE
            size = entry["size"]

            index_entry = (
                struct.pack(
                    endian + "III",
                    check_u32(start_block, "起始块"),
                    check_u32(blocks, "占位块数"),
                    check_u32(size, "文件字节数"),
                )
                + b"\x00" * 4
            )
            fidx.write(index_entry)


def run(argv: list[str]) -> int:
    version, input_dir, output_arg = parse_args(argv)

    files = collect_out_files(input_dir)
    entries, total_bytes, total_blocks = build_entries(files)

    base = resolve_output_base(input_dir, output_arg)
    bin_path = Path(str(base) + ".BIN")
    idx_path = Path(str(base) + ".IDX")

    write_bin(entries, total_bytes, bin_path)
    write_idx(entries, total_blocks, version, idx_path)

    print(f"完成。IDX 版本: {version}")
    print(f"共处理 {len(entries)} 个 .out 文件。")
    print(f"BIN: {bin_path}")
    print(f"IDX: {idx_path}")
    print(f"BIN 总字节数: {total_bytes} (0x{total_bytes:X})")
    print(f"BIN 总块数: {total_blocks} (0x{total_blocks:X})")

    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())