<script setup lang="ts">
import { ref } from 'vue'
import PoseLibrary from './components/PoseLibrary.vue'
import EditorPanel from './components/EditorPanel.vue'
import RecognizePanel from './components/RecognizePanel.vue'
import DiffView from './components/DiffView.vue'
import { refreshList } from './stores/pose'

refreshList()

type Tab = 'edit' | 'recognize' | 'diff'
const tab = ref<Tab>('edit')
</script>

<template>
  <div class="app">
    <aside>
      <PoseLibrary @open="tab = 'edit'" />
    </aside>
    <main>
      <nav class="tabs">
        <button :class="{ active: tab === 'edit' }" @click="tab = 'edit'">编辑器</button>
        <button :class="{ active: tab === 'recognize' }" @click="tab = 'recognize'">AI 识图</button>
        <button :class="{ active: tab === 'diff' }" @click="tab = 'diff'">对比</button>
      </nav>
      <div class="content">
        <EditorPanel v-if="tab === 'edit'" />
        <RecognizePanel v-else-if="tab === 'recognize'" />
        <DiffView v-else />
      </div>
    </main>
  </div>
</template>
