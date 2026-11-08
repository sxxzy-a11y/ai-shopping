<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { HistoryEntry, Overview } from '../api/types'
import { formatDateTime } from '../utils/format'

const data = ref<Overview | null>(null)
const analyses = ref<HistoryEntry[]>([])
const analysesTotal = ref(0)
const error = ref('')
const notice = ref('')

/** 列表有上限，标题必须说清「显示的是最近 N 条」，不能把截断后的条数当总数。 */
const analysesHeading = computed(() =>
  analysesTotal.value > analyses.value.length
    ? `全站分析记录（共 ${analysesTotal.value} 条，显示最近 ${analyses.value.length} 条）`
    : `全站分析记录（${analyses.value.length}）`,
)

async function load() {
  error.value = ''
  try {
    const [overview, history] = await Promise.all([
      api.get<Overview>('/admin/overview'),
      api.get<{ entries: HistoryEntry[]; total: number }>('/admin/analyses'),
    ])
    data.value = overview
    analyses.value = history.entries
    analysesTotal.value = history.total
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

interface AgentRunRow {
  id: number
  created_at: string
  question: string
  answer: string
  rounds: number
  degraded: number
  degrade_reason: string
  user_id: string | null
  step_count: number
}
interface AgentStep {
  round: number
  tool: string
  arguments: Record<string, unknown>
  status: string
  summary: string
}

const agentRuns = ref<AgentRunRow[]>([])
const activeTraceId = ref<number | null>(null)
const activeTrace = ref<AgentStep[] | null>(null)
const traceError = ref('')

async function loadAgentRuns() {
  try {
    const result = await api.get<{ runs: AgentRunRow[] }>('/admin/agent/runs?limit=20')
    agentRuns.value = result.runs
  } catch (err) {
    // 单独兜错：轨迹表读不到不该让账号/商品/历史三块内容一起消失。
    traceError.value = err instanceof ApiError ? err.message : '轨迹列表读取失败'
  }
}

async function openTrace(id: number) {
  if (activeTraceId.value === id) {
    activeTraceId.value = null
    activeTrace.value = null
    return
  }
  activeTraceId.value = id
  activeTrace.value = null
  traceError.value = ''
  try {
    const result = await api.get<{ run: { steps: AgentStep[] } }>(`/admin/agent/runs/${id}`)
    // 连点不同行时，慢的旧响应不能覆盖新展开的轨迹。
    if (activeTraceId.value !== id) return
    activeTrace.value = result.run.steps
  } catch (err) {
    if (activeTraceId.value !== id) return
    traceError.value = err instanceof ApiError ? err.message : '轨迹详情读取失败'
  }
}

onMounted(() => {
  void load()
  void loadAgentRuns()
})
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
    <div class="stat"><div class="value">{{ analysesTotal }}</div><div class="label">全站分析记录</div></div>
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
    <h2>{{ analysesHeading }}</h2>
    <div v-if="analyses.length" class="table-wrap">
      <table>
        <thead><tr><th>时间</th><th>归属</th><th>需求摘要</th><th>首选</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="e in analyses" :key="e.id">
            <td class="small">{{ formatDateTime(e.created_at) }}</td>
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

  <div class="card">
    <div class="spread" style="margin-bottom: 14px">
      <h2 style="margin: 0">Agent 执行轨迹</h2>
      <button class="btn btn-ghost btn-sm" @click="loadAgentRuns">刷新</button>
    </div>
    <p class="small muted">
      记录每次编排中真实发生过的工具调用，包括被参数校验拒绝的调用。点击「回放」查看步骤。
    </p>
    <p v-if="traceError" class="notice error">{{ traceError }}</p>
    <div v-if="agentRuns.length" class="table-wrap">
      <table>
        <thead><tr><th>时间</th><th>问题</th><th>轮次</th><th>调用数</th><th>结果</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in agentRuns" :key="r.id">
            <td class="small">{{ formatDateTime(r.created_at, { seconds: true }) }}</td>
            <td>{{ r.question || '—' }}</td>
            <td>{{ r.rounds }}</td>
            <td>{{ r.step_count }}</td>
            <td><span class="badge" :class="r.degraded ? 'amber' : 'green'">{{ r.degraded ? '已降级' : '完成' }}</span></td>
            <td><button class="btn btn-ghost btn-sm" @click="openTrace(r.id)">{{ activeTraceId === r.id ? '收起' : '回放' }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty"><strong>还没有轨迹记录</strong>跑一次智能分析后，后台会生成编排轨迹。</div>

    <div v-if="activeTraceId !== null" class="card" style="margin-top: 16px; background: var(--surface-soft)">
      <h3>轨迹 #{{ activeTraceId }}</h3>
      <div v-if="activeTrace?.length" class="table-wrap">
        <table>
          <thead><tr><th>轮次</th><th>工具</th><th>参数</th><th>状态</th><th>结果摘要</th></tr></thead>
          <tbody>
            <tr v-for="(s, i) in activeTrace" :key="i">
              <td>{{ s.round }}</td>
              <td><code>{{ s.tool }}</code></td>
              <td class="small">{{ JSON.stringify(s.arguments) }}</td>
              <td><span class="badge" :class="s.status === 'ok' ? 'green' : 'amber'">{{ s.status }}</span></td>
              <td class="small">{{ s.summary }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="small muted">这次编排没有产生工具调用（模型直接作答），或轨迹仍在加载。</p>
    </div>
  </div>
</template>
