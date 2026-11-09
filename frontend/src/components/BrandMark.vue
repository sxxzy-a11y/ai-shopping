<script setup lang="ts">
/**
 * 品牌标记：刻度棱镜（方向 B）。
 *
 * 外圈是一段不闭合的刻度弧——「可测量」；内部一条上升折线穿过弧心，末端一个暖色点——
 * 「把量出来的差异拉成一条可比较的曲线，最后落在一个结论上」。
 * 没有用购物车/灯泡/齿轮/放大镜：那类符号谁都能用，记不住。
 *
 * `tone` 决定底色：浅色页面用深墨圆角块，深色侧栏用镂空描边。
 */
withDefaults(
  defineProps<{
    size?: number
    /** `light` = 用于浅色背景（自带深墨底）；`dark` = 用于深色背景（镂空）。 */
    tone?: 'light' | 'dark'
  }>(),
  { size: 36, tone: 'light' },
)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 40 40"
    fill="none"
    role="img"
    aria-label="智购参谋"
    class="brand-mark"
  >
    <rect v-if="tone === 'light'" width="40" height="40" rx="11" fill="var(--brand-ink, #14242b)" />

    <!-- 刻度弧：开口朝下，读作「量具」而非闭合圆环 -->
    <path
      d="M10.5 27.5A13.5 13.5 0 1 1 29.5 27.5"
      stroke="var(--brand-line, #f2e8d8)"
      stroke-width="2.3"
      stroke-linecap="round"
    />
    <!-- 评分折线：三段上升，末端落点 -->
    <path
      d="M13 26 17 20.2 21 23 26 14.6"
      stroke="var(--brand-accent, #c8763f)"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <circle cx="26" cy="14.6" r="2.4" fill="var(--brand-accent, #c8763f)" />
  </svg>
</template>

<style scoped>
.brand-mark {
  display: block;
  flex: 0 0 auto;
}
</style>
