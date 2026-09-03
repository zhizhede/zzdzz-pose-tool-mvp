<script setup lang="ts">
import { computed } from 'vue'
import { deletePose, filteredPoses, newBlankPose, openPose, refreshList, store } from '../stores/pose'

defineEmits<{ (e: 'open'): void }>()

const list = computed(() => filteredPoses.value)

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
