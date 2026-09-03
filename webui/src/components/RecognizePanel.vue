<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { computeAngles, drawPose, JOINT_LABELS } from '../lib/skeleton'
import { loadPoseObject, refreshList, saveAs } from '../stores/pose'
import type { AngleMap, PoseFile } from '../types'

const configured = ref<boolean | null>(null)
const model = ref<string | null>(null)
const busy = ref(false)
const message = ref('')
const swap = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const resultPose = ref<PoseFile | null>(null)
const resultName = ref('')
const previewCanvas = ref<HTMLCanvasElement | null>(null)
const angles = computed<AngleMap>(() => (resultPose.value ? computeAngles(resultPose.value) : {}))

function drawPreview(pose: PoseFile) {
  if (previewCanvas.value) drawPose(previewCanvas.value, pose)
}

watch(resultPose, (p) => { if (p) drawPreview(p) })

onMounted(async () => {
  const r = await fetch('/api/recognize/status')
  const data = await r.json()
  configured.value = data.configured
  model.value = data.model
})

async function onFile(file: File | undefined) {
  if (!file) return
  busy.value = true
  message.value = `正在用 ${model.value ?? '模型'} 分析图片…（可能需要几十秒）`
  try {
    const body = new FormData()
    body.append('image', file)
    if (swap.value) body.append('swap', 'true')
    const r = await fetch('/api/recognize', { method: 'POST', body })
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }))
      throw new Error(err.detail ?? String(r.status))
    }
    const data = await r.json()
    resultPose.value = data.pose
    resultName.value = `recognized-${new Date().toISOString().slice(5, 16).replace(/[-T:]/g, '')}`
    message.value = '识别完成。可拖入编辑器微调后保存入库（识别结果是草稿，请目视核对）'
  } catch (e) {
    message.value = `识别失败：${(e as Error).message}`
  } finally {
    busy.value = false
  }
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  ;(e.currentTarget as HTMLElement).classList.remove('hover')
  onFile(e.dataTransfer?.files[0])
}

function loadIntoEditor() {
  if (!resultPose.value) return
  loadPoseObject(resultName.value || 'recognized', resultPose.value)
}

async function saveToLibrary() {
  if (!resultPose.value) return
  const ok = await saveAs(resultName.value || `recognized-${Date.now()}`, 'AI 识图草稿')
  message.value = ok ? '已保存入库，可在左侧列表找到' : '保存失败'
  if (ok) await refreshList()
}
</script>

<template>
  <div>
    <div v-if="configured === false" class="notice warn">
      识别未配置：请复制 config.example.yaml 为 config.local.yaml 并填入 API 密钥（不会入库）
    </div>
    <div v-else-if="configured" class="notice">
      识别模型：<strong>{{ model }}</strong> · 密钥仅保存在服务端 config.local.yaml
    </div>

    <div
      class="dropzone"
      :class="{ hover: false }"
      @click="fileInput?.click()"
      @dragover.prevent="($event.currentTarget as HTMLElement).classList.add('hover')"
      @dragleave.prevent="($event.currentTarget as HTMLElement).classList.remove('hover')"
      @drop="onDrop"
    >
      {{ busy ? '识别中…' : '点击选择图片，或把图片拖到这里（照片 / 骨架图均可）' }}
    </div>
    <input ref="fileInput" type="file" accept="image/*" hidden @change="onFile(($event.target as HTMLInputElement).files?.[0])" />

    <div class="toolbar" style="margin-top: 10px">
      <label style="display: flex; align-items: center; gap: 6px; cursor: pointer">
        <input v-model="swap" type="checkbox" />
        交换左右（骨架/剪影类图片常需要）
      </label>
      <span style="flex: 1"></span>
      <template v-if="resultPose">
        <input v-model="resultName" type="text" style="max-width: 220px" />
        <button class="ghost" @click="loadIntoEditor">载入编辑器微调</button>
        <button class="primary" @click="saveToLibrary">保存入库</button>
      </template>
    </div>

    <div v-if="message" class="notice">{{ message }}</div>

    <div v-if="resultPose" class="editor-layout">
      <div class="canvas-wrap"><canvas ref="previewCanvas" width="512" height="512" class="diff-canvas"></canvas></div>
      <div class="angles-panel">
        <h3>识别到的关节角度</h3>
        <div v-for="(value, name) in angles" :key="name" class="angle-row">
          <span>{{ JOINT_LABELS[name] ?? name }}</span>
          <span class="v">{{ value === null ? '—' : value.toFixed(1) + '°' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
