import { ref } from 'vue'

/**
 * 首屏加载态（全局单例）。
 *
 * 放在模块级是为了让 `App.vue` 只需渲染一处进度条，所有页面共用；
 * 用计数器是因为同一屏可能有多个并行请求（概览页一次发 3 个），
 * 先完成的那个不能提前把提示撤掉。
 *
 * **延迟 180ms 才显示**：首屏请求通常在 50–150ms 内回来，立即显示只会闪一下，
 * 反而被感知成「白屏闪烁」。更快的请求完全不显示，慢请求才给反馈。
 */
const loading = ref(false)
let pending = 0
let showTimer: number | undefined

const SHOW_DELAY_MS = 180

function clearTimer() {
  if (showTimer !== undefined) {
    window.clearTimeout(showTimer)
    showTimer = undefined
  }
}

export function useInitialLoad() {
  async function run(task: () => Promise<unknown>): Promise<void> {
    pending += 1
    if (pending === 1) {
      clearTimer()
      showTimer = window.setTimeout(() => {
        showTimer = undefined
        loading.value = true
      }, SHOW_DELAY_MS)
    }
    try {
      await task()
    } finally {
      pending -= 1
      if (pending === 0) {
        clearTimer()
        loading.value = false
      }
    }
  }

  return { loading, run }
}
