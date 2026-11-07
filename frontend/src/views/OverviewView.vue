<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { HistoryEntry, Overview } from '../api/types'

const data = ref<Overview | null>(null)
const analyses = ref<HistoryEntry[]>([])
const error = ref('')
const notice = ref('')

async function load() {
  error.value = ''
  try {
    const [overview, history] = await Promise.all([
      api.get<Overview>('/admin/overview'),
      api.get<{ entries: HistoryEntry[] }>('/admin/analyses'),
    ])
    data.value = overview
    analyses.value = history.entries
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '概览加载失败'
  }
}

async function removeAnalysis(entry: HistoryEntry) {
  if (!confirm(`确定删除记录 #${entry.id}（${entry.demand_summary || '无摘要'}）吗？此操作不可恢复。`)) return
  try {
    const result = await api.delete<{ ok: boolean; message?: string }>(`/admin/analyses/${entry.id}`)
    notice.value = result.ok ? `已删除记录 #${entry.id}。` : (result.message ?? '删除未生效')
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">运行概览</span>
    <h1>全站概览</h1>
    <p>账号、商品、数据库与全站分析记录的一屏体检。数字直接来自当前运行实例，不做估算。</p>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>
  <p v-if="notice" class="notice info">{{ notice }}</p>

  <div class="grid-3" style="margin-bottom: 20px">
    <div class="stat accent"><div class="value">{{ data?.user_count ?? '—' }}</div><div class="label">账号总数</div></div>
    <div class="stat"><div class="value">{{ data?.product_count ?? '—' }}</div><div class="label">在库商品</div></div>
    <div class="stat"><div class="value">{{ analyses.length }}</div><div class="label">全站分析记录</div></div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h2>运行状态</h2>
      <div class="table-wrap">
        <table>
          <tbody>
            <tr><th>数据库</th><td><span class="badge" :class="data?.healthy ? 'green' : 'amber'">{{ data?.message ?? '检查中' }}</span></td></tr>
            <tr><th>可用管理员</th><td>{{ data?.admin_count ?? '—' }}</td></tr>
            <tr><th>信息不完整商品</th><td>{{ data?.incomplete_products ?? '—' }}</td></tr>
            <tr><th>数据集</th><td>{{ data?.dataset_name || '—' }}</td></tr>
            <tr><th>数据更新时间</th><td>{{ data?.dataset_updated_at || '—' }}</td></tr>
            <tr><th>覆盖品类</th><td>{{ data?.categories?.map((c) => c.label).join('、') || '—' }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>最近账号</h2>
      <div v-if="data?.users?.length" class="table-wrap">
        <table>
          <thead><tr><th>用户名</th><th>角色</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="u in data.users.slice(0, 8)" :key="u.username">
              <td>{{ u.username }}</td>
              <td>{{ u.role === 'admin' ? '管理员' : '普通用户' }}</td>
              <td><span class="badge" :class="u.is_active ? 'green' : 'amber'">{{ u.is_active ? '启用' : '停用' }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty"><strong>暂无账号</strong>账号创建后会显示在这里。</div>
    </div>
  </div>

  <div class="card">
    <h2>全站分析记录（{{ analyses.length }}）</h2>
    <div v-if="analyses.length" class="table-wrap">
      <table>
        <thead><tr><th>时间</th><th>归属</th><th>需求摘要</th><th>首选</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="e in analyses" :key="e.id">
            <td class="small">{{ e.created_at?.replace('T', ' ').slice(0, 16) }}</td>
            <td class="small">{{ e.user_id || '无归属' }}</td>
            <td>{{ e.demand_summary || '—' }}</td>
            <td>{{ e.top_product || '—' }}</td>
            <td><button class="btn btn-ghost btn-sm" @click="removeAnalysis(e)">删除</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty"><strong>还没有分析记录</strong>用户跑一次分析后会出现在这里。</div>
  </div>
</template>
