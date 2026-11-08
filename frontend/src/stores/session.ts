import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { SessionUser } from '../api/types'

export const useSession = defineStore('session', () => {
  const user = ref<SessionUser | null>(null)
  const ready = ref(false)
  const error = ref('')

  async function restore() {
    error.value = ''
    try {
      user.value = await api.get<SessionUser>('/auth/me')
    } catch (err) {
      // 401 是「未登录」的正常路径；其余错误是服务不可用。两种情况都要
      // 结束加载态，否则界面会一直停在「加载中」。
      user.value = null
      if (!(err instanceof ApiError && err.status === 401)) {
        error.value = '服务暂时不可用，请稍后重试'
      }
    } finally {
      ready.value = true
    }
  }

  async function login(username: string, password: string): Promise<boolean> {
    error.value = ''
    try {
      user.value = await api.post<SessionUser>('/auth/login', { username, password })
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : '登录失败'
      return false
    }
  }

  async function logout() {
    try {
      await api.post<{ ok: boolean }>('/auth/logout', {})
    } catch {
      // 退出以本地状态为准：网络失败也必须让人退得出去。
      // 这里不能把异常继续抛给调用方 —— AppShell 里随后还有 `router.replace('/')`，
      // 一旦冒泡就会变成未捕获的 rejection，页面也不会跳转。
    } finally {
      user.value = null
    }
  }

  return { user, ready, error, restore, login, logout }
})
