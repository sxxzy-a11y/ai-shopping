<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { UNAUTHORIZED_EVENT } from './api/client'
import { useSession } from './stores/session'
import LoginView from './views/LoginView.vue'
import AppShell from './components/AppShell.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import BrandMark from './components/BrandMark.vue'
import { useInitialLoad } from './composables/useInitialLoad'

const { loading: initialLoading } = useInitialLoad()

// 会话恢复统一交给路由守卫（见 router/index.ts）。放在这里会和守卫
// 各发一次 /auth/me，登录页首屏因此多一次无谓请求。
const session = useSession()
const router = useRouter()

// 会话过期的统一出口：并发请求可能同时返回 401，用 user 判空去重。
function onUnauthorized() {
  if (!session.user) return
  session.clearLocal()
  void router.replace('/')
}

onMounted(() => window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized))
onUnmounted(() => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized))
</script>

<template>
  <div v-if="!session.ready" class="boot-screen">
    <BrandMark :size="56" tone="light" />
    <p>正在连接服务…</p>
  </div>
  <LoginView v-else-if="!session.user" />
  <AppShell v-else />
  <ConfirmDialog />
  <!-- 顶部细进度条：只提示「正在加载」，不遮挡内容。
       原先这里是全屏 rgba(255,255,255,.82) 遮罩，任何一次导航都会整页发白一下。 -->
  <div
    v-if="initialLoading && session.ready && session.user"
    class="route-progress"
    aria-hidden="true"
  />
</template>
