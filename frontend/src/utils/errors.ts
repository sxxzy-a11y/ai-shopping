import { ApiError } from '../api/client'

/**
 * 把未知异常转为用户可读文案。
 *
 * 视图层此前到处写 `err instanceof ApiError ? err.message : '兜底文案'`，
 * 而 API 层、composable、组件抛出的错误类型并不只有 ApiError。这里统一收口，
 * 顺带处理 `message` 为空字符串的情况（不能把空提示渲染出来）。
 */
export function toMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError || err instanceof Error) {
    return err.message.trim() || fallback
  }
  return fallback
}
