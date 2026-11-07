/** 统一 API 客户端：同源 Cookie 会话 + 一致的错误处理。 */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    ...init,
  })

  if (!response.ok) {
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
