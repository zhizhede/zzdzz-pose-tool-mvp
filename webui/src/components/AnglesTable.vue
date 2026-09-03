<script setup lang="ts">
import { computed } from 'vue'
import { computeAngles, JOINT_LABELS } from '../lib/skeleton'
import { store } from '../stores/pose'

const angles = computed(() => (store.current ? computeAngles(store.current) : {}))
</script>

<template>
  <div class="angles-panel">
    <h3>关节角度（实时）</h3>
    <div v-for="(value, name) in angles" :key="name" class="angle-row">
      <span>{{ JOINT_LABELS[name] ?? name }}</span>
      <span class="v">{{ value === null ? '—' : value.toFixed(1) + '°' }}</span>
    </div>
  </div>
</template>
