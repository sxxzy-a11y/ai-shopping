<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import { formatDateTime } from '../utils/format'

interface Metric {
  key: string
  label: string
  definition: string
  numerator: number
  denominator: number
  display: string
}
interface ManualMetric { name: string; definition: string; status: string }
interface CategoryResult { category: string; total: number; passed: number; failed: number }
interface EvalReport {
  schema_version: number
  generated_at: string
  dataset: { name: string; version: string; updated_at: string; case_count: number }
  retrieval: { mode: string; label: string; detail: string }
  summary: { total: number; passed: number; failed: number; duration_ms: number }
  metrics: Metric[]
  manual_metrics: ManualMetric[]
  categories: CategoryResult[]
}
interface EvalResponse {
  available: boolean
  reason?: string
  file?: string
  payload?: EvalReport
}

const response = ref<EvalResponse | null>(null)
const error = ref('')
const loading = ref(true)

const report = computed(() => response.value?.payload ?? null)
const summary = computed(() => report.value?.summary)

function percent(metric: Metric): number {
  if (!metric.denominator) return 0
  return Math.round((metric.numerator / metric.denominator) * 100)
}

onMounted(async () => {
  try {
    response.value = await api.get<EvalResponse>('/eval')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '评测数据加载失败'
  } finally {
    // 没有这个标志，请求失败后模板会一直停在「正在读取评测数据…」。
    loading.value = false
  }
})
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">效果评测</span>
    <h1>效果评测</h1>
    <p>这里展示的是评测报告的解读结果：用例总数、通过情况、各项指标与分类明细。数字来自仓库里的报告快照，不是实时计算。</p>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>

  <template v-if="report">
    <!-- 概览 -->
    <div class="grid-3" style="margin-bottom: 20px">
      <div class="stat accent"><div class="value">{{ summary?.total ?? '—' }}</div><div class="label">评测用例</div></div>
      <div class="stat"><div class="value" style="color: var(--green)">{{ summary?.passed ?? '—' }}</div><div class="label">通过</div></div>
      <div class="stat"><div class="value" :style="summary?.failed ? 'color: var(--accent)' : ''">{{ summary?.failed ?? '—' }}</div><div class="label">失败</div></div>
    </div>

    <!-- 数据集与运行方式 -->
    <div class="card">
      <div class="spread" style="margin-bottom: 14px">
        <h2 style="margin: 0">报告概况</h2>
        <span class="badge green">{{ report.retrieval?.label || '检索模式未标注' }}</span>
      </div>
      <div class="table-wrap">
        <table>
          <tbody>
            <tr><th>评测集</th><td>{{ report.dataset?.name }} · 版本 {{ report.dataset?.version }}</td></tr>
            <tr><th>用例数 / 数据更新</th><td>{{ report.dataset?.case_count }} 条 · {{ report.dataset?.updated_at }}</td></tr>
            <tr><th>报告生成时间</th><td>{{ formatDateTime(report.generated_at, { seconds: true }) || '—' }}</td></tr>
            <tr><th>结果生成耗时</th><td>{{ summary?.duration_ms }} 毫秒</td></tr>
            <tr><th>检索方式</th><td>{{ report.retrieval?.label || '本地检索' }}</td></tr>
            <tr><th>结果说明</th><td>最近一次完整评测，按用例逐项核对</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 自动指标 -->
    <div class="card">
      <h2>自动指标</h2>
      <p class="small muted" style="margin-top: -6px">分子 / 分母来自评测集标注，进度条表示通过比例。</p>
      <div v-for="m in report.metrics ?? []" :key="m.key" class="metric-row">
        <div>
          <strong>{{ m.label }}</strong>
          <div class="small muted" style="line-height: 1.55; margin-top: 3px">{{ m.definition }}</div>
        </div>
        <div class="metric-value">{{ m.display }}</div>
        <div class="progress"><span :style="{ width: percent(m) + '%' }"></span></div>
      </div>
    </div>

    <!-- 分类通过情况 -->
    <div class="card">
      <h2>分类通过情况（{{ report.categories?.length ?? 0 }} 类）</h2>
      <div v-if="report.categories?.length" class="table-wrap">
        <table>
          <thead><tr><th>类别</th><th>通过 / 总数</th><th>结果</th></tr></thead>
          <tbody>
            <tr v-for="c in report.categories" :key="c.category">
              <td>{{ c.category }}</td>
              <td>{{ c.passed }} / {{ c.total }}</td>
              <td><span class="badge" :class="c.failed ? 'amber' : 'green'">{{ c.failed ? `${c.failed} 项失败` : '全部通过' }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty"><strong>没有分类明细</strong>报告里未包含分类统计。</div>
    </div>

    <!-- 人工指标 -->
    <div class="card">
      <h2>需要人工复核的指标</h2>
      <div v-for="m in report.manual_metrics ?? []" :key="m.name" class="metric-row">
        <div>
          <strong>{{ m.name }}</strong>
          <div class="small muted" style="line-height: 1.55; margin-top: 3px">{{ m.definition }}</div>
        </div>
        <div class="small muted" style="grid-column: span 2">{{ m.status }}</div>
      </div>
      <p class="notice" style="margin-top: 16px">
        这些结果用于观察同一套口径下的变化，不代表系统在真实购物场景中的整体表现。
        任务完成率与证据支持率还需要人工复核。
      </p>
    </div>
  </template>

  <div v-else-if="response" class="card">
    <div class="empty">
      <strong>暂无评测快照</strong>
      {{ response.reason }}
    </div>
    <p class="notice info">
      评测按批次运行，结果生成后会自动出现在这里。本页展示的是最近一次完整结果。
    </p>
  </div>
  <p v-else-if="loading" class="loading"><span class="spinner" /> 正在读取评测数据…</p>
</template>
