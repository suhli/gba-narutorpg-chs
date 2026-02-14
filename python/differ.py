#!/usr/bin/env python3
"""Diff two binary files and output differing regions as JSON array."""

import json
from pathlib import Path

import click


def diff_binaries(data_a: bytes, data_b: bytes) -> list[dict]:
    """
    比较两个二进制数据，返回差异列表。
    每个元素: {"pos": "0x1234", "bytes": [u16, ...]}
    pos 为起始位置的十六进制地址，bytes 为该段差异的字节值（以 u16 形式存储 0-255）。
    """
    result = []
    i = 0
    max_len = max(len(data_a), len(data_b))

    while i < max_len:
        byte_a = data_a[i] if i < len(data_a) else None
        byte_b = data_b[i] if i < len(data_b) else None

        if byte_a != byte_b:
            start = i
            bytes_in_run = []
            while i < max_len:
                ba = data_a[i] if i < len(data_a) else None
                bb = data_b[i] if i < len(data_b) else None
                if ba != bb:
                    # 取第一个文件的字节值作为 diff 内容（0-255 用 u16 存）
                    bytes_in_run.append(ba if ba is not None else (bb if bb is not None else 0))
                    i += 1
                else:
                    break
            result.append({
                "pos": f"0x{start:04X}",
                "bytes": bytes_in_run,
            })
        else:
            i += 1

    return result


@click.command()
@click.argument("bin_a", type=click.Path(exists=True, path_type=Path))
@click.argument("bin_b", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--out", "out_path", required=True, type=click.Path(path_type=Path), help="输出 JSON 文件路径")
def main(bin_a: Path, bin_b: Path, out_path: Path) -> None:
    """比较两个二进制文件 BIN_A 与 BIN_B，将差异写入 OUT 指定的 JSON 文件。"""
    data_a = bin_a.read_bytes()
    data_b = bin_b.read_bytes()
    diffs = diff_binaries(data_a, data_b)
    out_path.write_text(json.dumps(diffs, ensure_ascii=False), encoding="utf-8")
    click.echo(f"共 {len(diffs)} 处差异，已写入 {out_path}")


if __name__ == "__main__":
    main()
