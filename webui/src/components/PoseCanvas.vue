<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { drawPose, pickKeypoint, BODY_KEYPOINT_NAMES } from '../lib/skeleton'
import { setKeypoint, store, toggleKeypointVisible } from '../stores/pose'

const canvasRef = ref<HTMLCanvasElement | null>(null)
const grid = ref(true)
const dragIndex = ref<number | null>(null)
const hoverIndex = ref<number | null>(null)
const status = ref('')

function redraw() {
  if (!canvasRef.value || !store.current) return
  drawPose(canvasRef.value, store.current, {
    grid: grid.value,
    active: dragIndex.value,
    hover: hoverIndex.value,
  })
}

watch(() => store.current, redraw, { deep: true })
watch(grid, redraw)
onMounted(redraw)

function toCanvasCoords(e: { clientX: number; clientY: number }): [number, number] {
  const canvas = canvasRef.value!
  const rect = canvas.getBoundingClientRect()
  const x = ((e.clientX - rect.left) * canvas.width) / rect.width
  const y = ((e.clientY - rect.top) * canvas.height) / rect.height
  return [x, y]
}

function onPointerDown(e: PointerEvent) {
  if (!store.current || !canvasRef.value) return
  const [x, y] = toCanvasCoords(e)
  const idx = pickKeypoint(store.current, x, y)
  if (idx === null) return
  dragIndex.value = idx
  canvasRef.value.setPointerCapture(e.pointerId)
  updateStatus(idx)
}

function onPointerMove(e: PointerEvent) {
  if (!store.current || !canvasRef.value) return
  const [x, y] = toCanvasCoords(e)
  if (dragIndex.value !== null) {
    const pose = store.current
    const cx = Math.max(0, Math.min(pose.canvas_width - 1, x))
    const cy = Math.max(0, Math.min(pose.canvas_height - 1, y))
    setKeypoint(dragIndex.value, cx, cy)
    updateStatus(dragIndex.value)
  } else {
    const idx = pickKeypoint(store.current, x, y)
    if (idx !== hoverIndex.value) { hoverIndex.value = idx; redraw() }
    if (idx !== null) updateStatus(idx)
    else status.value = ''
  }
}

function onPointerUp() {
  dragIndex.value = null
}

function onDblClick(e: MouseEvent) {
  if (!store.current) return
  const [x, y] = toCanvasCoords(e)
  const idx = pickKeypoint(store.current, x, y)
  if (idx !== null) { toggleKeypointVisible(idx); redraw() }
}

function updateStatus(idx: number) {
  const pose = store.current
  if (!pose) return
  const d = pose.people[0].pose_keypoints_2d
  const name = BODY_KEYPOINT_NAMES[idx] ?? String(idx)
  const conf = d[idx * 3 + 2]
  status.value = conf > 0
    ? `${name}  (${d[idx * 3].toFixed(1)}, ${d[idx * 3 + 1].toFixed(1)})`
    : `${name}  隐藏（拖入画布即启用，双击切换可见性）`
}
</script>

<template>
  <div class="canvas-wrap">
    <canvas
      ref="canvasRef"
      width="512"
      height="512"
      style="cursor: crosshair; touch-action: none"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @dblclick="onDblClick"
    ></canvas>
    <div class="status-line">{{ status || '拖拽圆点调整关键点；底部一排空心圆是隐藏关键点，拖入画布即启用' }}</div>
  </div>
</template>
