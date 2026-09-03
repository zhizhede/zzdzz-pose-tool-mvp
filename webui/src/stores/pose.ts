import { computed, reactive } from 'vue'
import type { Keypoint, PoseFile, PoseIndexEntry } from '../types'
import { blankTPose } from '../lib/skeleton'

interface State {
  poses: PoseIndexEntry[]
  filter: string
  currentName: string
  current: PoseFile | null
  dirty: boolean
  loading: boolean
}

export const store = reactive<State>({
  poses: [],
  filter: '',
  currentName: '',
  current: null,
  dirty: false,
  loading: false,
})

export const filteredPoses = computed(() => {
  const f = store.filter.trim().toLowerCase()
  if (!f) return store.poses
  return store.poses.filter(
    (p) =>
      p.name.toLowerCase().includes(f) ||
      p.description.toLowerCase().includes(f) ||
      p.tags.some((t) => t.toLowerCase().includes(f)),
  )
})

export async function refreshList(): Promise<void> {
  const r = await fetch('/api/poses')
  const data = await r.json()
  store.poses = data.poses
}

export async function openPose(name: string): Promise<void> {
  const r = await fetch(`/api/poses/${encodeURIComponent(name)}`)
  if (!r.ok) return
  const data = await r.json()
  store.currentName = name
  store.current = data.pose
  store.dirty = false
}

export function loadPoseObject(name: string, pose: PoseFile): void {
  store.currentName = name
  store.current = pose
  store.dirty = true
}

export function newBlankPose(): void {
  store.currentName = 'untitled'
  store.current = blankTPose()
  store.dirty = true
}

export function setKeypoint(index: number, x: number, y: number): void {
  const pose = store.current
  if (!pose) return
  const flat = pose.people[0].pose_keypoints_2d
  flat[index * 3] = Math.round(x * 10) / 10
  flat[index * 3 + 1] = Math.round(y * 10) / 10
  if (flat[index * 3 + 2] <= 0) flat[index * 3 + 2] = 0.9
  store.dirty = true
}

export function toggleKeypointVisible(index: number): void {
  const pose = store.current
  if (!pose) return
  const flat = pose.people[0].pose_keypoints_2d
  flat[index * 3 + 2] = flat[index * 3 + 2] > 0 ? 0 : 0.9
  store.dirty = true
}

export async function saveCurrent(): Promise<boolean> {
  const pose = store.current
  if (!pose || !store.currentName) return false
  const r = await fetch(`/api/poses/${encodeURIComponent(store.currentName)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pose }),
  })
  if (!r.ok) return false
  store.dirty = false
  await refreshList()
  return true
}

export async function saveAs(
  name: string,
  description = '',
  pose: PoseFile | null = store.current,
): Promise<boolean> {
  if (!pose) return false
  const r = await fetch('/api/poses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, pose, description }),
  })
  if (!r.ok) return false
  store.currentName = name
  store.dirty = false
  await refreshList()
  return true
}

export async function deletePose(name: string): Promise<boolean> {
  const r = await fetch(`/api/poses/${encodeURIComponent(name)}`, { method: 'DELETE' })
  if (store.currentName === name) { store.current = null; store.currentName = '' }
  await refreshList()
  return r.ok
}

export function keypointsList(pose: PoseFile): Keypoint[] {
  const d = pose.people[0].pose_keypoints_2d
  const out: Keypoint[] = []
  for (let i = 0; i + 2 < d.length; i += 3) out.push([d[i], d[i + 1], d[i + 2]])
  return out
}
