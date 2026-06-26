#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repair_and_extract_msix.py

修复并解压微软商店分发的 MSIX / APPX 安装包。

商店 MSIX 通常基于 ZIP64，但会缺少标准 ZIP 的 End-of-Central-Directory
签名，导致 Windows 资源管理器、PowerShell Expand-Archive、Python zipfile、
甚至部分 7-Zip 版本无法解压。

本脚本提供两种工作模式：
1. 提取模式（默认）：扫描文件中的 local file header，不依赖 central directory
   或 EOCD，直接逐个解压文件。
2. 修复模式（--repair）：在原始文件末尾补写 EOCD / ZIP64 EOCD 记录，生成一个
   标准 ZIP 文件，之后可用任意工具解压。

依赖：Python 3.7+（仅标准库）

    用法示例：
    python repair_and_extract_msix.py OpenAI.Codex_26.623.3763.0_x64__2p2nqsd0c76g0.Msix
    python repair_and_extract_msix.py OpenAI.Codex_26.623.3763.0_x64__2p2nqsd0c76g0.Msix -o "D:\\Apps\\Codex"
    python repair_and_extract_msix.py OpenAI.Codex_26.623.3763.0_x64__2p2nqsd0c76g0.Msix --repair -o fixed.zip
"""

import argparse
import os
import struct
import sys
import zlib
from pathlib import Path

LOCAL_FILE_HEADER = b"PK\x03\x04"
CENTRAL_DIR_HEADER = b"PK\x01\x02"
END_OF_CENTRAL_DIR = b"PK\x05\x06"
ZIP64_END_OF_CENTRAL_DIR = b"PK\x06\x06"
ZIP64_END_OF_CENTRAL_DIR_LOCATOR = b"PK\x06\x07"
DATA_DESCRIPTOR = b"PK\x07\x08"


def _p16(v: int) -> bytes:
    return struct.pack("<H", v)


def _p32(v: int) -> bytes:
    return struct.pack("<I", v)


def _p64(v: int) -> bytes:
    return struct.pack("<Q", v)


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _u64(data: bytes, off: int) -> int:
    return struct.unpack_from("<Q", data, off)[0]


def try_standard_zip(msix_path: str, out_dir: Path) -> bool:
    """先尝试标准 zipfile；如果成功则直接返回 True。"""
    try:
        import zipfile

        with zipfile.ZipFile(msix_path, "r") as zf:
            zf.extractall(out_dir)
        return True
    except Exception as e:
        print(f"[info] 标准 zipfile 失败: {e}")
        return False


def scan_local_file_headers(data: bytes):
    """
    扫描文件中的所有 local file header。
    返回 [(offset, header_info_dict)]。
    """
    entries = []
    pos = 0
    n = len(data)
    while pos < n - 30:
        if data[pos : pos + 4] != LOCAL_FILE_HEADER:
            pos += 1
            continue

        try:
            compression_method = _u16(data, pos + 8)
            compressed_size = _u32(data, pos + 18)
            uncompressed_size = _u32(data, pos + 22)
            name_len = _u16(data, pos + 26)
            extra_len = _u16(data, pos + 28)
            gp_flags = _u16(data, pos + 6)

            # 如果 local header 里的 compressed_size 为 0，说明后面有 data descriptor
            has_data_descriptor = (compressed_size == 0 or uncompressed_size == 0) and (
                gp_flags & 0x08
            )

            name_off = pos + 30
            extra_off = name_off + name_len
            data_off = extra_off + extra_len

            if data_off > n:
                pos += 1
                continue

            name = data[name_off:extra_off].decode("utf-8", errors="replace")

            # 如果文件名以 '/' 结尾，视为目录
            is_dir = name.endswith("/")

            entries.append(
                {
                    "offset": pos,
                    "compression_method": compression_method,
                    "compressed_size": compressed_size,
                    "uncompressed_size": uncompressed_size,
                    "name_len": name_len,
                    "extra_len": extra_len,
                    "data_offset": data_off,
                    "name": name,
                    "has_data_descriptor": has_data_descriptor,
                    "gp_flags": gp_flags,
                    "is_dir": is_dir,
                }
            )

            # 跳到下一个可能的 header（粗略跳过当前文件体）
            # 如果 compressed_size 有效，直接跳到 pos + 30 + name_len + extra_len + compressed_size (+ data descriptor)
            if compressed_size > 0 and not has_data_descriptor:
                next_pos = data_off + compressed_size
            else:
                # 对于 data descriptor 情况，先保守地只前进 1 字节，让后续扫描找到下一个 header
                next_pos = pos + 1
            pos = next_pos
        except Exception:
            pos += 1

    return entries


def find_next_local_header(data: bytes, start: int) -> int:
    """从 start 位置开始查找下一个 local file header 的偏移。"""
    pos = start
    n = len(data)
    while pos < n - 4:
        if data[pos : pos + 4] == LOCAL_FILE_HEADER:
            return pos
        pos += 1
    return -1


def extract_scanning(msix_path: str, out_dir: Path) -> int:
    """扫描 local file header 方式解压，不依赖 EOCD。"""
    with open(msix_path, "rb") as f:
        data = f.read()

    entries = scan_local_file_headers(data)
    if not entries:
        raise RuntimeError("未找到任何 local file header，该文件可能不是 ZIP/MSIX 格式。")

    extracted_count = 0
    skipped_count = 0
    errors = []

    for idx, entry in enumerate(entries):
        name = entry["name"]
        target_path = out_dir / name.replace("/", os.sep)

        if entry["is_dir"]:
            target_path.mkdir(parents=True, exist_ok=True)
            extracted_count += 1
            continue

        # 确定文件体结束位置
        if entry["compressed_size"] > 0 and not entry["has_data_descriptor"]:
            body_end = entry["data_offset"] + entry["compressed_size"]
        else:
            # 需要找到下一个 local header 或 central directory 作为边界
            next_header = find_next_local_header(data, entry["data_offset"] + 1)
            if next_header == -1:
                # 没有下一个 header，尝试用 central directory / EOCD 作为边界
                next_header = data.find(CENTRAL_DIR_HEADER, entry["data_offset"] + 1)
            if next_header == -1:
                next_header = data.find(END_OF_CENTRAL_DIR, entry["data_offset"] + 1)
            if next_header == -1:
                # 没找到边界， conservatively 使用文件末尾
                next_header = len(data)
            body_end = next_header

            if entry["has_data_descriptor"]:
                # 如果后面紧跟 data descriptor，需要跳过它
                dd_pos = body_end - 16  # data descriptor 固定 16 字节（无 signature）或 24 字节（有 signature）
                if dd_pos > entry["data_offset"] and data[dd_pos : dd_pos + 4] == DATA_DESCRIPTOR:
                    body_end = dd_pos
                elif body_end - 12 > entry["data_offset"]:
                    # 尝试无 signature 的 data descriptor
                    pass

        compressed = data[entry["data_offset"] : body_end]

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if entry["compression_method"] == 0:
                # stored
                decompressed = compressed
            elif entry["compression_method"] == 8:
                # deflate (raw)
                decompressed = zlib.decompress(compressed, -15)
            else:
                raise RuntimeError(f"不支持的压缩方法: {entry['compression_method']}")

            with open(target_path, "wb") as out:
                out.write(decompressed)
            extracted_count += 1
        except Exception as e:
            errors.append((name, str(e)))
            skipped_count += 1

    print(f"[ok] 成功提取 {extracted_count} 个条目，跳过 {skipped_count} 个。")
    if errors:
        print(f"[warn] 其中 {len(errors)} 个条目出错：")
        for name, err in errors[:10]:
            print(f"  - {name}: {err}")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors) - 10} 个错误未显示")

    return extracted_count


def find_central_directory(data: bytes) -> int:
    """返回第一个 central directory header 的偏移，找不到返回 -1。"""
    return data.find(CENTRAL_DIR_HEADER)


def repair_zip(msix_path: str, out_path: Path) -> None:
    """
    在原文件基础上补写 EOCD / ZIP64 EOCD 记录，生成标准 ZIP 文件。
    适用于 central directory 存在但 EOCD 缺失的情况。
    """
    with open(msix_path, "rb") as f:
        data = f.read()

    cd_offset = find_central_directory(data)
    if cd_offset == -1:
        raise RuntimeError("未找到 central directory，无法修复为 ZIP。请改用扫描提取模式。")

    cd_size = len(data) - cd_offset
    total_entries = 0
    pos = cd_offset
    while pos < len(data) - 46 and data[pos : pos + 4] == CENTRAL_DIR_HEADER:
        total_entries += 1
        name_len = _u16(data, pos + 28)
        extra_len = _u16(data, pos + 30)
        comment_len = _u16(data, pos + 32)
        pos += 46 + name_len + extra_len + comment_len

    # 追加 ZIP64 EOCD + locator + 传统 EOCD
    zip64_eocd_offset = len(data)
    zip64_eocd = bytearray()
    zip64_eocd += ZIP64_END_OF_CENTRAL_DIR
    zip64_eocd += _p64(44)  # size of zip64 end of central directory record
    zip64_eocd += _p16(45)  # version made by
    zip64_eocd += _p16(45)  # version needed to extract
    zip64_eocd += _p32(0)  # disk number
    zip64_eocd += _p32(0)  # disk number with start of central directory
    zip64_eocd += _p64(total_entries)  # total entries on this disk
    zip64_eocd += _p64(total_entries)  # total entries overall
    zip64_eocd += _p64(cd_size)  # size of central directory
    zip64_eocd += _p64(cd_offset)  # offset of start of central directory

    zip64_locator = bytearray()
    zip64_locator += ZIP64_END_OF_CENTRAL_DIR_LOCATOR
    zip64_locator += _p32(0)  # disk number
    zip64_locator += _p64(zip64_eocd_offset)  # offset of zip64 eocd
    zip64_locator += _p32(1)  # total number of disks

    # 传统 EOCD（用于兼容旧工具，虽然 entries 很多会填 0xFFFF，但这里直接写实际值）
    eocd = bytearray()
    eocd += END_OF_CENTRAL_DIR
    eocd += _p16(0)  # disk number
    eocd += _p16(0)  # disk with start of cd
    eocd += _p16(min(total_entries, 0xFFFF))  # entries on this disk
    eocd += _p16(min(total_entries, 0xFFFF))  # total entries
    eocd += _p32(min(cd_size, 0xFFFFFFFF))  # cd size
    eocd += _p32(min(cd_offset, 0xFFFFFFFF))  # cd offset
    eocd += _p16(0)  # comment length

    with open(out_path, "wb") as f:
        f.write(data)
        f.write(zip64_eocd)
        f.write(zip64_locator)
        f.write(eocd)

    print(f"[ok] 已修复 ZIP 并保存到: {out_path}")
    print(f"     原文件大小: {len(data)} bytes")
    print(f"     修复后大小: {len(data) + len(zip64_eocd) + len(zip64_locator) + len(eocd)} bytes")
    print(f"     条目数: {total_entries}")


def main():
    parser = argparse.ArgumentParser(
        description="修复/提取微软商店分发的 MSIX / APPX 安装包"
    )
    parser.add_argument("msix", help="输入的 .msix / .appx 文件路径")
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="输出目录（提取模式）或输出 zip 路径（修复模式）。默认：当前目录下的 codex-portable 子目录",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="修复模式：生成标准 .zip 文件，而不是直接解压",
    )
    parser.add_argument(
        "--no-zipfile-try",
        action="store_true",
        help="提取模式下跳过标准 zipfile 尝试，直接扫描 local file header",
    )
    args = parser.parse_args()

    msix_path = os.path.abspath(args.msix)
    if not os.path.exists(msix_path):
        print(f"[error] 文件不存在: {msix_path}", file=sys.stderr)
        sys.exit(1)

    if args.repair:
        out_path = args.output
        if not out_path:
            base = Path(msix_path).stem
            out_path = f"{base}.fixed.zip"
        repair_zip(msix_path, Path(out_path))
    else:
        out_dir = args.output
        if not out_dir:
            out_dir = os.path.join(os.path.dirname(msix_path), "codex-portable")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"[info] 输入文件: {msix_path}")
        print(f"[info] 输出目录: {out_dir}")

        if not args.no_zipfile_try and try_standard_zip(msix_path, out_dir):
            print("[ok] 标准 zipfile 提取成功。")
        else:
            print("[info] 使用扫描 local file header 方式提取...")
            extract_scanning(msix_path, out_dir)
            print("[ok] 提取完成。")


if __name__ == "__main__":
    main()
