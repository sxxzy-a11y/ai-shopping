<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSession } from '../stores/session'
import AppIcon from './AppIcon.vue'

interface NavItem {
  label: string
  to: string
  icon: string
  admin?: boolean
}

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: '选购工作台',
    items: [
      { label: '首页', to: '/', icon: 'home' },
      { label: '智能分析', to: '/analysis', icon: 'insights' },
      { label: '商品比较', to: '/compare', icon: 'compare' },
      { label: 'AI 问答', to: '/qa', icon: 'chat' },
      { label: '历史记录', to: '/history', icon: 'history' },
    ],
  },
  {
    label: '管理',
    items: [
      { label: '商品维护', to: '/catalog', icon: 'inventory', admin: true },
      { label: '知识库管理', to: '/knowledge-admin', icon: 'book', admin: true },
      { label: '全站概览', to: '/overview', icon: 'analytics', admin: true },
      { label: '用户管理', to: '/users', icon: 'group', admin: true },
      { label: '效果评测', to: '/eval', icon: 'check', admin: true },
    ],
  },
  {
    label: '其他',
    items: [
      { label: '个人设置', to: '/settings', icon: 'tune' },
      { label: '关于', to: '/about', icon: 'info' },
    ],
  },
]

const session = useSession()
const route = useRoute()
const router = useRouter()

const visibleGroups = computed(() =>
  groups
    .map((group) => ({
      label: group.label,
      items: group.items.filter((item) => !item.admin || session.user?.is_admin),
    }))
    .filter((group) => group.items.length > 0),
)
const title = computed(() => String(route.meta.title ?? '智购参谋'))

async function logout() {
  await session.logout()
  router.replace('/')
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="mark">智</div>
        <div>
          <strong>智购参谋</strong>
          <small>SMARTBUY ADVISOR</small>
        </div>
      </div>

      <div v-for="group in visibleGroups" :key="group.label" class="nav-group">
        <div class="nav-label">{{ group.label }}</div>
        <RouterLink
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          exact-active-class="active"
        >
          <AppIcon :name="item.icon" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </div>

      <div class="sidebar-foot">
        <div class="user-chip">
          <div class="avatar">{{ session.user?.username?.slice(0, 1).toUpperCase() }}</div>
          <div>
            <strong>{{ session.user?.username }}</strong>
            <small>{{ session.user?.role_label }}</small>
          </div>
        </div>
        <button class="logout-btn" type="button" @click="logout">
          <AppIcon name="logout" /> 退出登录
        </button>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="crumb">智购参谋 / <b>{{ title }}</b></div>
        <div class="row">
          <span class="mode-chip"><AppIcon name="shield" /> 参考价数据 · 购买前请核实</span>
          <span class="badge">{{ session.user?.role_label }}</span>
        </div>
      </header>
      <div class="page"><RouterView /></div>
      <footer class="app-footer">
        <span>© 2026 智购参谋 · 商品信息为整理所得参考值，不构成购买建议</span>
        <span class="row" style="gap: 12px">
          <RouterLink to="/about">关于与数据说明</RouterLink>
          <span class="muted">版本 2.8</span>
        </span>
      </footer>
    </main>
  </div>
</template>
