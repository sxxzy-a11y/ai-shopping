/**
 * 展示层格式化工具。
 *
 * 这些逻辑此前散在 4 个视图里各写一份，时间甚至有「到分钟」和「到秒」
 * 两种口径，价格也存在「¥2999」与后端「2999 元」两套写法。集中一处，
 * 改口径时不会再漏改某个页面。
 */

/** 后端 ISO 时间 → 可读文本。空值返回空串，由模板决定占位符。 */
export function formatDateTime(
  value?: string | null,
  options: { seconds?: boolean } = {},
): string {
  if (!value) return ''
  const text = String(value).replace('T', ' ')
  return options.seconds ? text.slice(0, 19) : text.slice(0, 16)
}

/** 价格统一成与后端 `price_label` 一致的「N 元」口径。 */
export function formatPrice(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '价格缺失'
  return `${value} 元`
}

/**
 * 数字输入框 → 数字。
 *
 * 空串与非法输入都返回 `undefined`：`Number('abc')` 会得到 `NaN`，经
 * `JSON.stringify` 变成 `null` 静默提交，看起来像「用户清空了字段」。
 */
export function toNumberOrUndefined(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}
