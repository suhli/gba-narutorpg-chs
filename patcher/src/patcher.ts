/** diff.json 中每一项：在原版 ROM 的 pos（十六进制）处写入 bytes */
export interface DiffItem {
  pos: string
  bytes: number[]
}

/**
 * 纯前端 ROM 打补丁：根据 diff 在原始 ROM 的指定位置写入字节。
 * @param romBuffer 原版 ROM 的 ArrayBuffer
 * @param diff diff.json 数组
 * @returns 打补丁后的 ROM
 */
export function applyDiff(romBuffer: ArrayBuffer, diff: DiffItem[]): Uint8Array {
  const rom = new Uint8Array(romBuffer)
  const out = new Uint8Array(rom)

  for (const item of diff) {
    const pos = parseInt(item.pos, 16)
    const bytes = item.bytes
    if (pos < 0 || pos + bytes.length > out.length) {
      throw new Error(
        `补丁越界: pos=0x${pos.toString(16)}, len=${bytes.length}, romLen=${out.length}`,
      )
    }
    for (let i = 0; i < bytes.length; i++) {
      out[pos + i] = bytes[i]! & 0xff
    }
  }

  return out
}
