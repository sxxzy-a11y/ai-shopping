<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { api, ApiError } from '../api/client'
import type { ComparisonTable, ProductList } from '../api/types'
import { formatPrice } from '../utils/format'

const category = ref('')
const products = ref<ProductList | null>(null)
const selected = ref<string[]>([])
const text = ref('')
const table = ref<ComparisonTable | null>(null)
const error = ref('')
const busy = ref(false)
/** 目录请求是否已结束。没有它，加载失败会永远显示「正在加载商品目录…」。 */
const loaded = ref(false)
/** 与 `config.MAX_COMPARE_COUNT`、README「2–5 件」、Agent 工具校验保持同一口径。 */
const MAX_SELECTED = 5

const rows = computed(() => table.value?.rows ?? [])

onMounted(async () => {
  try {
    products.value = await api.get<ProductList>('/products')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '商品目录加载失败'
  } finally {
    loaded.value = true
  }
})

function toggle(id: string) {
  const index = selected.value.indexOf(id)
  if (index >= 0) selected.value.splice(index, 1)
  else if (selected.value.length < MAX_SELECTED) selected.value.push(id)
  else error.value = `最多只能选择 ${MAX_SELECTED} 件商品`
}

async function run() {
  if (busy.value) return
  error.value = ''
  table.value = null
  busy.value = true
  try {
    table.value = await api.post<ComparisonTable>('/compare', {
      product_ids: selected.value,
      text: text.value,
    })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '比较失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">商品比较</span>
    <h1>商品比较</h1>
    <p>选择至少 2 件商品，把参数和使用场景并排摊开。可附加需求文本，让差异标注更贴合你的用途。</p>
  </div>

  <div class="card">
    <div class="row" style="margin-bottom: 16px">
      <div class="field" style="margin: 0; min-width: 180px">
        <label for="cat">按品类筛选</label>
        <select id="cat" v-model="category" class="select">
          <option value="">全部品类</option>
          <option v-for="c in products?.categories ?? []" :key="c.key" :value="c.key">{{ c.label }}</option>
        </select>
      </div>
      <span class="badge">已选 {{ selected.length }} / {{ MAX_SELECTED }}</span>
    </div>

    <div class="check-grid">
      <label
        v-for="p in (products?.products ?? []).filter(
          (x) => x.is_active !== false && (!category || x.category === category),
        )"
        :key="p.id"
        class="check-item"
        :class="{ selected: selected.includes(p.id) }"
      >
        <input type="checkbox" :checked="selected.includes(p.id)" @change="toggle(p.id)" />
        <span>
          <strong>{{ p.name }}</strong><br />
          <span class="small muted">{{ p.brand }} · {{ formatPrice(p.price) }}</span>
        </span>
      </label>
    </div>
    <p v-if="!loaded" class="loading"><span class="spinner" /> 正在加载商品目录…</p>
    <p v-else-if="!products" class="small muted">商品目录加载失败，请查看下方错误提示后刷新页面。</p>

    <div class="field" style="margin-top: 18px">
      <label for="cmp-text">需求文本（可选）</label>
      <input id="cmp-text" v-model="text" class="input" placeholder="例如：主要写代码，看重便携和续航" />
    </div>
    <button class="btn btn-primary" :disabled="busy || selected.length < 2" @click="run">
      <span v-if="busy" class="spinner" /> {{ busy ? '正在比较…' : '开始比较' }}
    </button>
    <span v-if="selected.length < 2" class="small muted" style="margin-left: 12px">还需选择 {{ 2 - selected.length }} 件</span>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>

  <div v-if="table" class="card">
    <h2>比较结果</h2>
    <div v-if="rows.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th v-for="key in Object.keys(rows[0])" :key="key">{{ key }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td v-for="key in Object.keys(row)" :key="key">{{ String(row[key] ?? '—') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty">
      <strong>没有可比较的参数</strong>
      这些商品缺少可对齐的核心参数，请换一组商品试试。
    </div>
  </div>
</template>
