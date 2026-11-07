<script setup lang="ts">
/** 轻量图标：单个复合 path，零外部字体/CDN 依赖。 */
import { computed } from 'vue'

const props = defineProps<{ name: string }>()

const shapes: Record<string, string> = {
  home: 'M3 11.2 12 4l9 7.2V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z',
  insights: 'M4 19h16M6 16V10M11 16V5M16 16v-4M20 16V8',
  compare: 'M3.5 5h6v14h-6zM14.5 5h6v14h-6zM3.5 9h6M14.5 9h6',
  chat: 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5',
  history: 'M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9zM12 7v5l3.5 2',
  inventory: 'M4 7 12 3l8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10',
  book: 'M4 4h7a3 3 0 0 1 3 3v13a3 3 0 0 0-3-3H4zM20 4h-3a3 3 0 0 0-3 3v13a3 3 0 0 1 3-3h3z',
  analytics: 'M4 20V5M4 20h16M8 16l4-5 3 2 5-7',
  group: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M17 11a3 3 0 1 0 0-6M18 14c2.2.5 3.5 2.4 3.5 5',
  check: 'M4 6h16v12H4zM7 10l3 3 5-5',
  tune: 'M4 7h10M18 7h2M4 17h2M10 17h10M16 4v6M8 14v6',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5h.01',
  spark: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z',
  logout: 'M10 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h5M14 8l4 4-4 4M18 12H9',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4',
}

const shape = computed(() => shapes[props.name] ?? shapes.info)
</script>

<template>
  <svg
    class="app-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="shape" />
  </svg>
</template>
