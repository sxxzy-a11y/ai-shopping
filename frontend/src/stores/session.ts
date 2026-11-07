import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { SessionUser } from '../api/types'

export const useSession = defineStore('session', () => {
  const user = ref<SessionUser | null>(null)
  const ready = ref(false)
  const error = ref('')

  async function restore() {
    try {
      user.value = await api.get<SessionUser>('/auth/me')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) user.value = null
      else error.value = '服务暂时不可用，请稍后重试'
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
    } finally {
      user.value = null
    }
  }

  return { user, ready, error, restore, login, logout }
})
