/** 统一 API 客户端：同源 Cookie 会话 + 一致的错误处理。 */

/**
 * 会话失效事件。任何业务请求拿到 401 时派发，由 `App.vue` 统一清登录态并回登录页。
 * 用事件而不是在客户端里直接 import Pinia store：`session.ts` 已经依赖本模块，
 * 反向 import 会形成循环依赖。
 */
export const UNAUTHORIZED_EVENT = 'zhigou:unauthorized'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  // headers 用 Headers 合并、放在 `...init` 之后：先前写成
  // `{ ...init }` 收尾，任何调用方传入 headers 都会把默认 Content-Type 整块覆盖掉。
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    ...init,
    headers,
  })

  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/me') {
      // 会话过期（30 分钟空闲 / 12 小时绝对）后，业务请求会 401。
      // 不通知应用层的话，页面仍显示已登录，用户点任何按钮都只得到错误提示，
      // 必须手动刷新浏览器才能回到登录页。
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    let message = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      const detail = body?.detail
      if (typeof detail === 'string') message = detail
      else if (Array.isArray(detail)) message = detail.map((d) => d?.msg ?? '').join('；') || message
    } catch {
      // 响应不是 JSON，保留状态码文案
    }
    throw new ApiError(response.status, message)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
