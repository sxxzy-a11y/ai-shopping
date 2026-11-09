import { ref } from 'vue'
import { api } from '../api/client'
import { toMessage } from '../utils/errors'

/**
 * 收藏状态与切换动作。
 *
 * 分析与问答两个视图此前各写一份同样的实现，而且都没有在途保护：
 * 连点两次会发两次请求，并用过期快照回写数组，最终收藏状态可能反掉。
 * 抽到一处后，两页行为一致，也只剩一份要维护。
 */
export function useFavorites() {
  const favorites = ref<string[]>([])
  const pending = ref<string[]>([])
  /** 读取失败不能伪装成「没有收藏」，否则按钮会一直显示「收藏」让人反复点。 */
  const loadError = ref('')

  async function load(): Promise<void> {
    loadError.value = ''
    try {
      const data = await api.get<{ items: { product_id: string }[] }>('/favorites')
      favorites.value = data.items.map((item) => item.product_id)
    } catch (err) {
      loadError.value = toMessage(err, '收藏加载失败')
      favorites.value = []
    }
  }

  async function toggle(productId: string): Promise<void> {
    if (!productId || pending.value.includes(productId)) return
    const wasFavorite = favorites.value.includes(productId)
    pending.value = [...pending.value, productId]
    try {
      if (wasFavorite) await api.delete(`/favorites/${encodeURIComponent(productId)}`)
      else await api.post('/favorites', { product_id: productId })
      favorites.value = wasFavorite
        ? favorites.value.filter((id) => id !== productId)
        : [...favorites.value, productId]
    } finally {
      pending.value = pending.value.filter((id) => id !== productId)
    }
  }

  return { favorites, pending, loadError, load, toggle }
}
