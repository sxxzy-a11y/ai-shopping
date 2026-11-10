<script setup lang="ts">
/**
 * 咖啡杯载入动画：DOM 与 CSS 均按 Uiverse.io by esraaabdel-kareem（MIT）原版，
 * 杯子、手柄、三缕烟、点阵的层级关系不改，避免出现烟雾与杯子各跑各的。
 */
withDefaults(defineProps<{ label?: string }>(), {
  label: '正在载入，先喝口咖啡…',
})
</script>

<template>
  <div class="coffee-loader" role="status" :aria-label="label">
    <div class="loader">
      <div class="cup">
        <div class="cup-handle"></div>
        <div class="smoke one"></div>
        <div class="smoke two"></div>
        <div class="smoke three"></div>
      </div>
      <div class="load">..........................</div>
    </div>
    <p class="coffee-label">{{ label }}</p>
  </div>
</template>
