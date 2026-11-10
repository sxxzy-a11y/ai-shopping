<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { ComparisonRow, ComparisonTable, ProductList } from '../api/types'
import { useLoadingBar } from '../composables/useLoadingBar'
import { formatPrice } from '../utils/format'

const category = ref('')
const products = ref<ProductList | null>(null)
const selected = ref<string[]>([])
const text = ref('')
const table = ref<ComparisonTable | null>(null)
const error = ref('')
const busy = ref(false)
/** 接口可能百毫秒内返回，加载条至少留 1.5s，让动效看得见；结果不延迟。 */
const { visible: progressVisible } = useLoadingBar(busy)
/** 目录请求是否已结束。没有它，加载失败会永远显示「正在加载商品目录…」。 */
const loaded = ref(false)
/** 与 `config.MAX_COMPARE_COUNT`、README「2–5 件」、Agent 工具校验保持同一口径。 */
const MAX_SELECTED = 5
const onlyDiff = ref(false)

/** 长文本行单独放到下面的分栏里，不挤进参数对照表。 */
const NOTE_LABELS = new Set(['适用场景', '优点', '缺点', '数据来源'])
const COLUMN_COLORS = ['#c8763f', '#3d7f66', '#4c7f9c', '#9a7b33', '#776b94']
const LETTERS = ['A', 'B', 'C', 'D', 'E']

function colColor(index: number): string {
  return COLUMN_COLORS[index % COLUMN_COLORS.length]
}

function isNoteRow(row: ComparisonRow): boolean {
  return NOTE_LABELS.has(row.label) || row.values.some((v) => String(v ?? '').length > 40)
}

const rows = computed<ComparisonRow[]>(() => table.value?.rows ?? [])
const specRows = computed(() => rows.value.filter((row) => !isNoteRow(row)))
const noteRows = computed(() => rows.value.filter(isNoteRow))
const visibleRows = computed(() =>
  onlyDiff.value ? specRows.value.filter((row) => row.varies) : specRows.value,
)
const diffCount = computed(() => specRows.value.filter((row) => row.varies).length)
const missingCount = computed(() =>
  rows.value.reduce((total, row) => total + row.missing.filter(Boolean).length, 0),
)

interface CompareColumn {
  index: number
  letter: string
  name: string
  sub: string
  price: string
  verified: boolean
}

/** 品类中文名沿用 `/products` 返回的字典，不在前端另写一份映射。 */
const categoryLabels = computed<Record<string, string>>(() =>
  Object.fromEntries((products.value?.categories ?? []).map((item) => [item.key, item.label])),
)

const columns = computed<CompareColumn[]>(() => {
  const priceRow = rows.value.find((row) => row.label === '参考价格')
  return (table.value?.products ?? []).map((product, index) => ({
    index,
    letter: LETTERS[index] ?? String(index + 1),
    name: String(product.name || product.id || `商品 ${index + 1}`),
    // 商品名本身通常已含品牌与型号，这里补编号和品类，避免重复
    sub: [product.id, categoryLabels.value[product.category] || product.category]
      .filter(Boolean)
      .join(' · '),
    price: String(priceRow?.values[index] ?? formatPrice(product.price)),
    verified: product.data_status === 'verified',
  }))
})

/** 列宽与滚动宽度同源，避免窄屏把两列压成一团。 */
const gridStyle = computed(
  () => `--cols:${columns.value.length};min-width:${148 + columns.value.length * 210}px`,
)

/** 差异速览：两件时左右对垒，多件时按列平铺；先一眼看清，再看完整参数。 */
const highlights = computed(() =>
  specRows.value
    .filter((row) => row.varies && row.values.every((v) => String(v ?? '').length <= 26))
    .slice(0, columns.value.length === 2 ? 6 : 4)
)

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
  onlyDiff.value = false
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
    <div v-if="progressVisible" class="progress indeterminate" style="margin-top: 16px" role="progressbar" aria-label="正在比较">
      <span></span>
    </div>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>

  <div v-if="table" class="card cmp-result">
    <div class="cmp-result-head">
      <div>
        <h2>比较结果</h2>
        <p class="cmp-result-sub">按商品分栏、逐行对齐；铜橙色底纹标出有差异的项目。缺失数据如实标注，不用其他商品的值补齐。</p>
      </div>
      <div class="cmp-seg" role="group" aria-label="显示范围">
        <button type="button" :class="{ active: !onlyDiff }" @click="onlyDiff = false">
          全部 {{ specRows.length }} 项
        </button>
        <button type="button" :class="{ active: onlyDiff }" @click="onlyDiff = true">
          仅看差异 {{ diffCount }} 项
        </button>
      </div>
    </div>

    <div class="cmp-summary">
      <span class="badge accent">{{ columns.length }} 件商品对照</span>
      <span class="badge">{{ diffCount }} 项参数不同</span>
      <span v-if="missingCount" class="badge amber">{{ missingCount }} 处信息缺失</span>
    </div>

    <div v-if="highlights.length" class="cmp-highlights">
      <div class="cmp-hl-head">
        <span class="eyebrow">关键差异</span>
        <div class="cmp-legend">
          <span v-for="col in columns" :key="col.index">
            <i :style="`background:${colColor(col.index)}`" /> {{ col.letter }} · {{ col.name }}
          </span>
        </div>
      </div>
      <template v-if="columns.length === 2">
        <div v-for="row in highlights" :key="row.label" class="cmp-hl-row">
          <span class="cmp-hl-val left" :class="{ 'is-missing': row.missing[0] }">{{ row.values[0] ?? '—' }}</span>
          <span class="cmp-hl-label">{{ row.label }}</span>
          <span class="cmp-hl-val right" :class="{ 'is-missing': row.missing[1] }">{{ row.values[1] ?? '—' }}</span>
        </div>
      </template>
      <template v-else>
        <div v-for="row in highlights" :key="row.label" class="cmp-hl-multi">
          <span class="cmp-hl-multi-label">{{ row.label }}</span>
          <div class="cmp-hl-multi-values" :style="`--cols:${columns.length}`">
            <div
              v-for="col in columns"
              :key="col.index"
              class="cmp-hl-multi-cell"
              :style="`--col-color:${colColor(col.index)}`"
              :class="{ 'is-missing': row.missing[col.index] }"
            >
              <span class="cmp-hl-multi-letter">{{ col.letter }}</span>
              <span class="cmp-hl-multi-value">{{ row.values[col.index] ?? '—' }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <template v-if="rows.length">
      <div class="cmp-scroll">
        <div class="cmp-grid" :style="gridStyle">
          <div class="cmp-row cmp-head-row">
            <div class="cmp-cell cmp-corner">
              <span class="cmp-corner-label">比较维度</span>
              <span class="cmp-corner-count">{{ visibleRows.length }} 项</span>
            </div>
            <div
              v-for="col in columns"
              :key="col.index"
              class="cmp-cell cmp-product"
              :style="`--col-color:${colColor(col.index)}`"
            >
              <div class="cmp-product-head">
                <span class="cmp-letter">{{ col.letter }}</span>
                <div class="cmp-product-info">
                  <strong class="cmp-product-name">{{ col.name }}</strong>
                  <span class="cmp-product-sub">{{ col.sub }}</span>
                </div>
              </div>
              <div class="cmp-product-price">{{ col.price }}</div>
              <div class="cmp-product-foot">{{ col.verified ? '资料已核验' : '资料待核验' }}</div>
            </div>
          </div>

          <div
            v-for="row in visibleRows"
            :key="row.label"
            class="cmp-row"
            :class="row.varies ? 'differs' : 'same'"
          >
            <div class="cmp-cell cmp-dim">
              <span>{{ row.label }}</span>
              <span v-if="row.varies" class="cmp-diff-tag">不同</span>
            </div>
            <div
              v-for="col in columns"
              :key="col.index"
              class="cmp-cell cmp-value"
              :class="{ 'is-missing': row.missing[col.index] }"
            >
              {{ row.values[col.index] ?? '—' }}
            </div>
          </div>
        </div>

        <div v-if="noteRows.length" class="cmp-notes-grid" :style="gridStyle">
          <div class="cmp-cell cmp-dim cmp-notes-dim">
            <strong>评价与资料</strong>
            <span class="cmp-corner-count">各自独立</span>
          </div>
          <div
            v-for="col in columns"
            :key="col.index"
            class="cmp-cell cmp-notes-cell"
            :style="`--col-color:${colColor(col.index)}`"
          >
            <div class="cmp-notes-col-head">{{ col.letter }} · {{ col.name }}</div>
            <div v-for="row in noteRows" :key="row.label" class="cmp-note-item">
              <span class="cmp-note-label">{{ row.label }}</span>
              <p :class="{ 'is-missing': row.missing[col.index] }">{{ row.values[col.index] ?? '—' }}</p>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!visibleRows.length" class="empty">
        <strong>这些商品的参数完全一致</strong>
        切回「全部」可以看到完整对照。
      </div>
      <p class="cmp-footnote">参数与价格来自本地商品库快照，非实时比价；「参考资料」以商品页与公开资料为准。</p>
    </template>
    <div v-else class="empty">
      <strong>没有可比较的参数</strong>
      这些商品缺少可对齐的核心参数，请换一组商品试试。
    </div>
  </div>
</template>
