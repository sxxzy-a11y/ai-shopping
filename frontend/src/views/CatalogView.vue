<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { Category, Product } from '../api/types'
import { formatPrice } from '../utils/format'

/**
 * 管理端商品行。
 *
 * 这些字段此前在本文件里重新声明了一遍，与 `api/types.ts` 的 `Product`
 * 严重重复且已经开始漂移（缺 `entered_by` 等）。统一用公共类型，保留别名
 * 以免模板大改。
 */
type ProductRow = Product

interface CategoryMeta {
  key: string
  label: string
  display_label: string
  sort_order: number
  is_active: boolean
  custom_label: boolean
  product_count: number
  brands: string[]
}
interface BrandMeta {
  brand_name: string
  display_name: string
  sort_order: number
  is_active: boolean
  product_count: number
  categories: string[]
}

const tab = ref<'products' | 'meta'>('products')
const items = ref<ProductRow[]>([])
const meta = ref<{ categories: CategoryMeta[]; brands: BrandMeta[] } | null>(null)
const categories = ref<Category[]>([])
const expandedCategory = ref('')
const selectedBrand = ref('')
const brandForm = reactive({ brand_name: '', display_name: '', sort_order: 0, is_active: true })

const unassignedBrands = computed(() =>
  (meta.value?.brands ?? []).filter((b) => !b.categories?.length),
)

function brandDisplayName(name: string): string {
  return meta.value?.brands.find((b) => b.brand_name === name)?.display_name || name
}

function selectBrand(name: string) {
  if (selectedBrand.value === name) {
    selectedBrand.value = ''
    return
  }
  const row = meta.value?.brands.find((b) => b.brand_name === name)
  selectedBrand.value = name
  Object.assign(brandForm, {
    brand_name: name,
    display_name: row?.display_name ?? name,
    sort_order: row?.sort_order ?? 0,
    is_active: row?.is_active ?? true,
  })
}
const error = ref('')
const notice = ref('')
const busy = ref(false)
/** 区分「正在加载」「加载失败」「确实为空」三态。 */
const loaded = ref(false)
const showForm = ref(false)
const editing = ref(false)

const form = reactive({
  id: '', name: '', brand: '', category: '', model: '', price: '',
  specs: '', use_cases: '', pros: '', cons: '', image_url: '', source_url: '',
})

const verified = computed(() => items.value.filter((p) => p.data_status === 'verified').length)
const activeCount = computed(() => items.value.filter((p) => p.is_active !== false).length)

// 商品清单按中文品类大类分组；表里不再重复显示品类列。
const collapsedGroups = ref<string[]>([])
const groupedProducts = computed(() => {
  const groups = categories.value
    .map((c) => ({
      key: c.key,
      label: c.label,
      items: items.value.filter((p) => p.category === c.key),
    }))
    .filter((g) => g.items.length > 0)
  const known = new Set(categories.value.map((c) => c.key))
  const rest = items.value.filter((p) => !known.has(p.category))
  if (rest.length) groups.push({ key: '__other__', label: '其他', items: rest })
  return groups
})
const allCollapsed = computed(
  () => groupedProducts.value.length > 0 && collapsedGroups.value.length === groupedProducts.value.length,
)

function activeIn(group: { items: ProductRow[] }): number {
  return group.items.filter((p) => p.is_active !== false).length
}

function toggleGroup(key: string) {
  collapsedGroups.value = collapsedGroups.value.includes(key)
    ? collapsedGroups.value.filter((k) => k !== key)
    : [...collapsedGroups.value, key]
}

function toggleAllGroups() {
  collapsedGroups.value = allCollapsed.value ? [] : groupedProducts.value.map((g) => g.key)
}

function lines(values: unknown): string {
  return Array.isArray(values) ? values.join('\n') : ''
}
function specsText(value: Record<string, unknown> | undefined): string {
  return Object.entries(value ?? {}).map(([k, v]) => `${k}=${v}`).join('\n')
}

async function load() {
  error.value = ''
  loaded.value = false
  try {
    // `/admin/catalog-meta` 已经带回带中文 label 的品类，先前额外请求一次
    // 全量 `/products` 只为取 categories，是纯浪费。
    const [products, metaData] = await Promise.all([
      api.get<{ items: ProductRow[] }>('/admin/products'),
      api.get<{ categories: CategoryMeta[]; brands: BrandMeta[] }>('/admin/catalog-meta'),
    ])
    items.value = products.items
    meta.value = metaData
    categories.value = metaData.categories.map(({ key, label }) => ({ key, label }))
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '商品数据加载失败'
  } finally {
    loaded.value = true
  }
}

function openCreate() {
  Object.assign(form, {
    id: '', name: '', brand: '', category: categories.value[0]?.key ?? '',
    model: '', price: '', specs: '', use_cases: '', pros: '', cons: '', image_url: '', source_url: '',
  })
  editing.value = false
  showForm.value = true
  notice.value = ''
}

function openEdit(row: ProductRow) {
  Object.assign(form, {
    id: row.id, name: row.name, brand: row.brand, category: row.category,
    model: row.model, price: row.price == null ? '' : String(row.price),
    specs: specsText(row.specs), use_cases: lines(row.use_cases),
    pros: lines(row.pros), cons: lines(row.cons),
    image_url: row.image_url, source_url: row.source_url,
  })
  editing.value = true
  showForm.value = true
  notice.value = ''
}

async function submit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    if (editing.value) {
      await api.put(`/admin/products/${encodeURIComponent(form.id)}`, form)
      notice.value = `已保存商品「${form.name}」。`
    } else {
      await api.post('/admin/products', form)
      notice.value = `已新增商品「${form.name}」，标为未核验。`
    }
    showForm.value = false
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    busy.value = false
  }
}

async function toggleActive(row: ProductRow) {
  // 连点会翻转两次并各触发一次全量刷新，用同一个在途标志挡住。
  if (busy.value) return
  busy.value = true
  try {
    await api.put(`/admin/products/${encodeURIComponent(row.id)}/active`, {
      is_active: row.is_active === false,
    })
    notice.value = `已${row.is_active === false ? '启用' : '停用'}「${row.name}」。`
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  } finally {
    busy.value = false
  }
}

async function saveCategory(row: CategoryMeta) {
  // `v-model.number` 遇到非数字会保留原字符串，直接提交会序列化成 null。
  const order = Number(row.sort_order)
  if (!Number.isFinite(order)) {
    error.value = '排序必须是数字'
    return
  }
  if (busy.value) return
  busy.value = true
  try {
    await api.put(`/admin/catalog-meta/category/${encodeURIComponent(row.key)}`, {
      display_label: row.display_label,
      sort_order: order,
      is_active: row.is_active,
    })
    notice.value = `品类「${row.display_label}」已保存。`
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '品类保存失败'
  } finally {
    busy.value = false
  }
}

async function saveBrand() {
  const order = Number(brandForm.sort_order)
  if (!Number.isFinite(order)) {
    error.value = '排序必须是数字'
    return
  }
  if (busy.value) return
  busy.value = true
  try {
    await api.put(`/admin/catalog-meta/brand/${encodeURIComponent(brandForm.brand_name)}`, {
      display_name: brandForm.display_name,
      sort_order: order,
      is_active: brandForm.is_active,
    })
    notice.value = `品牌「${brandForm.brand_name}」已保存。`
    selectedBrand.value = ''
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '品牌保存失败'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">商品管理</span>
    <h1>商品维护</h1>
    <p>维护在库商品与分类信息。新增或编辑的商品会自动标记为「未核验」，提醒使用者核实价格与参数。</p>
  </div>

  <div class="grid-3" style="margin-bottom: 20px">
    <div class="stat accent"><div class="value">{{ items.length }}</div><div class="label">商品总数</div></div>
    <div class="stat"><div class="value">{{ activeCount }}</div><div class="label">在售</div></div>
    <div class="stat"><div class="value">{{ verified }}</div><div class="label">已核实条目</div></div>
  </div>

  <div class="row" style="margin-bottom: 18px">
    <button class="btn btn-sm" :class="tab === 'products' ? 'btn-primary' : 'btn-ghost'" @click="tab = 'products'">商品清单</button>
    <button class="btn btn-sm" :class="tab === 'meta' ? 'btn-primary' : 'btn-ghost'" @click="tab = 'meta'">品类与品牌</button>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>
  <p v-if="notice && !error" class="notice info">{{ notice }}</p>

  <template v-if="tab === 'products'">
    <div class="card">
      <div class="spread" style="margin-bottom: 16px">
        <h2 style="margin: 0">商品清单</h2>
        <button class="btn btn-primary btn-sm" @click="openCreate">新增商品</button>
      </div>

      <div v-if="showForm" class="card" style="background: var(--surface-soft); margin-bottom: 20px">
        <div class="spread" style="margin-bottom: 14px">
          <h2 style="margin: 0">{{ editing ? '编辑商品' : '新增商品' }}</h2>
          <button class="btn btn-ghost btn-sm" @click="showForm = false">收起</button>
        </div>
        <div class="grid-3">
          <div class="field"><label for="p-id">商品 ID</label><input id="p-id" v-model="form.id" class="input" :disabled="editing" /></div>
          <div class="field"><label for="p-name">名称</label><input id="p-name" v-model="form.name" class="input" /></div>
          <div class="field"><label for="p-brand">品牌</label><input id="p-brand" v-model="form.brand" class="input" /></div>
          <div class="field">
            <label for="p-cat">品类</label>
            <select id="p-cat" v-model="form.category" class="select">
              <option v-for="c in categories" :key="c.key" :value="c.key">{{ c.label }}</option>
            </select>
          </div>
          <div class="field"><label for="p-model">型号</label><input id="p-model" v-model="form.model" class="input" /></div>
          <div class="field"><label for="p-price">价格（元）</label><input id="p-price" v-model="form.price" class="input" inputmode="decimal" /></div>
        </div>
        <div class="grid-2">
          <div class="field"><label for="p-specs">参数（每行 键=值）</label><textarea id="p-specs" v-model="form.specs" class="textarea" /></div>
          <div class="field"><label for="p-use">使用场景（一行一条）</label><textarea id="p-use" v-model="form.use_cases" class="textarea" /></div>
          <div class="field"><label for="p-pros">亮点（一行一条）</label><textarea id="p-pros" v-model="form.pros" class="textarea" /></div>
          <div class="field"><label for="p-cons">不足（一行一条）</label><textarea id="p-cons" v-model="form.cons" class="textarea" /></div>
          <div class="field"><label for="p-img">图片地址</label><input id="p-img" v-model="form.image_url" class="input" /></div>
          <div class="field"><label for="p-url">来源链接</label><input id="p-url" v-model="form.source_url" class="input" /></div>
        </div>
        <button class="btn btn-primary" :disabled="busy" @click="submit">
          <span v-if="busy" class="spinner" /> {{ editing ? '保存修改' : '确认新增' }}
        </button>
      </div>

    </div>

    <div class="row" style="margin: 4px 0 14px">
      <span class="small muted">共 {{ items.length }} 件商品，按品类分为 {{ groupedProducts.length }} 个大类；点击大类标题可折叠。</span>
      <button v-if="groupedProducts.length" class="btn btn-ghost btn-sm" @click="toggleAllGroups">
        {{ allCollapsed ? '全部展开' : '全部收起' }}
      </button>
    </div>

    <div v-for="group in groupedProducts" :key="group.key" class="card category-block">
      <div class="spread" style="cursor: pointer" @click="toggleGroup(group.key)">
        <div>
          <h2>{{ group.label }}</h2>
          <span class="small muted">{{ group.items.length }} 件商品 · {{ activeIn(group) }} 件在售</span>
        </div>
        <span class="badge" :class="collapsedGroups.includes(group.key) ? 'accent' : ''">
          {{ collapsedGroups.includes(group.key) ? '已收起 · 点击展开' : '点击收起' }}
        </span>
      </div>

      <div v-if="!collapsedGroups.includes(group.key)" class="table-wrap" style="margin-top: 16px">
        <table>
          <thead><tr><th>名称</th><th>品牌</th><th>价格</th><th>状态</th><th>核验</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="p in group.items" :key="p.id">
              <td><strong>{{ p.name }}</strong><br /><span class="small muted">{{ p.id }}</span></td>
              <td>{{ p.brand || '—' }}</td>
              <td>{{ formatPrice(p.price) }}</td>
              <td><span class="badge" :class="p.is_active === false ? 'amber' : 'green'">{{ p.is_active === false ? '已停用' : '在售' }}</span></td>
              <td><span class="badge" :class="p.data_status === 'verified' ? 'green' : 'amber'">{{ p.data_status === 'verified' ? '已核实' : '未核实' }}</span></td>
              <td>
                <div class="row" style="gap: 6px; flex-wrap: nowrap">
                  <button class="btn btn-ghost btn-sm" @click="openEdit(p)">编辑</button>
                  <button class="btn btn-ghost btn-sm" @click="toggleActive(p)">{{ p.is_active === false ? '启用' : '停用' }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <p v-if="!loaded" class="loading"><span class="spinner" /> 正在加载商品目录…</p>
    <p v-else-if="!items.length" class="small muted">商品目录为空或加载失败，请查看上方提示后刷新页面。</p>
  </template>

  <div v-else class="stack">
    <p class="small muted">按品类大类分组，品类名为中文。默认只展示概要；点「编辑品类」或某个品牌才展开设置。</p>

    <div v-for="cat in meta?.categories ?? []" :key="cat.key" class="card category-block">
      <div class="spread">
        <div>
          <h2>{{ cat.label }}</h2>
          <span class="small muted">{{ cat.product_count }} 件商品 · {{ cat.brands.length }} 个品牌</span>
        </div>
        <div class="row">
          <span class="badge" :class="cat.is_active ? 'green' : 'amber'">{{ cat.is_active ? '启用' : '停用' }}</span>
          <button class="btn btn-ghost btn-sm" @click="expandedCategory = expandedCategory === cat.key ? '' : cat.key">
            {{ expandedCategory === cat.key ? '收起' : '编辑品类' }}
          </button>
        </div>
      </div>

      <div class="row brand-chips" style="margin-top: 16px">
        <button
          v-for="b in cat.brands"
          :key="b"
          class="brand-chip"
          :class="{ selected: selectedBrand === b }"
          @click="selectBrand(b)"
        >{{ brandDisplayName(b) }}</button>
        <span v-if="!cat.brands.length" class="small muted">该品类下暂无品牌</span>
      </div>

      <div v-if="expandedCategory === cat.key" class="card" style="background: var(--surface-soft); margin: 16px 0 0">
        <h3>编辑品类「{{ cat.label }}」</h3>
        <div class="grid-3">
          <div class="field"><label>展示名</label><input v-model="cat.display_label" class="input" /></div>
          <div class="field"><label>排序</label><input v-model.number="cat.sort_order" class="input" inputmode="numeric" /></div>
          <div class="field">
            <label>状态</label>
            <label class="check-item" style="margin-top: 2px">
              <input v-model="cat.is_active" type="checkbox" /><span>启用该品类</span>
            </label>
          </div>
        </div>
        <div class="row">
          <button class="btn btn-primary btn-sm" @click="saveCategory(cat)">保存品类</button>
          <span class="small muted">{{ cat.custom_label ? '当前使用自定义名称' : '当前使用系统默认名称' }}</span>
        </div>
      </div>
    </div>

    <div v-if="selectedBrand" class="card">
      <div class="spread" style="margin-bottom: 14px">
        <h2 style="margin: 0">编辑品牌「{{ brandDisplayName(selectedBrand) }}」</h2>
        <button class="btn btn-ghost btn-sm" @click="selectedBrand = ''">取消</button>
      </div>
      <div class="grid-3">
        <div class="field"><label>展示名</label><input v-model="brandForm.display_name" class="input" /></div>
        <div class="field"><label>排序</label><input v-model.number="brandForm.sort_order" class="input" inputmode="numeric" /></div>
        <div class="field">
          <label>状态</label>
          <label class="check-item" style="margin-top: 2px">
            <input v-model="brandForm.is_active" type="checkbox" /><span>启用该品牌</span>
          </label>
        </div>
      </div>
      <div class="row">
        <button class="btn btn-primary btn-sm" @click="saveBrand">保存品牌</button>
        <span class="small muted">展示名会同步用于筛选与报告</span>
      </div>
    </div>

    <div v-if="unassignedBrands.length" class="card">
      <h2>其他品牌（当前没有在售商品）</h2>
      <div class="row brand-chips">
        <button
          v-for="b in unassignedBrands"
          :key="b.brand_name"
          class="brand-chip"
          :class="{ selected: selectedBrand === b.brand_name }"
          @click="selectBrand(b.brand_name)"
        >{{ b.display_name }}</button>
      </div>
      <p class="small muted" style="margin: 12px 0 0">这些品牌登记在字典里但库里没有商品，解析器不会识别它们。</p>
    </div>

    <div v-if="!meta?.categories?.length" class="card">
      <div class="empty"><strong>暂无品类</strong>添加商品后会自动归类。</div>
    </div>
  </div>
</template>
