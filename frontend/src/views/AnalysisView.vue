<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { AnalysisResult, Meta, ReportItem } from '../api/types'
import { useFavorites } from '../composables/useFavorites'
import { useLoadingBar } from '../composables/useLoadingBar'

const meta = ref<Meta | null>(null)
const text = ref('')
const category = ref('')
const budget = ref('')
const brand = ref('')
const result = ref<AnalysisResult | null>(null)
const error = ref('')
const busy = ref(false)
/** 接口可能百毫秒内返回，加载条至少留 1.5s，让动效看得见；结果不延迟。 */
const { visible: progressVisible } = useLoadingBar(busy)
const { favorites, pending, loadError, load: loadFavorites, toggle: toggleFavoriteRaw } = useFavorites()

onMounted(async () => {
  try {
    meta.value = await api.get<Meta>('/meta')
  } catch {
    meta.value = null
  }
  await loadFavorites()
  if (loadError.value) error.value = loadError.value
})

async function toggleFavorite(productId: string) {
  try {
    await toggleFavoriteRaw(productId)
  } catch {
    error.value = '收藏操作失败，请稍后重试'
  }
}

async function run() {
  if (busy.value) return
  error.value = ''
  result.value = null
  busy.value = true
  try {
    result.value = await api.post<AnalysisResult>('/analysis', {
      text: text.value,
      category: category.value,
      budget: budget.value,
      brand: brand.value,
    })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '分析失败'
  } finally {
    busy.value = false
  }
}

function fillExample() {
  text.value = '5000 元以内，主要写代码，需要便携，14 寸左右'
  category.value = meta.value?.categories?.[0]?.key ?? ''
  budget.value = '5000'
}

function scoreText(item: ReportItem) {
  return typeof item.score_total === 'number' ? item.score_total.toFixed(0) : '—'
}
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">需求分析</span>
    <h1>智能分析</h1>
    <p>描述你的需求，也可以配合结构化控件把品类和预算说清楚。系统会把筛选依据和评分构成一并交给你。</p>
  </div>

  <div class="card">
    <div class="field">
      <label for="demand">描述需求</label>
      <textarea id="demand" v-model="text" class="textarea" placeholder="例如：5000 元以内，主要写代码，需要便携，14 寸左右" />
    </div>

    <div class="grid-3">
      <div class="field">
        <label for="cat">商品品类</label>
        <select id="cat" v-model="category" class="select">
          <option value="">未指定</option>
          <option v-for="c in meta?.categories ?? []" :key="c.key" :value="c.key">{{ c.label }}</option>
        </select>
      </div>
      <div class="field">
        <label for="budget">预算（元）</label>
        <input id="budget" v-model="budget" class="input" inputmode="numeric" placeholder="例如：5000" />
      </div>
      <div class="field">
        <label for="brand">品牌偏好</label>
        <select id="brand" v-model="brand" class="select">
          <option value="">不限</option>
          <option v-for="b in meta?.brands ?? []" :key="b" :value="b">{{ b }}</option>
        </select>
      </div>
    </div>

    <div class="row">
      <button class="btn btn-primary" :disabled="busy" @click="run">
        <span v-if="busy" class="spinner" /> {{ busy ? '分析中…' : '开始分析' }}
      </button>
      <button class="btn btn-ghost" :disabled="busy" @click="fillExample">填入示例</button>
      <span class="small muted">分析会保存为一条历史记录</span>
    </div>
    <div v-if="progressVisible" class="progress indeterminate" style="margin-top: 16px" role="progressbar" aria-label="正在分析">
      <span></span>
    </div>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>

  <!-- 信息不足时先请用户补充，不硬给结论 -->
  <div v-if="result?.status === 'need_info'" class="card">
    <h2>还需要补充一点信息</h2>
    <ul class="fact-list">
      <li v-for="(q, i) in result.questions ?? []" :key="i">{{ q }}</li>
    </ul>
    <p class="notice info" style="margin-top: 18px">
      可以在上面的品类 / 预算 / 品牌里补齐，或在需求文本里写得更具体，再点一次「开始分析」。
    </p>
  </div>

  <template v-if="result?.status === 'ok' && result.report">
    <div class="card">
      <div class="spread" style="margin-bottom: 18px">
        <div>
          <span class="eyebrow">首选方案</span>
          <h2 style="margin: 0">{{ result.report.demand_summary || '分析结果' }}</h2>
        </div>
        <span class="badge accent">{{ result.report.recommendations?.length ?? 0 }} 条推荐</span>
      </div>

      <div v-if="result.report.recommendations?.length" class="result-hero">
        <div class="result-score">{{ scoreText(result.report.recommendations[0]) }}</div>
        <div style="flex: 1; min-width: 240px">
          <div class="spread">
            <div class="product-title">{{ result.report.recommendations[0].name }}</div>
            <span class="price">{{ result.report.recommendations[0].price_label }}</span>
          </div>
          <div class="row" style="margin: 8px 0 12px">
            <span class="badge">{{ result.report.recommendations[0].match_level }}</span>
            <span class="badge">{{ result.report.recommendations[0].budget_label }}</span>
            <span class="badge" :class="result.report.recommendations[0].data_status === 'verified' ? 'green' : 'amber'">
              {{ result.report.recommendations[0].data_status === 'verified' ? '已核实' : '未核实' }}
            </span>
          </div>
          <ul class="fact-list">
            <li v-for="(r, i) in result.report.recommendations[0].reasons ?? []" :key="i">{{ r }}</li>
          </ul>
          <button
            class="btn btn-ghost btn-sm"
            style="margin-top: 12px"
            @click="toggleFavorite(result.report.recommendations[0].product_id)"
          >
            {{ pending.includes(result.report.recommendations[0].product_id) ? '处理中…' : (favorites.includes(result.report.recommendations[0].product_id) ? '取消收藏' : '收藏首选') }}
          </button>
        </div>
      </div>
      <div v-else class="empty"><strong>没有符合条件的商品</strong>试试放宽预算或品类。</div>
    </div>

    <div class="grid-2">
      <div class="card">
        <h2>需求与筛选依据</h2>
        <div v-if="result.report.demand_facts?.length" class="table-wrap" style="margin-bottom: 14px">
          <table>
            <tbody>
              <tr v-for="(fact, i) in result.report.demand_facts" :key="i">
                <th style="width: 38%">{{ fact[0] }}</th><td>{{ fact[1] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <ul v-if="result.report.filter_facts?.length" class="fact-list">
          <li v-for="(fact, i) in result.report.filter_facts" :key="i">{{ fact[0] }}：{{ fact[1] }}</li>
        </ul>
      </div>

      <div class="card">
        <h2>其他候选</h2>
        <div v-if="(result.report.recommendations?.length ?? 0) > 1" class="stack">
          <div v-for="(item, i) in result.report.recommendations!.slice(1)" :key="i" class="product-row">
            <div class="spread">
              <strong>{{ item.name }}</strong>
              <span class="price">{{ item.price_label }}</span>
            </div>
            <div class="spread">
              <span class="small muted">{{ item.score_total }} 分 · {{ item.match_level }}</span>
              <button class="btn btn-ghost btn-sm" @click="toggleFavorite(item.product_id)">
                {{ pending.includes(item.product_id) ? '处理中…' : (favorites.includes(item.product_id) ? '已收藏' : '收藏') }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="empty"><strong>没有更多候选</strong>当前条件下只筛出这一件。</div>

        <template v-if="result.report.over_budget?.length">
          <div class="divider"></div>
          <h3>超出预算但可参考</h3>
          <div v-for="(item, i) in result.report.over_budget" :key="i" class="product-row" style="margin-bottom: 8px">
            <div class="spread"><strong>{{ item.name }}</strong><span class="small">{{ item.price_label }}</span></div>
          </div>
        </template>
      </div>
    </div>

    <div class="card">
      <div class="grid-2">
        <div>
          <h2>结论</h2>
          <p class="answer" style="font-size: 13px">{{ result.report.conclusion || '—' }}</p>
        </div>
        <div>
          <h2>购买前请核实</h2>
          <ul class="fact-list">
            <li v-for="(t, i) in result.report.to_verify ?? []" :key="i">{{ t }}</li>
            <li v-if="!result.report.to_verify?.length">本次没有额外待核实项。</li>
          </ul>
        </div>
      </div>
      <p v-if="result.report.dataset_disclaimer" class="notice" style="margin-top: 18px">{{ result.report.dataset_disclaimer }}</p>
      <div v-if="result.report.notes?.length" class="divider"></div>
      <ul v-if="result.report.notes?.length" class="fact-list">
        <li v-for="(n, i) in result.report.notes" :key="i">{{ n }}</li>
      </ul>
    </div>
  </template>
</template>
