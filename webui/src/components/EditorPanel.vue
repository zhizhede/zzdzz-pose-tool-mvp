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

/** 朝向 → 生成提示词片段：2D 骨架表达不了正/背面，必须靠提示词补 */
function facingPromptFor(pose: PoseFile): { zh: string; prompt: string } {
  const facing = pose.people[0]?.facing
  if (facing === 'front') return { zh: '人物面向镜头', prompt: 'facing the camera, front view' }
  if (facing === 'back') return { zh: '人物背对镜头', prompt: 'viewed from behind, back view' }
  if (facing === 'profile') return { zh: '人物侧对镜头', prompt: 'side view, profile' }
  return { zh: '', prompt: '' }
}

/** 规则式姿态摘要：从角度与关键点布局推导姿势特征，中英双语 */
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

  // 双臂平展检测：双腕接近肩部高度且横向越过肩线
  if (kps.length >= 18) {
    const lSho = kps[5], rSho = kps[2], lWri = kps[7], rWri = kps[4]
    if ([lSho, rSho, lWri, rWri].every((k) => k[2] > 0)) {
      const lSpread = Math.abs(lWri[1] - lSho[1]) < 50 && lWri[0] < lSho[0]
      const rSpread = Math.abs(rWri[1] - rSho[1]) < 50 && rWri[0] > rSho[0]
      if (lSpread && rSpread) {
        parts.push('双臂水平展开')
        partsEn.push('arms spread horizontally')
      }
    }
  }

  // 朝向（3D 导入判定的真值）
  const facingPrompt = facingPromptFor(pose)
  if (facingPrompt.zh) {
    parts.push(facingPrompt.zh)
    partsEn.push(facingPrompt.prompt)
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

/** 生成配合骨架图使用的生图指令（用户需同时附上骨架 PNG） */
async function copyGenInstruction() {
  if (!store.current) return
  const wrapped = withSemanticMeta(store.current)
  const zh = wrapped.meta.auto_description ?? ''
  const en = wrapped.meta.auto_description_en ?? ''
  const facing = facingPromptFor(store.current)
  const facingLine = facing.prompt
    ? `\n朝向要求（骨架图无法表达正/背面，生成时务必在提示词中加上：${facing.prompt}）。\nFacing requirement (add this to the image prompt: ${facing.prompt}).\n`
    : '\n朝向要求：若骨架无法看出正反面，请按场景自行指定朝向提示词（如 facing the camera / viewed from behind）。\n'
  const instruction =
    `请严格按照随附骨架图中的人物姿势，生成一张写实人物全身照。\n` +
    `姿势要求（与骨架图一致）：${zh}\n` +
    `Pose reference (match the attached skeleton exactly): ${en}\n` +
    facingLine +
    `要求：全身可见、姿势与骨架逐关节对应、不要自行改变动作；背景与服装可自由发挥。`
  try {
    await navigator.clipboard.writeText(instruction)
    message.value = '生图指令已复制——下载骨架 PNG 后，把图片和这段指令一起发给生图 AI'
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
      <button class="ghost" title="导出姿态数值，供 openpose-editor / 程序 / 版本管理使用（生图 AI 不直接消费此格式）" @click="copyJson">复制 JSON（程序用）</button>
      <button class="ghost" title="生成配合骨架图使用的生图指令文案：下载骨架 PNG 后，连同这段指令一起发给多模态生图 AI" @click="copyGenInstruction">复制生图指令（配骨架图）</button>
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
