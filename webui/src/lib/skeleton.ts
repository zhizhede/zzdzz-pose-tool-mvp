// 骨架渲染与几何计算 —— render.py / angles.py 的 TS 移植
// LIMB_SEQ / LIMB_COLORS 与 controlnet_aux.util.draw_bodypose 一致，保证所见即喂给 ControlNet 的
import type { Keypoint, Person, PoseFile, AngleMap } from '../types'

export const N_BODY_KEYPOINTS = 18

export const BODY_KEYPOINT_NAMES = [
  'nose', 'neck', 'right_shoulder', 'right_elbow', 'right_wrist',
  'left_shoulder', 'left_elbow', 'left_wrist', 'right_hip', 'right_knee',
  'right_ankle', 'left_hip', 'left_knee', 'left_ankle', 'right_eye',
  'left_eye', 'right_ear', 'left_ear',
]

// 1 起始下标
export const LIMB_SEQ: [number, number][] = [
  [2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10],
  [10, 11], [2, 12], [12, 13], [13, 14], [2, 16], [16, 17], [17, 18],
  [2, 15], [15, 14],
]

export const LIMB_COLORS: [number, number, number][] = [
  [255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0],
  [85, 255, 0], [0, 255, 0], [0, 255, 85], [0, 255, 170], [0, 255, 255],
  [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], [170, 0, 255],
  [255, 0, 255], [255, 0, 170], [255, 0, 85],
]

const STICK_WIDTH = 4
const KEYPOINT_RADIUS = 4

export function keypointsOf(person: Person): Keypoint[] {
  const d = person.pose_keypoints_2d
  const out: Keypoint[] = []
  for (let i = 0; i + 2 < d.length; i += 3) out.push([d[i], d[i + 1], d[i + 2]])
  return out
}

/** conf<=0 的关键点没有真实坐标，编辑时停靠在画布底部一排 */
export function displayPos(pose: PoseFile, k: Keypoint, index: number): [number, number] {
  if (k[2] > 0) return [k[0], k[1]]
  const n = N_BODY_KEYPOINTS
  const slot = index % n
  const x = 24 + slot * ((pose.canvas_width - 48) / (n - 1))
  return [x, pose.canvas_height - 14]
}

export function drawPose(
  canvas: HTMLCanvasElement,
  pose: PoseFile,
  opts: { grid?: boolean; active?: number | null; hover?: number | null } = {},
): void {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const W = pose.canvas_width
  const H = pose.canvas_height
  canvas.width = W
  canvas.height = H
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, W, H)

  if (opts.grid) {
    ctx.strokeStyle = '#151515'
    ctx.lineWidth = 1
    for (let x = 32; x < W; x += 32) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke() }
    for (let y = 32; y < H; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke() }
  }

  const person = pose.people[0]
  const kps = keypointsOf(person)

  ctx.lineCap = 'round'
  LIMB_SEQ.forEach(([a, b], i) => {
    const ka = kps[a - 1]
    const kb = kps[b - 1]
    if (ka[2] <= 0 || kb[2] <= 0) return
    ctx.strokeStyle = `rgb(${LIMB_COLORS[i].join(',')})`
    ctx.lineWidth = STICK_WIDTH
    ctx.beginPath()
    ctx.moveTo(ka[0], ka[1])
    ctx.lineTo(kb[0], kb[1])
    ctx.stroke()
  })

  kps.forEach((k, j) => {
    const [x, y] = displayPos(pose, k, j)
    const [r, g, b] = LIMB_COLORS[j]
    const isActive = opts.active === j
    const isHover = opts.hover === j
    if (k[2] <= 0) {
      // 停靠区：空心圆
      ctx.strokeStyle = `rgba(${r},${g},${b},0.6)`
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(x, y, KEYPOINT_RADIUS, 0, Math.PI * 2)
      ctx.stroke()
      return
    }
    ctx.fillStyle = `rgb(${r},${g},${b})`
    ctx.beginPath()
    ctx.arc(x, y, KEYPOINT_RADIUS + (isHover ? 2 : 0), 0, Math.PI * 2)
    ctx.fill()
    if (isActive || isHover) {
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(x, y, KEYPOINT_RADIUS + 4, 0, Math.PI * 2)
      ctx.stroke()
    }
  })
}

/** 命中检测：返回画布内最近的可见关键点下标，或停靠区的隐藏点下标 */
export function pickKeypoint(
  pose: PoseFile,
  px: number,
  py: number,
  radius = 12,
): number | null {
  const person = pose.people[0]
  const kps = keypointsOf(person)
  let best: number | null = null
  let bestDist = radius
  kps.forEach((k, j) => {
    const [x, y] = displayPos(pose, k, j)
    const d = Math.hypot(k[2] > 0 ? px - x : px - x, py - y)
    if (d <= bestDist) { best = j; bestDist = d }
  })
  return best
}

// ---- 角度计算（angles.py 移植） ----

const JOINTS: Record<string, [number, number, number]> = {
  right_elbow: [2, 3, 4],
  left_elbow: [5, 6, 7],
  right_shoulder: [8, 2, 3],
  left_shoulder: [11, 5, 6],
  right_hip: [2, 8, 9],
  left_hip: [5, 11, 12],
  right_knee: [8, 9, 10],
  left_knee: [11, 12, 13],
}

export const JOINT_LABELS: Record<string, string> = {
  right_elbow: '右肘', left_elbow: '左肘',
  right_shoulder: '右肩', left_shoulder: '左肩',
  right_hip: '右髋', left_hip: '左髋',
  right_knee: '右膝', left_knee: '左膝',
  head_tilt_deg: '头部倾斜',
}

function angleDeg(ax: number, ay: number, bx: number, by: number, cx: number, cy: number): number {
  const v1x = ax - bx, v1y = ay - by
  const v2x = cx - bx, v2y = cy - by
  const n1 = Math.hypot(v1x, v1y)
  const n2 = Math.hypot(v2x, v2y)
  if (n1 === 0 || n2 === 0) return NaN
  const cos = Math.max(-1, Math.min(1, (v1x * v2x + v1y * v2y) / (n1 * n2)))
  return (Math.acos(cos) * 180) / Math.PI
}

export function computeAngles(pose: PoseFile, personIndex = 0): AngleMap {
  const person = pose.people[personIndex]
  if (!person) return {}
  const kps = keypointsOf(person)
  const out: AngleMap = {}
  for (const [name, [i, j, k]] of Object.entries(JOINTS)) {
    const a = kps[i], b = kps[j], c = kps[k]
    if (a[2] <= 0 || b[2] <= 0 || c[2] <= 0) { out[name] = null; continue }
    out[name] = Math.round(angleDeg(a[0], a[1], b[0], b[1], c[0], c[1]) * 10) / 10
  }
  const nose = kps[0], neck = kps[1]
  out.head_tilt_deg = nose[2] > 0 && neck[2] > 0
    ? Math.round(angleDeg(nose[0], nose[1] - 100, neck[0], neck[1], nose[0], nose[1]) * 10) / 10
    : null
  return out
}

/** 空白 T-pose 模板 */
export function blankTPose(w = 512, h = 512): PoseFile {
  const cx = w / 2
  const c: [number, number] = [cx, 0]
  const pts: [number, number][] = [
    [cx, 90], [cx, 200], [cx + 100, 200], [cx + 180, 200], [cx + 250, 200],
    [cx - 100, 200], [cx - 180, 200], [cx - 250, 200],
    [cx + 60, 320], [cx + 60, 400], [cx + 60, 480],
    [cx - 60, 320], [cx - 60, 400], [cx - 60, 480],
    [cx - 12, 80], [cx + 12, 80], [cx + 24, 92], [cx - 24, 92],
  ]
  const flat: number[] = []
  for (const [x, y] of pts) flat.push(Math.round(x * 10) / 10, Math.round(y * 10) / 10, 0.9)
  void c
  return { version: '0.2', canvas_width: w, canvas_height: h, meta: {}, people: [{ pose_keypoints_2d: flat }] }
}
