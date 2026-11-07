<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { HistoryEntry, Meta } from '../api/types'
import AppIcon from '../components/AppIcon.vue'

const meta = ref<Meta | null>(null)
const recent = ref<HistoryEntry[]>([])

function formatTime(value: string): string {
  return value ? value.replace('T', ' ').slice(0, 16) : ''
}

onMounted(async () => {
  try {
    const [metaData, history] = await Promise.all([
      api.get<Meta>('/meta'),
      api.get<{ entries: HistoryEntry[] }>('/history'),
    ])
    meta.value = metaData
    recent.value = history.entries.slice(0, 3)
  } catch {
    meta.value = null
  }
})
</script>

<template>
  <section class="hero">
    <span class="eyebrow">SMARTBUY ADVISOR</span>
    <h1>把购买决定，讲清楚</h1>
    <p>
      不替你拍板，也不堆砌参数。输入你的需求，系统把筛选依据、评分构成和需要核实的点摊开，
      让你知道自己为什么选、以及还该确认什么。
    </p>
    <div class="steps">
      <span class="step"><b>01</b> 描述需求</span>
      <span class="step"><b>02</b> 核对证据</span>
      <span class="step"><b>03</b> 做出决定</span>
    </div>
  </section>

  <div class="grid-3" style="margin-bottom: 20px">
    <div class="stat accent">
      <div class="value">{{ meta?.total ?? '—' }}</div>
      <div class="label">在库商品</div>
    </div>
    <div class="stat">
      <div class="value">{{ meta?.categories?.length ?? '—' }}</div>
      <div class="label">覆盖品类</div>
    </div>
    <div class="stat">
      <div class="value">{{ meta?.brands?.length ?? '—' }}</div>
      <div class="label">可选品牌</div>
    </div>
  </div>

  <div class="card">
    <div class="spread" style="margin-bottom: 14px">
      <h2 style="margin: 0">最近分析</h2>
      <RouterLink to="/history" class="btn btn-ghost btn-sm">查看全部记录</RouterLink>
    </div>
    <div v-if="recent.length" class="grid-3">
      <RouterLink v-for="entry in recent" :key="entry.id" to="/history" class="product-row" style="text-decoration: none">
        <span class="small muted">{{ formatTime(entry.created_at) }}</span>
        <strong>{{ entry.demand_summary || '未填写需求摘要' }}</strong>
        <span class="small muted">首选 {{ entry.top_product || '—' }} · {{ entry.result_count }} 条结果</span>
      </RouterLink>
    </div>
    <div v-else class="empty">
      <strong>还没有分析记录</strong>
      写下你的第一条需求，几分钟就能拿到一份说明依据的建议。
      <div style="margin-top: 14px"><RouterLink to="/analysis" class="btn btn-primary btn-sm">开始第一次分析</RouterLink></div>
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h2>开始一次分析</h2>
      <p class="muted small" style="line-height: 1.8; margin-top: 0">
        用一句话描述预算、用途和偏好，例如「5000 元以内，主要写代码，需要便携」。
        也可以配合结构化控件指定品类与预算，让结果更精确。
      </p>
      <RouterLink to="/analysis" class="btn btn-primary">
        <AppIcon name="arrow" /> 前往智能分析
      </RouterLink>
    </div>
    <div class="card">
      <h2>横向比较 / 提问</h2>
      <p class="muted small" style="line-height: 1.8; margin-top: 0">
        选定几件商品看参数差异，或直接向 AI 问答咨询选购思路。所有结论都标注来源，
        不会把参考价说成实时成交价。
      </p>
      <div class="row">
        <RouterLink to="/compare" class="btn btn-ghost">商品比较</RouterLink>
        <RouterLink to="/qa" class="btn btn-ghost">AI 问答</RouterLink>
      </div>
    </div>
  </div>

  <div v-if="meta?.disclaimer" class="notice">
    <strong>数据说明：</strong>{{ meta.disclaimer }}
  </div>
</template>
