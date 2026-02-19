#!/usr/bin/env python3
"""
从 NDS ROM 解压所有内容到指定目录。
从 .env 读取 ndstool 路径（环境变量 ndstool），支持指定 ROM 与输出目录。

使用：
  python nds_extract.py [rom.nds] [-o extract]
  python nds_extract.py ../rom3.nds -o extract/nds_rpg3
"""

import os
import subprocess
import sys
from pathlib import Path

import click

# 支持从 python/ 或 项目根 运行
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


@click.command(help="解压 NDS ROM 到指定目录")
@click.argument("rom", type=click.Path(path_type=Path), default="rom.nds", required=False)
@click.option("-o", "--output", default="extract", help="解压输出目录（默认 extract）")
@click.option("-v", "--verbose", is_flag=True, help="显示 ndstool 详细信息")
def main(rom: Path, output: str, verbose: bool) -> None:
    if not rom.is_file():
        raise SystemExit(f"ROM 文件不存在: {rom}")

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    data_dir = out / "data"
    overlay_dir = out / "overlay"
    data_dir.mkdir(exist_ok=True)
    overlay_dir.mkdir(exist_ok=True)

    ndstool = get_ndstool()
    rom_abs = rom.resolve()
    # cwd=out 时，输出路径用相对 out 的路径，ROM 用绝对路径以免相对路径被误解析
    cmd = [
        ndstool,
        "-x", str(rom_abs),
        "-9", "arm9.bin",
        "-7", "arm7.bin",
        "-y9", "y9.bin",
        "-y7", "y7.bin",
        "-d", "data",
        "-y", "overlay",
        "-t", "banner.bin",
        "-h", "header.bin",
    ]
    if verbose:
        cmd.append("-vv")

    print("执行:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=out)
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    print("解压完成:", out.resolve())


if __name__ == "__main__":
    main()
