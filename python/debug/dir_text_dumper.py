"""
在指定目录下所有文件中，按 Shift-JIS 扫描并 dump 所有语句。
语句的 hex 长度必须是 2 的整数倍，否则 trim 掉第一个字节。
输出结构与 text_dumper 一致，每条多一个 file 路径字段。
"""
import json
import os
import re

import click

# --- 配置 ---
MIN_TEXT_LEN = 4
MEANINGFUL_CHAR_PATTERN = re.compile(r'[ぁ-んァ-ヶ\u4E00-\u9FAF\uFF66-\uFF9F]')


def load_binary_charset(bin_path: str) -> set | None:
    """
    解析二进制码表 [u16 key][u16 value]，返回合法字符的 set。
    不在码表内的字符在扫描时会被跳过（断句）。
    """
    if not os.path.exists(bin_path):
        click.echo(f"警告: 找不到码表文件 {bin_path}，将跳过码表过滤。", err=True)
        return None
    valid_chars = set()
    with open(bin_path, "rb") as f:
        data = f.read()
    entry_count = len(data) // 4
    click.echo(f"正在加载码表，共 {entry_count} 个条目...")
    for i in range(entry_count):
        low_byte = data[i * 4]
        high_byte = data[i * 4 + 1]
        sjis_bytes = bytes([high_byte, low_byte])
        try:
            char = sjis_bytes.decode("shift-jis")
            valid_chars.add(char)
        except UnicodeDecodeError:
            pass
    click.echo(f"码表加载完成，有效字符去重后共: {len(valid_chars)} 个")
    return valid_chars


def is_sjis_first_byte(b):
    return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xEF)


def dump_sjis_from_data(data: bytes, file_path: str, charset=None):
    """
    从一段二进制数据中按 Shift-JIS 提取所有语句。
    每条语句的 hex 长度保证为 2 的整数倍（奇数则 trim 第一个字节）。
    每条结果带 file 路径。
    """
    raw_results = []
    offset = 0
    data_len = len(data)

    while offset < data_len:
        chunk_start = offset
        temp_hex = []
        temp_text = ""

        while offset < data_len:
            b1 = int(data[offset])

            # 1. 双字节 SJIS
            if (0x81 <= b1 <= 0x9F) or (0xE0 <= b1 <= 0xEF):
                if offset + 1 < data_len:
                    b2 = int(data[offset + 1])
                    try:
                        char = data[offset:offset+2].decode('shift-jis')
                        if charset is not None and char not in charset:
                            break
                        temp_text += char
                        temp_hex.extend([b1, b2])
                        offset += 2
                        continue
                    except UnicodeDecodeError:
                        break
                else:
                    break

            # 2. 半角区域 (ASCII & 半角片假名)
            elif (0x20 <= b1 <= 0x7E) or (0xA1 <= b1 <= 0xDF):
                try:
                    char = data[offset:offset+1].decode('shift-jis')
                    if charset is not None and b1 > 0x7F:
                        if char not in charset:
                            break
                    temp_text += char
                    temp_hex.append(b1)
                    offset += 1
                    continue
                except Exception:
                    break

            # 3. 非文字，断开
            else:
                break

        # 准入：至少 MIN_TEXT_LEN 字节
        if len(temp_hex) >= MIN_TEXT_LEN:
            meaningful_chars = MEANINGFUL_CHAR_PATTERN.findall(temp_text)
            if len(meaningful_chars) >= 2:
                # 保证 hex 长度为 2 的整数倍：不是则 trim 掉第一个字节
                if len(temp_hex) % 2 != 0:
                    temp_hex = temp_hex[1:]
                    chunk_start += 1
                    try:
                        temp_text = bytes(temp_hex).decode('shift-jis', errors='replace')
                    except Exception:
                        temp_text = "(decode error after trim)"
                if len(temp_hex) < MIN_TEXT_LEN:
                    offset += 1
                    continue
                raw_results.append({
                    "file": file_path,
                    "offset": chunk_start,
                    "length": len(temp_hex),
                    "hex": bytes(temp_hex).hex().upper(),
                    "original": temp_text,
                    "translation": ""
                })

        offset += 1

    return raw_results


def dump_directory(
    root_dir: str,
    output_path: str | None = None,
    charset=None,
    extensions: list[str] | None = None,
    exclude_dirs: set | None = None,
):
    """
    遍历 root_dir 下所有文件，对每个文件做 Shift-JIS dump，汇总结果。
    """
    if exclude_dirs is None:
        exclude_dirs = set()
    root_dir = os.path.abspath(root_dir)
    all_results = []
    files_processed = 0

    for dirpath, _dirnames, filenames in os.walk(root_dir):
        # 可选：跳过某些目录
        rel_dir = os.path.relpath(dirpath, root_dir)
        if rel_dir != "." and any(d in rel_dir for d in exclude_dirs):
            continue
        for name in filenames:
            if extensions and not any(name.lower().endswith(ext) for ext in extensions):
                continue
            file_path = os.path.join(dirpath, name)
            # 相对路径便于阅读
            rel_path = os.path.relpath(file_path, root_dir)
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
            except (OSError, PermissionError) as e:
                print(f"跳过 {rel_path}: {e}")
                continue
            items = dump_sjis_from_data(data, rel_path, charset=charset)
            all_results.extend(items)
            if items:
                files_processed += 1
                print(f"  {rel_path}: {len(items)} 条")

    print(f"共处理 {files_processed} 个含文本的文件，总语句数: {len(all_results)}")

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"已保存到: {output_path}")

    return all_results


@click.command()
@click.argument("dir", type=click.Path(exists=True, file_okay=False, path_type=str), default=".")
@click.option("-o", "--output", type=click.Path(path_type=str), default=None, help="输出 JSON 路径，不指定则只打印统计")
@click.option("--ext", multiple=True, help="只处理这些扩展名的文件，可多次指定，如 --ext .bin --ext .t")
@click.option("--exclude-dir", multiple=True, help="排除路径中包含该字符串的目录，可多次指定")
@click.option("-c", "--charset", type=click.Path(exists=True, dir_okay=False, path_type=str), default=None, help="二进制码表路径 [u16 key][u16 value]，不在码表内的字符会断句跳过")
def main(dir, output, ext, exclude_dir, charset):
    """指定目录下所有文件按 Shift-JIS dump 语句，hex 长度为 2 的整数倍，输出带 file 路径。

    Example:

    \b
      python dir_text_dumper.py
      python dir_text_dumper.py extract/nds_rpg3/data/text -o rpg3/text_dump.json -c extract/nds_rpg3/data/font/font_1x2.tbl
      python dir_text_dumper.py extract/nds_rpg3/overlay -o rpg3/overlay_dump.json -c extract/nds_rpg3/data/font/font_1x2.tbl
      python dir_text_dumper.py extract -o out.json --ext .t --ext .c --charset path/to/charset.bin
      python dir_text_dumper.py . -o out.json --exclude-dir __pycache__
    """
    ext_list = list(ext) if ext else None
    exclude_set = set(exclude_dir) if exclude_dir else None
    charset_set = load_binary_charset(charset) if charset else None
    dump_directory(
        dir,
        output_path=output,
        charset=charset_set,
        extensions=ext_list,
        exclude_dirs=exclude_set,
    )


if __name__ == "__main__":
    main()
