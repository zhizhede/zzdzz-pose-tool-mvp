export type Keypoint = [number, number, number]

export interface Person {
  pose_keypoints_2d: number[]
  hand_left_keypoints_2d?: number[] | null
  hand_right_keypoints_2d?: number[] | null
  face_keypoints_2d?: number[] | null
  /** 人物朝向（3D 导入判定）：front / back / profile；缺省未知 */
  facing?: 'front' | 'back' | 'profile' | null
}

export interface PoseFile {
  version: string
  canvas_width: number
  canvas_height: number
  meta: Record<string, unknown>
  people: Person[]
}

export interface PoseIndexEntry {
  name: string
  path: string
  description: string
  tags: string[]
  canvas: number[]
  people: number
  has_preview: boolean
}

export interface DiffReport {
  moved_keypoints: {
    keypoint: number
    from: number[]
    to: number[]
    dx: number
    dy: number
  }[]
  derived_features: Record<string, { before: number; after: number; delta: number }>
  summary: { moved_count: number; total_keypoints: number }
}

export type AngleMap = Record<string, number | null>
