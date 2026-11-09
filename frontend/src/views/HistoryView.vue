<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import { useConfirm } from '../composables/useConfirm'
import type { DecisionReport, HistoryEntry } from '../api/types'
import { formatDateTime } from '../utils/format'

const entries = ref<HistoryEntry[]>([])
const detail = ref<DecisionReport | null>(null)
const activeId = ref<number | null>(null)
const error = ref('')
const loading = ref(true)
const favorites = ref<{ product_id: string; added_at: string }[]>([])
const productNames = ref<Record<string, string>>({})

async function loadFavorites() {
  try {
    const [favs, products] = await Promise.all([
      api.get<{ items: { product_id: string; added_at: string }[] }>('/favorites'),
      api.get<{ products: { id: string; name: string }[] }>('/products'),
    ])
    favorites.value = favs.items
    productNames.value = Object.fromEntries(products.products.map((p) => [p.id, p.name]))
  } catch (err) {
    // 不能静默清空：那会让「加载失败」显示成「你没有收藏」。
    error.value = err instanceof ApiError ? err.message : '收藏加载失败'
  }
}

async function removeFavorite(productId: string) {
  try {
    await api.delete(`/favorites/${encodeURIComponent(productId)}`)
    favorites.value = favorites.value.filter((f) => f.product_id !== productId)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '取消收藏失败'
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    // 收藏与记录一起加载：先结束 loading 再拉收藏，会让「我的收藏」
    // 先闪一下「还没有收藏」再变成真实数据。
    const [data] = await Promise.all([
      api.get<{ entries: HistoryEntry[] }>('/history'),
      loadFavorites(),
    ])
    entries.value = data.entries
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '历史记录加载失败'
  } finally {
    loading.value = false
  }
}

async function open(id: number) {
  activeId.value = id
  detail.value = null
  const requested = id
  try {
    const report = await api.get<DecisionReport>(`/history/${id}`)
    // 连点不同记录时，慢的旧请求不能覆盖新选中的那条。
    if (activeId.value !== requested) return
    detail.value = report
  } catch (err) {
    if (activeId.value !== requested) return
    error.value = err instanceof ApiError ? err.message : '打开报告失败'
  }
}

let removing = false

async function remove(id: number) {
  if (removing) return
  if (!(await useConfirm().ask(`确定删除记录 #${id} 吗？报告快照将被移除，且不可恢复。`, '删除记录'))) return
  removing = true
  error.value = ''
  try {
    await api.delete(`/history/${id}`)
    if (activeId.value === id) {
      detail.value = null
      activeId.value = null
    }
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  } finally {
    removing = false
  }
}

function exportUrl(id: number, format: 'md' | 'csv') {
  return `/api/history/${id}/export?format=${format}`
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">我的记录</span>
    <h1>历史记录</h1>
    <p>每次分析都会留下一份快照。可以回看当时的需求、筛选依据与结论，或导出报告。</p>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>

  <div class="card">
    <h2>我的分析（{{ entries.length }}）</h2>
    <p v-if="loading" class="loading"><span class="spinner" /> 正在加载…</p>
    <div v-else-if="!entries.length" class="empty">
      <strong>还没有分析记录</strong>
      去「智能分析」跑一次，报告会保存在这里。
    </div>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr><th>时间</th><th>需求摘要</th><th>首选</th><th>结果数</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in entries" :key="e.id" :style="activeId === e.id ? 'background:#fdf3ed' : ''">
            <td class="small">{{ formatDateTime(e.created_at) }}</td>
            <td>{{ e.demand_summary || '—' }}</td>
            <td>{{ e.top_product || '—' }}</td>
            <td>{{ e.result_count }}</td>
            <td>
              <div class="row" style="gap: 6px; flex-wrap: nowrap">
                <button class="btn btn-ghost btn-sm" @click="open(e.id)">查看</button>
                <a class="btn btn-ghost btn-sm" :href="exportUrl(e.id, 'md')">MD</a>
                <a class="btn btn-ghost btn-sm" :href="exportUrl(e.id, 'csv')">CSV</a>
                <button class="btn btn-ghost btn-sm" @click="remove(e.id)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- open() 会先置 activeId 再清空 detail，加载失败时 error 有值：这三个量足以区分详情的三态，无需另加状态。 -->
  <p v-if="activeId !== null && !detail && !error" class="loading">
    <span class="spinner" /> 正在读取报告详情…
  </p>

  <div v-if="detail" class="card">
    <div class="spread" style="margin-bottom: 16px">
      <h2 style="margin: 0">报告详情 #{{ activeId }}</h2>
      <span class="badge accent">{{ detail.recommendations?.length ?? 0 }} 条推荐</span>
    </div>
    <p v-if="detail.demand_summary" class="small muted">需求：{{ detail.demand_summary }}</p>
    <p v-if="detail.conclusion" class="notice info">{{ detail.conclusion }}</p>
    <div class="stack" style="margin-top: 16px">
      <div v-for="(item, i) in detail.recommendations ?? []" :key="i" class="product-row" :class="{ top: i === 0 }">
        <div class="spread">
          <strong>{{ item.name }}</strong>
          <span class="price">{{ item.price_label }}</span>
        </div>
        <span class="small muted">{{ (item.reasons ?? []).join(' · ') }}</span>
      </div>
    </div>
    <ul v-if="detail.to_verify?.length" class="fact-list" style="margin-top: 18px">
      <li v-for="(t, i) in detail.to_verify" :key="i">{{ t }}</li>
    </ul>
  </div>

  <div class="card">
    <h2>我的收藏（{{ favorites.length }}）</h2>
    <div v-if="favorites.length" class="table-wrap">
      <table>
        <thead><tr><th>商品</th><th>商品 ID</th><th>收藏时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="f in favorites" :key="f.product_id">
            <td><strong>{{ productNames[f.product_id] || '（商品已不在库中）' }}</strong></td>
            <td class="small muted">{{ f.product_id }}</td>
            <td class="small">{{ formatDateTime(f.added_at) }}</td>
            <td><button class="btn btn-ghost btn-sm" @click="removeFavorite(f.product_id)">取消收藏</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty"><strong>还没有收藏</strong>在分析结果页点「收藏」即可保存。</div>
  </div>
</template>
