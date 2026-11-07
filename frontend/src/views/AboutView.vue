<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'

interface AboutInfo {
  name: string
  score_display_name: string
  categories: { key: string; label: string }[]
  product_count: number
  dataset_name: string
  disclaimer: string
  database_healthy: boolean
  database_message: string
  frontend: string
  backend: string
}

const info = ref<AboutInfo | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    info.value = await api.get<AboutInfo>('/about')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '信息加载失败'
  }
})
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">关于我们</span>
    <h1>关于智购参谋</h1>
    <p>它不替你决定买什么，只把依据、取舍和待核实项摊开，让决定由你自己做。</p>
  </div>

  <div class="card">
    <h2>这个项目做什么</h2>
    <p class="answer" style="font-size: 13.5px">
      输入预算、用途和偏好后，系统先做规则筛选与可解释评分，再生成一份决策报告：
      为什么筛掉、为什么排第一、哪些信息还没核实。分数叫「{{ info?.score_display_name ?? '综合匹配分' }}」，
      它是相对排序用的参考值，不是商品质量认证。
    </p>
  </div>

  <div class="grid-2">
    <div class="card">
      <h2>数据概况</h2>
      <div class="table-wrap">
        <table>
          <tbody>
            <tr><th>数据来源</th><td>{{ info?.dataset_name || '公开资料整理' }}</td></tr>
            <tr><th>在库商品</th><td>{{ info?.product_count ?? '—' }} 件</td></tr>
            <tr><th>覆盖品类</th><td>{{ info?.categories?.map((c) => c.label).join('、') || '—' }}</td></tr>
            <tr>
              <th>服务状态</th>
              <td>
                <span class="badge" :class="info?.database_healthy ? 'green' : 'amber'">
                  {{ info?.database_message ?? '检查中' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="error" class="notice error" style="margin-top: 14px">{{ error }}</p>
    </div>

    <div class="card">
      <h2>数据边界</h2>
      <ul class="fact-list">
        <li>在库商品数量有限，结论只在「这些商品之间比较」的意义上成立。</li>
        <li>价格与参数带核验状态，未核实的条目会明确标注。</li>
        <li>AI 回答可能出错，涉及具体参数与售后请到官方渠道确认。</li>
        <li>不收集手机号、邮箱等与选购无关的个人信息。</li>
      </ul>
      <p v-if="info?.disclaimer" class="notice" style="margin-top: 18px">{{ info.disclaimer }}</p>
    </div>
  </div>

  <div class="card">
    <h2>怎么用</h2>
    <div class="grid-3">
      <div class="product-row">
        <span class="badge accent">第 1 步</span>
        <strong>说清需求</strong>
        <span class="small muted">写下预算、用途、尺寸或品牌偏好，也可以只填品类和预算。</span>
      </div>
      <div class="product-row">
        <span class="badge accent">第 2 步</span>
        <strong>核对依据</strong>
        <span class="small muted">查看筛选过程、评分构成与待核实项，需要时补充信息再算一次。</span>
      </div>
      <div class="product-row">
        <span class="badge accent">第 3 步</span>
        <strong>做出决定</strong>
        <span class="small muted">横向比较候选、保存或导出报告，到官方渠道确认价格后下单。</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>常见问题</h2>
    <details class="faq-item">
      <summary>分数是怎么算出来的？</summary>
      <p>按预算匹配、用途匹配、性能适配、性价比、便携性等维度加权，不同品类权重不同。缺少参数的维度不参与计分并会注明原因。分数只代表本次需求下的相对排序，不是商品质量评级。</p>
    </details>
    <details class="faq-item">
      <summary>为什么有些商品单独列在「超出预算」？</summary>
      <p>不直接丢掉，方便你判断「多一点预算能换来什么」。是否展示超预算商品可以在偏好设置里调整。</p>
    </details>
    <details class="faq-item">
      <summary>页面上的价格是实时价吗？</summary>
      <p>不是。价格是按公开资料整理的参考值，会随促销变化；每条商品都标注核验状态。下单前请以官方渠道的实时价格为准。</p>
    </details>
    <details class="faq-item">
      <summary>AI 回答可以直接当结论吗？</summary>
      <p>不建议。AI 负责解释与表达，不参与筛选和评分；涉及具体参数、保修与库存时，请到官方渠道核实。问答页面会标明每条回答的依据来源。</p>
    </details>
    <details class="faq-item">
      <summary>我的分析记录会保存在哪里？</summary>
      <p>记录与收藏按账号保存在本地，可以在「我的记录」里查看、导出或删除。管理员可统一管理全站记录。</p>
    </details>
  </div>
</template>
