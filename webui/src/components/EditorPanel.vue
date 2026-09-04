<script setup lang="ts">
import { ref } from 'vue'
import PoseCanvas from './PoseCanvas.vue'
import AnglesTable from './AnglesTable.vue'
import { BODY_KEYPOINT_NAMES, computeAngles, keypointsOf } from '../lib/skeleton'
import { saveAs, saveCurrent, store } from '../stores/pose'
import type { PoseFile } from '../types'

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
    // 带语义包装：关键点名称映射 + 规则式姿态摘要，
    // 让 LLM/程序拿到的不只是裸数字（生图模型仍只认骨架 PNG）
    const wrapped = withSemanticMeta(store.current)
    await navigator.clipboard.writeText(JSON.stringify(wrapped, null, 2))
    message.value = '姿态 JSON（含关键点名称与姿态摘要）已复制到剪贴板'
  } catch {
    message.value = '复制失败：浏览器拒绝了剪贴板访问'
  }
}

/** 规则式姿态摘要：从角度特征推导姿势类型，中英双语 */
function withSemanticMeta(pose: PoseFile): PoseFile {
  const angles = computeAngles(pose)
  const kps = keypointsOf(pose.people[0])
  const visible = kps.filter((k) => k[2] > 0).length
  const parts: string[] = []
  const partsEn: string[] = []

  const tilt = angles.torso_tilt_deg ?? 0
  if (tilt < 30) { parts.push('躯干直立'); partsEn.push('upright torso') }
  else if (tilt < 60) { parts.push('躯干前倾'); partsEn.push('leaning torso') }
  else { parts.push('躯干接近水平（躺/卧姿态）'); partsEn.push('torso near horizontal (lying)') }

  const kneeL = angles.left_knee_deg ?? 180, kneeR = angles.right_knee_deg ?? 180
  if (kneeL < 120 || kneeR < 120) {
    parts.push(`屈膝（左 ${kneeL.toFixed(0)}° / 右 ${kneeR.toFixed(0)}°）`)
    partsEn.push(`bent knees (L ${kneeL.toFixed(0)}° / R ${kneeR.toFixed(0)}°)`)
  }
  const hipL = angles.left_hip_deg ?? 180, hipR = angles.right_hip_deg ?? 180
  if (hipL < 100 && hipR < 100) {
    parts.push('双髋屈曲（坐姿/蹲姿特征）')
    partsEn.push('hips flexed (sitting/crouching)')
  }
  const wL = angles.left_elbow_deg ?? 180, wR = angles.right_elbow_deg ?? 180
  if (wL < 120 || wR < 120) {
    parts.push('手臂弯曲')
    partsEn.push('arms bent')
  }

  const desc =
    `结构化姿态数据：OpenPose COCO-18 关键点，共 ${visible}/18 可见，单位像素，画布 ${pose.canvas_width}×${pose.canvas_height}。` +
    `自动姿势判定：${parts.join('，') || '无显著特征'}。` +
    `注意：此数据供 openpose-editor / ControlNet 渲染使用，生图请配合骨架图。`

  const descEn = `Structured pose data: OpenPose COCO-18 keypoints (${visible}/18 visible), canvas ${pose.canvas_width}×${pose.canvas_height}. ` +
    `Auto-detected pose: ${partsEn.join(', ') || 'no strong features'}.`

  return {
    ...pose,
    meta: {
      ...pose.meta,
      keypoint_names: BODY_KEYPOINT_NAMES,
      auto_description: desc,
      auto_description_en: descEn,
    },
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
      <button class="ghost" title="导出姿态数值，供 openpose-editor / 程序 / 版本管理使用（生图 AI 不直接消费此格式）" @click="copyJson">复制 JSON（程序用）</button>
      <button class="ghost" title="渲染骨架图并下载——这才是喂给 ControlNet 的控制信号" @click="downloadPng">下载骨架 PNG（喂 ControlNet）</button>
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
