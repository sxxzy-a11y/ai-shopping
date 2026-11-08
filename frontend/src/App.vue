<script setup lang="ts">
import { useSession } from './stores/session'
import LoginView from './views/LoginView.vue'
import AppShell from './components/AppShell.vue'

// 会话恢复统一交给路由守卫（见 router/index.ts）。放在这里会和守卫
// 各发一次 /auth/me，登录页首屏因此多一次无谓请求。
const session = useSession()
</script>

<template>
  <div v-if="!session.ready" class="boot-screen">
    <div class="boot-mark">智</div>
    <p>正在连接服务…</p>
  </div>
  <LoginView v-else-if="!session.user" />
  <AppShell v-else />
</template>
