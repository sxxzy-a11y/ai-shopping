<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, ApiError } from '../api/client'
import { formatDateTime } from '../utils/format'

interface UserRow {
  username: string
  role: string
  is_active: boolean
  created_at: string
}

const users = ref<UserRow[]>([])
const error = ref('')
const notice = ref('')
const busy = ref(false)
const showCreate = ref(false)
const createForm = reactive({ username: '', password: '', role: 'user' })
const passwordFor = ref('')
const newPassword = ref('')

const admins = computed(() => users.value.filter((u) => u.role === 'admin').length)

async function load() {
  error.value = ''
  try {
    const data = await api.get<{ users: UserRow[] }>('/admin/users')
    users.value = data.users
    // 刷新后该行可能已不存在，改密码输入框要一起收起，
    // 否则它会挂到列表里下一个同名位置之外的任意行上。
    passwordFor.value = ''
    newPassword.value = ''
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '账号列表加载失败'
  }
}

async function createUser() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api.post('/admin/users', createForm)
    notice.value = `已创建账号「${createForm.username}」。`
    createForm.username = ''
    createForm.password = ''
    createForm.role = 'user'
    showCreate.value = false
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '创建失败'
  } finally {
    busy.value = false
  }
}

async function changeRole(row: UserRow) {
  try {
    await api.put(`/admin/users/${encodeURIComponent(row.username)}/role`, { role: row.role })
    notice.value = `已将「${row.username}」设为${row.role === 'admin' ? '管理员' : '普通用户'}。`
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '改角色失败（最后一个管理员不能降级）'
    await load()
  }
}

async function toggleActive(row: UserRow) {
  try {
    await api.put(`/admin/users/${encodeURIComponent(row.username)}/active`, {
      is_active: !row.is_active,
    })
    notice.value = `已${row.is_active ? '停用' : '启用'}「${row.username}」。`
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
    await load()
  }
}

async function resetPassword(username: string) {
  // 输入框 label 已声明「至少 8 位」，这里先按同一口径拦一次，
  // 免得把校验完全丢给服务端、只能得到一句泛化的 400。
  if (newPassword.value.trim().length < 8) {
    error.value = '新密码至少 8 位。'
    return
  }
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api.put(`/admin/users/${encodeURIComponent(username)}/password`, {
      password: newPassword.value,
    })
    notice.value = `已重置「${username}」的密码。`
    passwordFor.value = ''
    newPassword.value = ''
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '重置失败'
  } finally {
    busy.value = false
  }
}

async function remove(row: UserRow) {
  if (busy.value) return
  if (!confirm(`确定删除账号「${row.username}」吗？该账号的历史、收藏与偏好会一并删除，且不可恢复。`)) return
  busy.value = true
  error.value = ''
  try {
    const data = await api.delete<{ deleted_histories: number; deleted_favorites: number }>(
      `/admin/users/${encodeURIComponent(row.username)}`
    )
    notice.value = `已删除「${row.username}」（历史 ${data.deleted_histories} 条、收藏 ${data.deleted_favorites} 条）。`
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败（不能删自己或最后一个管理员）'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <span class="eyebrow">账号管理</span>
    <h1>用户管理</h1>
    <p>管理可登录的账号与权限。删除账号会同时清除其分析记录与收藏，操作前请先确认。</p>
  </div>

  <div class="grid-3" style="margin-bottom: 20px">
    <div class="stat accent"><div class="value">{{ users.length }}</div><div class="label">账号总数</div></div>
    <div class="stat"><div class="value">{{ admins }}</div><div class="label">管理员</div></div>
    <div class="stat"><div class="value">{{ users.length - admins }}</div><div class="label">普通用户</div></div>
  </div>

  <p v-if="error" class="notice error">{{ error }}</p>
  <p v-if="notice" class="notice info">{{ notice }}</p>

  <div class="card">
    <div class="spread" style="margin-bottom: 16px">
      <h2 style="margin: 0">账号清单</h2>
      <button class="btn btn-primary btn-sm" @click="showCreate = !showCreate">新建账号</button>
    </div>

    <div v-if="showCreate" class="card" style="background: var(--surface-soft); margin-bottom: 18px">
      <h2>新建账号</h2>
      <div class="grid-3">
        <div class="field"><label for="u-name">用户名</label><input id="u-name" v-model="createForm.username" class="input" /></div>
        <div class="field"><label for="u-pass">初始密码（至少 8 位）</label><input id="u-pass" v-model="createForm.password" class="input" type="password" /></div>
        <div class="field">
          <label for="u-role">角色</label>
          <select id="u-role" v-model="createForm.role" class="select">
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
        </div>
      </div>
      <button class="btn btn-primary" :disabled="busy" @click="createUser">
        <span v-if="busy" class="spinner" /> 确认创建
      </button>
    </div>

    <div v-if="users.length" class="table-wrap">
      <table>
        <thead><tr><th>用户名</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="u in users" :key="u.username">
            <td><strong>{{ u.username }}</strong></td>
            <td>
              <select v-model="u.role" class="select" style="width: 118px; padding: 6px 26px 6px 9px" @change="changeRole(u)">
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
            </td>
            <td><span class="badge" :class="u.is_active ? 'green' : 'amber'">{{ u.is_active ? '启用' : '停用' }}</span></td>
            <td class="small">{{ formatDateTime(u.created_at) || '—' }}</td>
            <td>
              <div class="row" style="gap: 6px; flex-wrap: nowrap">
                <button class="btn btn-ghost btn-sm" @click="toggleActive(u)">{{ u.is_active ? '停用' : '启用' }}</button>
                <button class="btn btn-ghost btn-sm" @click="passwordFor = u.username; newPassword = ''">改密码</button>
                <button class="btn btn-ghost btn-sm" @click="remove(u)">删除</button>
              </div>
              <div v-if="passwordFor === u.username" class="row" style="margin-top: 8px; flex-wrap: nowrap">
                <input v-model="newPassword" class="input" type="password" placeholder="新密码（至少 8 位）" style="max-width: 210px" />
                <button class="btn btn-primary btn-sm" @click="resetPassword(u.username)">确认</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty"><strong>暂无账号</strong>新建账号后会出现在这里。</div>
    <p class="notice" style="margin-top: 18px">
      密码始终加密保存，页面不会显示。为保障系统可用，不能删除当前登录的账号，也不能停用最后一位管理员。
    </p>
  </div>
</template>
