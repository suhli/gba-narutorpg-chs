#!/usr/bin/env python3
"""
将指定目录（此前由 nds_extract.py 解压）打包为 NDS ROM。
从 .env 读取 ndstool 路径（环境变量 ndstool），支持指定输入目录与输出 ROM。

使用：
  python nds_pack.py -o out.nds [extract]
  python nds_pack.py -o ../rom3_rebuild.nds extract/nds_rpg3
"""

import os
import subprocess
import sys
from pathlib import Path

import click

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = PYTHON_DIR.parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PYTHON_DIR / ".env")


def get_ndstool() -> str:
    path = os.environ.get("ndstool") or os.environ.get("NDSTOOL")
    if not path or not Path(path).exists():
        raise SystemExit("未找到 ndstool。请在 .env 中设置 ndstool=路径")
    return path


@click.command(help="将解压目录打包为 NDS ROM")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path), default="extract", required=False)
@click.option("-o", "--output", required=True, help="输出 NDS ROM 文件路径")
@click.option("-v", "--verbose", is_flag=True, help="显示 ndstool 详细信息")
def main(input_dir: Path, output: str, verbose: bool) -> None:
    indir = input_dir.resolve()
    if not indir.is_dir():
        raise SystemExit(f"输入目录不存在: {indir}")

    out_nds = Path(output).resolve()
    out_nds.parent.mkdir(parents=True, exist_ok=True)

    arm9 = indir / "arm9.bin"
    arm7 = indir / "arm7.bin"
    data_dir = indir / "data"
    header = indir / "header.bin"
    banner = indir / "banner.bin"
    y9 = indir / "y9.bin"
    y7 = indir / "y7.bin"
    overlay_dir = indir / "overlay"

    if not arm9.is_file() or not arm7.is_file():
        raise SystemExit("解压目录中缺少 arm9.bin 或 arm7.bin，请先用 nds_extract.py 解压。")
    if not data_dir.is_dir():
        raise SystemExit("解压目录中缺少 data 目录。")

    ndstool = get_ndstool()
    # 全部使用绝对路径，避免 cwd 或相对路径导致 ndstool 找不到文件
    cmd = [
        ndstool,
        "-c", str(out_nds),
        "-9", str(arm9.resolve()),
        "-7", str(arm7.resolve()),
        "-d", str(data_dir.resolve()),
    ]
    if header.is_file():
        cmd.extend(["-h", str(header.resolve())])
    if banner.is_file():
        cmd.extend(["-t", str(banner.resolve())])
    if y9.is_file():
        cmd.extend(["-y9", str(y9.resolve())])
    if y7.is_file():
        cmd.extend(["-y7", str(y7.resolve())])
    if overlay_dir.is_dir():
        cmd.extend(["-y", str(overlay_dir.resolve())])
    if verbose:
        cmd.append("-vv")

    print("执行:", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    print("打包完成:", out_nds)


if __name__ == "__main__":
    main()
