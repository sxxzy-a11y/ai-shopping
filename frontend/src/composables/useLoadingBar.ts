/** 加载进度条的最短展示时长。

本地接口常在百毫秒内返回，`v-if="busy"` 会让动效一闪而过，等于没加。
这里只延长进度条的「视觉收尾」，不延迟结果数据：busy 结束后结果照常
渲染，进度条多留一会儿，把一轮 expansion 走完再移除。
*/
import { onUnmounted, ref, watch, type Ref } from 'vue'

/** 与 `.progress.indeterminate` / `.route-progress` 的 1.4s 周期对齐。 */
const MIN_VISIBLE_MS = 1500

export function useLoadingBar(busy: Ref<boolean>) {
  const visible = ref(false)
  let timer: number | undefined
  let startedAt = 0

  function start() {
    startedAt = Date.now()
    visible.value = true
    if (timer !== undefined) {
      window.clearTimeout(timer)
      timer = undefined
    }
  }

  function stop() {
    const remaining = Math.max(0, MIN_VISIBLE_MS - (Date.now() - startedAt))
    if (timer !== undefined) window.clearTimeout(timer)
    timer = window.setTimeout(() => {
      visible.value = false
      timer = undefined
    }, remaining)
  }

  watch(busy, (isBusy) => (isBusy ? start() : stop()))

  onUnmounted(() => {
    if (timer !== undefined) window.clearTimeout(timer)
  })

  return { visible }
}
