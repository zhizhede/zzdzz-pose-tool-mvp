<script setup lang="ts">
import { computed, ref } from 'vue'
import { deletePose, filteredPoses, loadPoseObject, newBlankPose, openPose, refreshList, setSourceImage, store } from '../stores/pose'

const emit = defineEmits<{ (e: 'open'): void }>()
const importInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const daeFrame = ref(0)
const list = computed(() => filteredPoses.value)

async function onImportFile(f: File | undefined) {
  if (!f) return
  importing.value = true
  try {
    const body = new FormData()
    body.append('file', f)
    const isDae = f.name.toLowerCase().endsWith('.dae')
    if (isDae) body.append('frame', String(daeFrame.value))
    const r = await fetch('/api/import', { method: 'POST', body })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) {
      alert(`导入失败：${data.detail ?? r.statusText}`)
      return
    }
    if (data.warnings?.length) alert('导入警告：\n' + data.warnings.join('\n'))
    const isImage = /\.(jpe?g|png|webp|bmp)$/i.test(f.name)
    // 图片导入的姿势记住原图：保存后自动作为角色参考图（reference.png）
    setSourceImage(isImage && data.meta?.source_format === 'dwpose-image' ? f : null)
    const base = f.name.replace(/\.(json|dae|jpe?g|png|webp|bmp)$/i, '')
    loadPoseObject(isDae ? `${base}-f${daeFrame.value}` : base, data.pose)
    emit('open')
  } finally {
    importing.value = false
    if (importInput.value) importInput.value.value = ''
  }
}

function onImportDrop(e: DragEvent) {
  e.preventDefault()
  ;(e.currentTarget as HTMLElement).classList.remove('hover')
  onImportFile(e.dataTransfer?.files[0])
}

async function onOpen(name: string) {
  await openPose(name)
}

async function onDelete(name: string) {
  if (!confirm(`确定删除姿态 ${name}？（资产目录将从磁盘移除）`)) return
  await deletePose(name)
}

function previewUrl(name: string): string {
  return `/api/poses/${encodeURIComponent(name)}/preview?ts=${Date.now()}`
}
</script>

<template>
  <div>
    <div style="display: flex; gap: 8px; align-items: center">
      <input v-model="store.filter" type="text" placeholder="搜索名称 / 描述 / 标签…" />
      <button class="ghost" title="刷新列表" @click="refreshList()">↻</button>
    </div>

    <button
      class="ghost dropzone-mini"
      :disabled="importing"
      style="width: 100%; margin-top: 10px"
      title="支持 openpose-editor JSON / COCO 标注 JSON / Mixamo Collada (.dae)"
      @click="importInput?.click()"
      @dragover.prevent="($event.currentTarget as HTMLElement).classList.add('hover')"
      @dragleave.prevent="($event.currentTarget as HTMLElement).classList.remove('hover')"
      @drop="onImportDrop"
    >
      {{ importing ? '导入中…' : '⤓ 导入 JSON / DAE（点击或拖入）' }}
    </button>
    <div style="display: flex; gap: 6px; align-items: center; margin-top: 6px">
      <label style="color: var(--text-dim); font-size: 12px; white-space: nowrap">.dae 帧号</label>
      <input v-model.number="daeFrame" type="number" min="0" style="width: 80px" />
      <span style="color: var(--text-dim); font-size: 11px">仅对 .dae 生效，一帧一个姿势</span>
    </div>
    <input ref="importInput" type="file" accept=".json,.dae,application/json" hidden @change="onImportFile(($event.target as HTMLInputElement).files?.[0])" />

    <div class="poses-list">
      <div
        v-for="p in list"
        :key="p.name"
        class="pose-item"
        :class="{ active: p.name === store.currentName }"
        @click="onOpen(p.name)"
      >
        <img v-if="p.has_preview" class="thumb" :src="previewUrl(p.name)" alt="" />
        <div v-else class="thumb"></div>
        <div style="flex: 1; min-width: 0">
          <div class="name">{{ p.name }}</div>
          <div class="desc">{{ p.description || '（无描述）' }}</div>
          <div style="margin-top: 3px">
            <span v-for="t in p.tags.slice(0, 3)" :key="t" class="tag">{{ t }}</span>
          </div>
        </div>
        <button class="ghost" style="padding: 3px 8px" title="删除" @click.stop="onDelete(p.name)">✕</button>
      </div>
      <div v-if="!list.length" class="notice">库为空或无匹配结果</div>
    </div>

    <button class="ghost" style="width: 100%; margin-top: 12px" @click="newBlankPose()">
      ＋ 新建空白姿态（T-pose）
    </button>
  </div>
</template>
