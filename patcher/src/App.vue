<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { applyDiff, type DiffItem } from './patcher'

const version = import.meta.env.VITE_VERSION ?? ''

const diff = ref<DiffItem[] | null>(null)
const diffError = ref<string | null>(null)
const loading = ref(true)
const selectedFile = ref<File | null>(null)
const patching = ref(false)
const patchError = ref<string | null>(null)

onMounted(async () => {
  try {
    const base = import.meta.env.BASE_URL
    const res = await fetch(`${base.endsWith('/') ? base : base + '/'}diff.json`)
    if (!res.ok) throw new Error(`加载 diff.json 失败: ${res.status}`)
    const data = (await res.json()) as unknown
    if (!Array.isArray(data)) throw new Error('diff.json 格式错误：应为数组')
    diff.value = data as DiffItem[]
  } catch (e) {
    diffError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const f = target.files?.[0]
  selectedFile.value = f ?? null
  patchError.value = null
}

async function runPatch() {
  if (!diff.value || !selectedFile.value) return
  patching.value = true
  patchError.value = null
  try {
    const buffer = await selectedFile.value.arrayBuffer()
    const patched = applyDiff(buffer, diff.value)
    const blob = new Blob([patched], { type: 'application/octet-stream' })
    const name = selectedFile.value.name.replace(/\.[^.]+$/, '') + '_patched.gba'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    patchError.value = e instanceof Error ? e.message : String(e)
  } finally {
    patching.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-zinc-900 text-zinc-100 flex flex-col items-center justify-center p-6">
    <div class="w-full max-w-md rounded-2xl bg-zinc-800/80 border border-zinc-700 shadow-xl p-8">
      <h1 class="text-2xl font-bold text-center mb-2 flex items-center justify-center gap-2">
        <span class="i-mdi-file-document-edit text-amber-400" />
        火影忍者 RPG · 汉化补丁
      </h1>
      <p v-if="version" class="text-zinc-500 text-xs text-center mb-1">
        版本 {{ version }}
      </p>
      <p class="text-zinc-400 text-sm text-center mb-6">
        选择原版 GBA ROM，在浏览器内打补丁并下载，不上传任何文件。
      </p>

      <!-- 加载 diff 状态 -->
      <div v-if="loading" class="flex items-center justify-center gap-2 py-6 text-zinc-400">
        <span class="i-svg-spinners-90-ring-with-bg" />
        正在加载补丁数据…
      </div>
      <div v-else-if="diffError" class="rounded-lg bg-red-500/20 border border-red-500/50 text-red-300 px-4 py-3 mb-6">
        {{ diffError }}
      </div>
      <template v-else>
        <p class="text-zinc-500 text-sm mb-4">
          补丁已就绪，共 {{ diff.length }} 处修改。
        </p>

        <!-- 选择 ROM -->
        <label class="flex flex-col gap-2 mb-4">
          <span class="text-zinc-400 text-sm">选择原版 ROM 文件（.gba）</span>
          <input
            type="file"
            accept=".gba"
            class="block w-full text-sm text-zinc-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-amber-500/20 file:text-amber-300 file:font-medium hover:file:bg-amber-500/30 file:cursor-pointer cursor-pointer"
            @change="onFileChange"
          >
        </label>
        <p v-if="selectedFile" class="text-zinc-400 text-sm mb-4 flex items-center gap-2">
          <span class="i-mdi-file-check text-emerald-400" />
          {{ selectedFile.name }}
        </p>

        <button
          type="button"
          :disabled="!selectedFile || patching"
          class="w-full py-3 px-4 rounded-xl font-medium bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-600 disabled:cursor-not-allowed text-zinc-900 transition-colors flex items-center justify-center gap-2"
          @click="runPatch"
        >
          <span v-if="patching" class="i-svg-spinners-90-ring-with-bg" />
          <span v-else class="i-mdi-download" />
          {{ patching ? '正在打补丁…' : '打补丁并下载' }}
        </button>

        <p v-if="patchError" class="mt-4 rounded-lg bg-red-500/20 border border-red-500/50 text-red-300 px-4 py-3 text-sm">
          {{ patchError }}
        </p>
      </template>
    </div>

    <p class="mt-6 text-zinc-500 text-xs text-center">
      本工具在本地运行，不会上传您的 ROM 文件。
    </p>
  </div>
</template>
