import { ref } from 'vue'

/**
 * 站内二次确认，替代原生 `confirm()`。
 *
 * 单例状态放在模块级，对话框由 `App.vue` 全局渲染一次；任何视图只需
 * `if (!(await ask('…'))) return`。原生 confirm 会阻塞整个浏览器线程、
 * 样式无法统一，浏览器巡检脚本也难以覆盖。
 */
interface ConfirmRequest {
  message: string
  confirmText: string
  resolve: (confirmed: boolean) => void
}

const current = ref<ConfirmRequest | null>(null)

export function useConfirm() {
  function ask(message: string, confirmText = '确认'): Promise<boolean> {
    // 已有未决请求时先以「取消」收尾，避免旧 Promise 永远悬着。
    current.value?.resolve(false)
    return new Promise<boolean>((resolve) => {
      current.value = { message, confirmText, resolve }
    })
  }

  function settle(confirmed: boolean) {
    const request = current.value
    current.value = null
    request?.resolve(confirmed)
  }

  return { current, ask, settle }
}
