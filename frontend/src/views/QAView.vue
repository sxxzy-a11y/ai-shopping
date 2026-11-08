<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { QAResult } from '../api/types'
import { useFavorites } from '../composables/useFavorites'
import { formatPrice } from '../utils/format'

const question = ref('')
const result = ref<QAResult | null>(null)
const error = ref('')
const busy = ref(false)
const expanded = ref('')
const { favorites, load: loadFavorites, toggle: toggleFavoriteRaw } = useFavorites()

const examples = [
  '写代码用的笔记本该看哪些参数？',
  '5000 元以内有什么适合通勤的手机？',
  '续航和性能之间怎么取舍？',
]

const SOURCE_LABELS: Record<string, string> = {
  'knowledge+products': '选购资料 + 在库商品',
  knowledge: '选购资料',
  'general-knowledge': '通用知识（未引用资料）',
  catalog: '在库商品',
  empty: '暂无结果',
}
const MODE_LABELS: Record<string, string> = {
  vector: '语义检索', keyword: '关键词检索', bm25: '关键词检索', unavailable: '暂不可用',
}

function percent(weight: number): string {
  return `${Math.round(weight * 100)}%`
}

onMounted(loadFavorites)

async function toggleFavorite(productId: string) {
  try {
    await toggleFavoriteRaw(productId)
  } catch {
    error.value = '收藏操作失败，请稍后重试'
  }
}

async function ask(text = question.value) {
  if (!text.trim() || busy.value) return
  question.value = text
  error.value = ''
  result.value = null
  expanded.value = ''
  busy.value = true
  try {
    result.value = await api.post<QAResult>('/qa', { question: text })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '问答失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">选购问答</span>
    <h1>AI 问答</h1>
    <p>问选购思路、参数取舍或具体商品都可以。回答会标明依据来源，相关商品可以点开看参数、评分理由与资料出处。</p>
  </div>

  <div class="card">
    <div class="field">
      <label for="q">你的问题</label>
      <textarea id="q" v-model="question" class="textarea" style="min-height: 92px" placeholder="想问点什么？" @keydown.ctrl.enter="ask()" />
    </div>
    <div class="row">
      <button class="btn btn-primary" :disabled="busy || !question.trim()" @click="ask()">
        <span v-if="busy" class="spinner" /> {{ busy ? '思考中…' : '提问' }}
      </button>
      <span class="small muted">Ctrl + Enter 快速提交</span>
    </div>
    <div class="divider"></div>
    <div class="row">
      <span class="small muted">试试：</span>
      <button v-for="e in examples" :key="e" class="badge" style="cursor: pointer" @click="ask(e)">{{ e }}</button>
    </div>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>

  <div v-if="result" class="card">
    <div class="spread" style="margin-bottom: 14px">
      <h2 style="margin: 0">回答</h2>
      <span class="badge" :class="result.source === 'catalog' || result.source === 'knowledge' ? 'green' : 'accent'">
        {{ SOURCE_LABELS[result.source] ?? result.source }}
      </span>
    </div>
    <p class="answer">{{ result.answer }}</p>

    <div v-if="result.products?.length" style="margin-top: 24px">
      <div class="spread" style="margin-bottom: 12px">
        <h2 style="margin: 0">相关商品（{{ result.products.length }}）</h2>
        <span class="small muted">点击商品查看完整信息</span>
      </div>

      <div class="stack">
        <div v-for="p in result.products" :key="p.id" class="product-row">
          <div class="spread" style="cursor: pointer" @click="expanded = expanded === p.id ? '' : p.id">
            <div>
              <strong>{{ p.name }}</strong>
              <div class="small muted">{{ p.brand }} {{ p.model }} · {{ p.category_label }}</div>
            </div>
            <div class="row">
              <span class="price">{{ formatPrice(p.price) }}</span>
              <span class="badge accent">{{ p.score_total }} 分</span>
              <span class="badge" :class="p.within_budget ? 'green' : 'amber'">{{ p.budget_label }}</span>
              <button class="btn btn-ghost btn-sm">{{ expanded === p.id ? '收起' : '查看详情' }}</button>
            </div>
          </div>

          <div v-if="expanded === p.id" class="qa-detail">
            <div class="grid-2">
              <div>
                <h3>评分构成</h3>
                <div v-if="p.dimensions?.length" class="table-wrap">
                  <table>
                    <thead><tr><th>维度</th><th>得分</th><th>权重</th></tr></thead>
                    <tbody>
                      <tr v-for="d in p.dimensions" :key="d.key">
                        <td>
                          <strong>{{ d.label }}</strong>
                          <div class="small muted" style="line-height: 1.55; margin-top: 3px">{{ d.reason }}</div>
                        </td>
                        <td>{{ d.score }}</td>
                        <td>{{ percent(d.weight) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="small muted">本次没有可用的评分明细。</p>
              </div>

              <div>
                <h3>核心参数</h3>
                <div v-if="p.specs?.length" class="table-wrap">
                  <table>
                    <tbody>
                      <tr v-for="s in p.specs" :key="s.key"><th>{{ s.label }}</th><td>{{ s.value }}</td></tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="small muted">该商品没有登记核心参数。</p>
              </div>
            </div>

            <div class="grid-2" style="margin-top: 18px">
              <div>
                <h3>亮点</h3>
                <ul class="fact-list">
                  <li v-for="(text, i) in p.pros" :key="i">{{ text }}</li>
                  <li v-if="!p.pros?.length" class="muted">暂无登记</li>
                </ul>
              </div>
              <div>
                <h3>需要留意</h3>
                <ul class="fact-list">
                  <li v-for="(text, i) in p.cons" :key="i">{{ text }}</li>
                  <li v-if="!p.cons?.length" class="muted">暂无登记</li>
                </ul>
              </div>
            </div>

            <div v-if="p.use_cases?.length" style="margin-top: 18px">
              <h3>适用场景</h3>
              <div class="row brand-chips">
                <span v-for="u in p.use_cases" :key="u" class="brand-chip" style="cursor: default">{{ u }}</span>
              </div>
            </div>

            <div class="divider"></div>
            <div class="grid-2">
              <div class="small muted" style="line-height: 1.9">
                资料来源：{{ p.data_source || '公开资料整理' }}<br />
                核验状态：<span class="badge" :class="p.data_status === 'verified' ? 'green' : 'amber'">{{ p.data_status === 'verified' ? '已核实' : '未核实' }}</span><br />
                资料更新：{{ p.updated_at || '—' }} · 价格采集：{{ p.price_collected_at || '—' }}
              </div>
              <div class="row">
                <a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener noreferrer" class="btn btn-ghost btn-sm">查看原始资料</a>
                <button class="btn btn-ghost btn-sm" @click="toggleFavorite(p.id)">
                  {{ favorites.includes(p.id) ? '取消收藏' : '收藏' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="divider"></div>
    <div class="row">
      <span class="badge">依据检索：{{ MODE_LABELS[result.retrieval_mode] ?? '本地检索' }}</span>
      <span v-if="result.retrieval_note" class="small muted">{{ result.retrieval_note }}</span>
    </div>
    <p class="notice info" style="margin-top: 14px">
      AI 回答可能不准确，涉及具体价格、参数、保修政策时请到官方渠道核实。
    </p>
  </div>
</template>
