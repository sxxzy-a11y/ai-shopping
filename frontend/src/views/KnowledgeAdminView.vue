<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { Meta, ProductList } from '../api/types'

interface DocRow {
  doc_id: string
  title: string
  doc_type: string
  category: string
  source_path: string
  deletable: boolean
}
interface RetrievalHit { [key: string]: unknown }

const meta = ref<Meta | null>(null)
const products = ref<ProductList | null>(null)
const docs = ref<DocRow[]>([])
const error = ref('')
const notice = ref('')
const busy = ref(false)
const showCreate = ref(false)
const createForm = reactive({ title: '', doc_type: 'service', body: '', source: '本项目整理（非厂商资料）', category: '' })
const query = ref('笔记本多重适合带出门')
const retrieval = ref<{ mode: string; note: string; passages: RetrievalHit[]; count: number } | null>(null)

const MODE_LABELS: Record<string, string> = {
  vector: '语义检索', keyword: '关键词检索', bm25: '关键词检索', unavailable: '暂不可用',
}
const TYPE_LABELS: Record<string, string> = {
  category: '品类指南', service: '常见问题', product: '商品资料',
}

async function load() {
  error.value = ''
  try {
    const [m, p, d] = await Promise.all([
      api.get<Meta>('/meta'),
      api.get<ProductList>('/products'),
      api.get<{ documents: DocRow[] }>('/admin/knowledge/documents'),
    ])
    meta.value = m
    products.value = p
    docs.value = d.documents
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '知识库状态加载失败'
  }
}

async function createDoc() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const data = await api.post<{ documents: DocRow[] }>('/admin/knowledge/documents', createForm)
    docs.value = data.documents
    notice.value = `已新增资料「${createForm.title}」。`
    createForm.title = ''
    createForm.body = ''
    showCreate.value = false
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '新增失败'
  } finally {
    busy.value = false
  }
}

async function removeDoc(row: DocRow) {
  if (!confirm(`确定删除资料「${row.title}」吗？对应文件会被移除，商品级资料不能在页面删除。`)) return
  try {
    const data = await api.delete<{ documents: DocRow[] }>(`/admin/knowledge/documents/${encodeURIComponent(row.doc_id)}`)
    docs.value = data.documents
    notice.value = `已删除「${row.title}」。`
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

async function runRetrieval() {
  if (!query.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    retrieval.value = await api.post('/admin/knowledge/retrieve', { query: query.value })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '检索失败'
  } finally {
    busy.value = false
  }
}

async function reindex() {
  try {
    const data = await api.post<{ documents: DocRow[]; cleared_caches: number }>('/admin/knowledge/reindex', {})
    docs.value = data.documents
    notice.value = `已清理 ${data.cleared_caches} 处索引缓存，下次检索按文件时间自动重建。`
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '重建失败'
  }
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">资料管理</span>
    <h1>知识库管理</h1>
    <p>维护选购资料并检验检索效果。资料更新后可以刷新检索索引，让问答用上最新内容。</p>
  </div>

  <div class="grid-3" style="margin-bottom: 20px">
    <div class="stat accent"><div class="value">{{ products?.total ?? '—' }}</div><div class="label">语料覆盖商品</div></div>
    <div class="stat"><div class="value">{{ docs.length }}</div><div class="label">知识文档</div></div>
    <div class="stat"><div class="value">{{ products?.issues?.length ?? 0 }}</div><div class="label">数据加载告警</div></div>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>
  <p v-if="notice" class="notice info">{{ notice }}</p>

  <div class="card">
    <div class="spread" style="margin-bottom: 16px">
      <h2 style="margin: 0">知识文档</h2>
      <div class="row">
        <button class="btn btn-ghost btn-sm" @click="reindex">刷新检索索引</button>
        <button class="btn btn-primary btn-sm" @click="showCreate = !showCreate">新增资料</button>
      </div>
    </div>

    <div v-if="showCreate" class="card" style="background: var(--surface-soft); margin-bottom: 18px">
      <h2>新增知识文档</h2>
      <div class="grid-3">
        <div class="field"><label for="k-title">标题</label><input id="k-title" v-model="createForm.title" class="input" /></div>
        <div class="field">
          <label for="k-type">类型</label>
          <select id="k-type" v-model="createForm.doc_type" class="select">
            <option value="service">服务说明 / FAQ</option>
            <option value="category">品类指南</option>
          </select>
        </div>
        <div class="field"><label for="k-cat">分类（可选）</label><input id="k-cat" v-model="createForm.category" class="input" /></div>
      </div>
      <div class="field"><label for="k-source">来源</label><input id="k-source" v-model="createForm.source" class="input" /></div>
      <div class="field"><label for="k-body">正文</label><textarea id="k-body" v-model="createForm.body" class="textarea" /></div>
      <button class="btn btn-primary" :disabled="busy" @click="createDoc">
        <span v-if="busy" class="spinner" /> 确认新增
      </button>
    </div>

    <div v-if="docs.length" class="table-wrap">
      <table>
        <thead><tr><th>标题</th><th>类型</th><th>分类</th><th>文档 ID</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="row in docs" :key="row.doc_id">
            <td><strong>{{ row.title }}</strong></td>
            <td><span class="badge">{{ TYPE_LABELS[row.doc_type] ?? '资料' }}</span></td>
            <td>{{ row.category || '—' }}</td>
            <td class="small muted">{{ row.doc_id }}</td>
            <td>
              <button v-if="row.deletable" class="btn btn-ghost btn-sm" @click="removeDoc(row)">删除</button>
              <span v-else class="small muted">商品级自动生成</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty"><strong>暂无资料</strong>新增选购指南或常见问题后会显示在这里。</div>
  </div>

  <div class="card">
    <h2>检索效果检查</h2>
    <div class="row" style="margin-bottom: 14px">
      <input v-model="query" class="input" style="max-width: 420px" placeholder="输入一个问题，看命中了哪些资料" />
      <button class="btn btn-primary" :disabled="busy" @click="runRetrieval">
        <span v-if="busy" class="spinner" /> 检索
      </button>
    </div>
    <template v-if="retrieval">
      <div class="row" style="margin-bottom: 12px">
        <span class="badge accent">方式：{{ MODE_LABELS[retrieval.mode] ?? '本地检索' }}</span>
        <span class="badge">命中 {{ retrieval.count }} 条</span>
        <span v-if="retrieval.note" class="small muted">{{ retrieval.note }}</span>
      </div>
      <div v-for="(hit, i) in retrieval.passages" :key="i" class="product-row" style="margin-bottom: 8px">
        <strong>{{ String(hit.title ?? hit.doc_id ?? '资料片段') }}</strong>
        <span class="small muted">{{ String(hit.excerpt ?? hit.text ?? '').slice(0, 220) }}</span>
      </div>
      <div v-if="!retrieval.passages.length" class="empty"><strong>没有命中资料</strong>这是「确实没有相关资料」，不是服务故障。</div>
    </template>
    <div v-else class="empty"><strong>尚未检索</strong>输入问题后可以看到实际命中的语料片段。</div>
  </div>

  <div class="card">
    <h2>数据集状态</h2>
    <div class="table-wrap">
      <table>
        <tbody>
          <tr><th>名称</th><td>{{ products?.dataset_name || '—' }}</td></tr>
          <tr><th>品类</th><td>{{ meta?.categories?.map((c) => c.label).join('、') || '—' }}</td></tr>
          <tr><th>免责声明</th><td class="small">{{ products?.disclaimer || '—' }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
