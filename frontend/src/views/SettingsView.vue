<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, ApiError } from '../api/client'
import { useConfirm } from '../composables/useConfirm'
import type { Preferences } from '../api/types'
import { useSession } from '../stores/session'
import { toNumberOrUndefined } from '../utils/format'

interface ApiConfigView {
  values: Record<string, string>
  sources: Record<string, string>
  configured: { llm: boolean; embedding: boolean }
  masked_keys: string[]
}

interface ProbeResult { ok: boolean; message: string }

const session = useSession()
const isAdmin = computed(() => Boolean(session.user?.is_admin))

const prefs = ref<Preferences>({ ai_enhanced: true, price_priority: 'none', show_over_budget: true, auto_apply: true })
const message = ref('')
const error = ref('')
const busy = ref(false)

const cfg = ref<ApiConfigView | null>(null)
const cfgForm = reactive({
  llm_base_url: '', llm_model: '', llm_api_key: '',
  embedding_base_url: '', embedding_model: '', embedding_dim: '', embedding_api_key: '',
})
const probeLlm = ref<ProbeResult | null>(null)
const probeEmb = ref<ProbeResult | null>(null)
const probeBusy = ref('')
const cfgMessage = ref('')
const cfgError = ref('')
const cfgBusy = ref(false)
const cfgLoading = ref(false)

onMounted(async () => {
  try {
    prefs.value = await api.get<Preferences>('/preferences')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '偏好加载失败'
  }
  if (isAdmin.value) await loadConfig()
})

async function loadConfig() {
  cfgLoading.value = true
  cfgError.value = ''
  try {
    cfg.value = await api.get<ApiConfigView>('/admin/api-config')
    cfgForm.llm_base_url = cfg.value.values.llm_base_url ?? ''
    cfgForm.llm_model = cfg.value.values.llm_model ?? ''
    cfgForm.embedding_base_url = cfg.value.values.embedding_base_url ?? ''
    cfgForm.embedding_model = cfg.value.values.embedding_model ?? ''
    cfgForm.embedding_dim = cfg.value.values.embedding_dim ?? ''
    cfgForm.llm_api_key = ''
    cfgForm.embedding_api_key = ''
  } catch (err) {
    // 失败时 `cfg` 保持 null。没有独立的加载态，模板会一直显示
    // 「正在读取设置…」，管理员会以为它在转，其实早就失败了。
    cfgError.value = err instanceof ApiError ? err.message : '设置读取失败'
  } finally {
    cfgLoading.value = false
  }
}

async function save() {
  if (busy.value) return
  busy.value = true
  message.value = ''
  error.value = ''
  try {
    prefs.value = await api.put<Preferences>('/preferences', prefs.value)
    message.value = '偏好已保存，下一次分析会按新设置执行。'
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    busy.value = false
  }
}

async function saveConfig() {
  if (cfgBusy.value) return
  cfgBusy.value = true
  cfgError.value = ''
  cfgMessage.value = ''
  const payload: Record<string, string | number> = {
    llm_base_url: cfgForm.llm_base_url,
    llm_model: cfgForm.llm_model,
    embedding_base_url: cfgForm.embedding_base_url,
    embedding_model: cfgForm.embedding_model,
  }
  if (cfgForm.llm_api_key.trim()) payload.llm_api_key = cfgForm.llm_api_key
  if (cfgForm.embedding_api_key.trim()) payload.embedding_api_key = cfgForm.embedding_api_key
  // 用安全解析：`Number('abc')` 会得到 NaN，序列化成 null 静默提交。
  const dim = toNumberOrUndefined(cfgForm.embedding_dim)
  if (dim !== undefined) payload.embedding_dim = dim
  try {
    cfg.value = await api.put<ApiConfigView>('/admin/api-config', payload)
    cfgMessage.value = '已保存。新配置从下一次请求开始生效。'
    // 配置已变，此前的连接检测结论不再适用，必须清掉避免误导。
    probeLlm.value = null
    probeEmb.value = null
    cfgForm.llm_api_key = ''
    cfgForm.embedding_api_key = ''
  } catch (err) {
    cfgError.value = err instanceof ApiError ? err.message : '配置保存失败'
  } finally {
    cfgBusy.value = false
  }
}

async function clearConfig() {
  // 与 saveConfig 共用同一个在途标志：两者都会覆写服务端配置，
  // 同时进行时后返回的那次会盖掉前一次的界面状态。
  if (cfgBusy.value) return
  if (!(await useConfirm().ask('确定恢复为环境变量 / 默认配置吗？本机覆盖文件会被删除。', '恢复默认'))) return
  cfgBusy.value = true
  cfgError.value = ''
  try {
    cfg.value = await api.delete<ApiConfigView>('/admin/api-config')
    cfgMessage.value = '已恢复为环境变量 / 默认配置。'
    // 恢复默认后连接目标可能完全不同，旧探测结果必须作废。
    probeLlm.value = null
    probeEmb.value = null
    Object.assign(cfgForm, {
      llm_base_url: cfg.value.values.llm_base_url, llm_model: cfg.value.values.llm_model,
      llm_api_key: '', embedding_base_url: cfg.value.values.embedding_base_url,
      embedding_model: cfg.value.values.embedding_model,
      embedding_dim: cfg.value.values.embedding_dim, embedding_api_key: '',
    })
  } catch (err) {
    cfgError.value = err instanceof ApiError ? err.message : '恢复失败'
  } finally {
    cfgBusy.value = false
  }
}

async function runProbe(kind: 'llm' | 'embedding') {
  probeBusy.value = kind
  try {
    const result = await api.post<ProbeResult>(`/admin/api-config/probe/${kind}`, {})
    if (kind === 'llm') probeLlm.value = result
    else probeEmb.value = result
  } catch (err) {
    const failed: ProbeResult = { ok: false, message: err instanceof Error ? err.message : '检测失败' }
    if (kind === 'llm') probeLlm.value = failed
    else probeEmb.value = failed
  } finally {
    probeBusy.value = ''
  }
}
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">偏好设置</span>
    <h1>个人设置</h1>
    <p>偏好只作用于你自己的账号；管理员还可以在这里配置模型并做连接检测。</p>
  </div>

  <div class="grid-2">
    <div class="card">
      <h2>分析偏好</h2>
      <div class="field">
        <label for="priority">价格取向</label>
        <select id="priority" v-model="prefs.price_priority" class="select">
          <option value="none">不限</option>
          <option value="value">性价比优先</option>
          <option value="performance">性能优先</option>
          <option value="brand">品牌优先</option>
        </select>
        <span class="hint">只影响缺省条件，不改写你手填的预算或品类。</span>
      </div>

      <label class="check-item" style="margin-bottom: 10px">
        <input v-model="prefs.ai_enhanced" type="checkbox" />
        <span><strong>启用 AI 增强</strong><br /><span class="small muted">已配置模型时，用于需求解析与问答</span></span>
      </label>
      <label class="check-item" style="margin-bottom: 10px">
        <input v-model="prefs.show_over_budget" type="checkbox" />
        <span><strong>展示超预算商品</strong><br /><span class="small muted">关掉后结果只保留预算内</span></span>
      </label>
      <label class="check-item">
        <input v-model="prefs.auto_apply" type="checkbox" />
        <span><strong>分析时自动带上偏好</strong><br /><span class="small muted">关掉后完全按本次输入计算</span></span>
      </label>

      <div style="margin-top: 20px">
        <button class="btn btn-primary" :disabled="busy" @click="save">
          <span v-if="busy" class="spinner" /> 保存设置
        </button>
      </div>
      <p v-if="message" class="notice info" style="margin-top: 14px">{{ message }}</p>
      <p v-if="error" class="notice error" style="margin-top: 14px">{{ error }}</p>
    </div>

    <div class="card">
      <h2>数据与会话</h2>
      <ul class="fact-list">
        <li>你的偏好只按账号保存，不会用于其他用途。</li>
        <li>登录满 12 小时、或连续 30 分钟没有操作后，需要重新登录。</li>
        <li>模型服务密钥只保存在服务端，不会出现在页面中。</li>
        <li>商品价格是整理所得参考值，均标注核验状态，不代表实时成交价。</li>
      </ul>
      <div class="divider"></div>
      <p v-if="cfg" class="small muted">
        模型状态：对话模型
        <span class="badge" :class="cfg.configured.llm ? 'green' : 'amber'">{{ cfg.configured.llm ? '已配置' : '未配置' }}</span>
        · 向量化
        <span class="badge" :class="cfg.configured.embedding ? 'green' : 'amber'">{{ cfg.configured.embedding ? '已配置' : '未配置' }}</span>
      </p>
    </div>
  </div>

  <!-- 管理员：模型服务设置 -->
  <div v-if="isAdmin" class="card">
    <div class="spread" style="margin-bottom: 6px">
      <h2 style="margin: 0">模型服务设置</h2>
      <span class="badge accent">仅管理员</span>
    </div>
    <p class="small muted">密钥留空表示不修改。配置安全保存在服务端，页面只显示掩码，可随时检测是否连通。</p>

    <div v-if="cfg" class="grid-2" style="margin-top: 18px">
      <div>
        <h3>对话模型</h3>
        <div class="field">
          <label for="llm-base">端点</label>
          <input id="llm-base" v-model="cfgForm.llm_base_url" class="input" />
          <span class="hint">来源：{{ cfg.sources.llm_base_url }}</span>
        </div>
        <div class="field">
          <label for="llm-model">模型名</label>
          <input id="llm-model" v-model="cfgForm.llm_model" class="input" />
        </div>
        <div class="field">
          <label for="llm-key">密钥</label>
          <input id="llm-key" v-model="cfgForm.llm_api_key" class="input" type="password" placeholder="留空表示不修改" />
          <span class="hint">当前：{{ cfg.values.llm_api_key }}</span>
        </div>
        <button class="btn btn-ghost btn-sm" :disabled="probeBusy === 'llm'" @click="runProbe('llm')">
          <span v-if="probeBusy === 'llm'" class="spinner" /> 测试对话连接
        </button>
        <p v-if="probeLlm" class="notice" :class="probeLlm.ok ? 'info' : 'error'" style="margin-top: 12px">{{ probeLlm.message }}</p>
      </div>

      <div>
        <h3>语义检索服务</h3>
        <div class="field">
          <label for="emb-base">端点</label>
          <input id="emb-base" v-model="cfgForm.embedding_base_url" class="input" />
          <span class="hint">来源：{{ cfg.sources.embedding_base_url }}</span>
        </div>
        <div class="field">
          <label for="emb-model">模型名</label>
          <input id="emb-model" v-model="cfgForm.embedding_model" class="input" />
        </div>
        <div class="field">
          <label for="emb-dim">向量维度</label>
          <input id="emb-dim" v-model="cfgForm.embedding_dim" class="input" inputmode="numeric" />
        </div>
        <div class="field">
          <label for="emb-key">密钥</label>
          <input id="emb-key" v-model="cfgForm.embedding_api_key" class="input" type="password" placeholder="留空表示不修改" />
          <span class="hint">当前：{{ cfg.values.embedding_api_key }}</span>
        </div>
        <button class="btn btn-ghost btn-sm" :disabled="probeBusy === 'embedding'" @click="runProbe('embedding')">
          <span v-if="probeBusy === 'embedding'" class="spinner" /> 测试向量化连接
        </button>
        <p v-if="probeEmb" class="notice" :class="probeEmb.ok ? 'info' : 'error'" style="margin-top: 12px">{{ probeEmb.message }}</p>
      </div>
    </div>
    <p v-else-if="cfgLoading" class="loading"><span class="spinner" /> 正在读取设置…</p>
    <p v-else class="small muted" style="margin-top: 18px">
      设置未能读取。
      <button class="btn btn-ghost btn-sm" style="margin-left: 6px" @click="loadConfig">重新读取</button>
    </p>

    <div class="divider"></div>
    <div class="row">
      <button class="btn btn-primary" :disabled="cfgBusy" @click="saveConfig">
        <span v-if="cfgBusy" class="spinner" /> 保存设置
      </button>
      <button class="btn btn-ghost" :disabled="cfgBusy" @click="clearConfig">恢复默认设置</button>
    </div>
    <p v-if="cfgMessage && !cfgError" class="notice info" style="margin-top: 14px">{{ cfgMessage }}</p>
    <p v-if="cfgError" class="notice error" style="margin-top: 14px">{{ cfgError }}</p>
  </div>
</template>
