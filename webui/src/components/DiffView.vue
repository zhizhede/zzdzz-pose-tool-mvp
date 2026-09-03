<script setup lang="ts">
import { computed, ref } from 'vue'
import { drawPose, BODY_KEYPOINT_NAMES } from '../lib/skeleton'
import { store } from '../stores/pose'
import type { DiffReport, PoseFile } from '../types'

const nameA = ref(store.currentName || 'looking-down-phone')
const nameB = ref('')
const threshold = ref(2.0)
const busy = ref(false)
const error = ref('')
const report = ref<DiffReport | null>(null)
const poseA = ref<PoseFile | null>(null)
const poseB = ref<PoseFile | null>(null)
const canvasA = ref<HTMLCanvasElement | null>(null)
const canvasB = ref<HTMLCanvasElement | null>(null)

const options = computed(() => store.poses.map((p) => p.name))

const DERIVED_LABELS: Record<string, string> = {
  head_down_ratio: '低头程度（nose 相对 neck 下移量 / 肩宽）',
  torso_tilt_deg: '躯干倾角（度）',
  shoulder_tilt_deg: '肩部倾斜角（度）',
  hands_gap_px: '两手腕间距（px）',
}

async function redrawBoth() {
  if (poseA.value && canvasA.value) drawPose(canvasA.value, poseA.value)
  if (poseB.value && canvasB.value) drawPose(canvasB.value, poseB.value)
}

async function run() {
  busy.value = true
  error.value = ''
  report.value = null
  try {
    const load = async (name: string) => {
      const r = await fetch(`/api/poses/${encodeURIComponent(name)}`)
      if (!r.ok) throw new Error(`加载 ${name} 失败`)
      return ((await r.json()).pose) as PoseFile
    }
    poseA.value = await load(nameA.value)
    poseB.value = await load(nameB.value)
    const r = await fetch('/api/diff', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ a: poseA.value, b: poseB.value, threshold_px: threshold.value }),
    })
    if (!r.ok) throw new Error((await r.json()).detail ?? String(r.status))
    report.value = await r.json()
    await redrawBoth()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <select v-model="nameA" style="max-width: 220px">
        <option v-for="n in options" :key="n" :value="n">{{ n }}</option>
      </select>
      <span>→</span>
      <select v-model="nameB" style="max-width: 220px">
        <option v-for="n in options" :key="n" :value="n">{{ n }}</option>
      </select>
      <label style="display: flex; align-items: center; gap: 6px">
        阈值
        <input v-model.number="threshold" type="number" min="0" step="1" style="width: 70px" /> px
      </label>
      <button class="primary" :disabled="busy || !nameB" @click="run">
        {{ busy ? '计算中…' : '对比' }}
      </button>
    </div>

    <div v-if="error" class="notice warn">{{ error }}</div>

    <div v-if="poseA && poseB" class="diff-grid">
      <div>
        <div class="status-line">A：{{ nameA }}</div>
        <canvas ref="canvasA" width="512" height="512" class="diff-canvas"></canvas>
      </div>
      <div>
        <div class="status-line">B：{{ nameB }}</div>
        <canvas ref="canvasB" width="512" height="512" class="diff-canvas"></canvas>
      </div>
    </div>

    <div v-if="report" class="report">
      <h3 style="margin-top: 0">
        关键点变化：{{ report.summary.moved_count }}/{{ report.summary.total_keypoints }} 个移动
      </h3>
      <table v-if="report.moved_keypoints.length">
        <tr><th>关键点</th><th>变化</th><th>位移</th><th>原坐标</th><th>新坐标</th></tr>
        <tr v-for="m in report.moved_keypoints" :key="m.keypoint">
          <td class="kp-name">{{ BODY_KEYPOINT_NAMES[m.keypoint] }}</td>
          <td>
            {{ m.dy > 0 ? '下移' : m.dy < 0 ? '上移' : '' }}
            {{ Math.abs(m.dy) >= 1e-9 && m.dx !== 0 ? '、' : '' }}
            {{ m.dx > 0 ? '右移' : m.dx < 0 ? '左移' : '' }}
          </td>
          <td>{{ Math.hypot(m.dx, m.dy).toFixed(1) }}px</td>
          <td>({{ m.from[0] }}, {{ m.from[1] }})</td>
          <td>({{ m.to[0] }}, {{ m.to[1] }})</td>
        </tr>
      </table>
      <p v-else>两个姿态在阈值内一致。</p>

      <h3>派生特征</h3>
      <table>
        <tr><th>特征</th><th>A</th><th>B</th><th>Δ</th></tr>
        <tr v-for="(d, key) in report.derived_features" :key="key">
          <td>{{ DERIVED_LABELS[key] ?? key }}</td>
          <td>{{ d.before.toFixed(3) }}</td>
          <td>{{ d.after.toFixed(3) }}</td>
          <td :class="d.delta > 0 ? 'delta-up' : d.delta < 0 ? 'delta-down' : ''">
            {{ d.delta >= 0 ? '+' : '' }}{{ d.delta.toFixed(3) }}
          </td>
        </tr>
      </table>
    </div>
  </div>
</template>
