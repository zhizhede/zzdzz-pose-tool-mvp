<script setup lang="ts">
import { ref } from 'vue'
import PoseCanvas from './PoseCanvas.vue'
import AnglesTable from './AnglesTable.vue'
import { saveAs, saveCurrent, store } from '../stores/pose'

const saving = ref(false)
const message = ref('')
const saveAsName = ref('')
const showSaveAs = ref(false)

async function onSave() {
  saving.value = true
  message.value = (await saveCurrent()) ? '已保存（预览图已同步重渲）' : '保存失败'
  saving.value = false
}

async function onSaveAs() {
  const name = saveAsName.value.trim()
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name)) {
    message.value = '名称只能用小写字母/数字/中划线/下划线'
    return
  }
  saving.value = true
  const ok = await saveAs(name, `由 ${store.currentName} 另存`)
  message.value = ok ? `已另存为 ${name}` : '另存失败（可能重名）'
  saving.value = false
  showSaveAs.value = false
  saveAsName.value = ''
}

async function copyJson() {
  if (!store.current) return
  try {
    await navigator.clipboard.writeText(JSON.stringify(store.current, null, 2))
    message.value = '姿态 JSON 已复制到剪贴板'
  } catch {
    message.value = '复制失败：浏览器拒绝了剪贴板访问'
  }
}

async function downloadPng() {
  if (!store.current) return
  // 走服务端渲染：与 controlnet_aux 训练分布一致的成品图，而不是画布截图
  const r = await fetch('/api/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(store.current),
  })
  if (!r.ok) {
    message.value = '渲染失败'
    return
  }
  const blob = await r.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${store.currentName || 'pose'}.png`
  a.click()
  URL.revokeObjectURL(url)
  message.value = '骨架 PNG 已下载'
}
</script>

<template>
  <div v-if="!store.current" class="notice">
    左侧选择一个姿态，或点「新建空白姿态」开始。
  </div>
  <div v-else>
    <div class="toolbar">
      <strong>{{ store.currentName }}</strong>
      <span v-if="store.dirty" title="有未保存修改"><span class="dirty-dot"></span>未保存</span>
      <span style="flex: 1"></span>
      <button class="ghost" @click="copyJson">复制 JSON</button>
      <button class="ghost" @click="downloadPng">下载 PNG</button>
      <button class="ghost" @click="showSaveAs = !showSaveAs">另存为…</button>
      <button class="primary" :disabled="!store.dirty || saving" @click="onSave">
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </div>

    <div v-if="showSaveAs" class="toolbar">
      <input v-model="saveAsName" type="text" placeholder="新姿态名（如 waving-hand）" style="max-width: 240px" />
      <button class="primary" @click="onSaveAs">确认另存</button>
    </div>

    <div v-if="message" class="notice">{{ message }}</div>

    <div class="editor-layout">
      <PoseCanvas />
      <AnglesTable />
    </div>
  </div>
</template>
