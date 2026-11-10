<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { UNAUTHORIZED_EVENT } from './api/client'
import { LOGGED_IN_EVENT, useSession } from './stores/session'
import LoginView from './views/LoginView.vue'
import AppShell from './components/AppShell.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import CoffeeSplash from './components/CoffeeSplash.vue'
import { useInitialLoad } from './composables/useInitialLoad'

const { loading: initialLoading } = useInitialLoad()

// 会话恢复统一交给路由守卫（见 router/index.ts）。放在这里会和守卫
// 各发一次 /auth/me，登录页首屏因此多一次无谓请求。
const session = useSession()
const router = useRouter()

// 咖啡杯载入画面只保留两段真实需要的过渡：
// 1) 进入页面 → 登录页：至少 1.8s，会话没就绪就一直显示，登录页随后淡入；
// 2) 登录页 → 主页面：主动登录成功后 1.4s。
// 侧栏切页不再有覆盖层的过渡。都只是「视觉最短展示」，不阻塞任何请求。
const BOOT_SPLASH_MS = 1800
const LOGIN_SPLASH_MS = 1400

const bootMinimumDone = ref(false)
const bootSplash = computed(() => !bootMinimumDone.value || !session.ready)
const loginSplash = ref(false)
const splashVisible = computed(() => bootSplash.value || loginSplash.value)
const splashMessage = computed(() => {
  if (loginSplash.value) return '登录成功，正在进入…'
  if (!session.ready) return '正在连接服务，先喝口咖啡…'
  return session.user ? '正在进入，先喝口咖啡…' : '正在打开登录页面…'
})

let bootTimer: number | undefined
let loginTimer: number | undefined

function onLoggedIn() {
  if (!session.user) return
  loginSplash.value = true
  if (loginTimer !== undefined) window.clearTimeout(loginTimer)
  loginTimer = window.setTimeout(() => { loginSplash.value = false }, LOGIN_SPLASH_MS)
}

// 会话过期的统一出口：并发请求可能同时返回 401，用 user 判空去重。
function onUnauthorized() {
  if (!session.user) return
  session.clearLocal()
  void router.replace('/')
}

onMounted(() => {
  bootTimer = window.setTimeout(() => { bootMinimumDone.value = true }, BOOT_SPLASH_MS)
  window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  window.addEventListener(LOGGED_IN_EVENT, onLoggedIn)
})
onUnmounted(() => {
  if (bootTimer !== undefined) window.clearTimeout(bootTimer)
  if (loginTimer !== undefined) window.clearTimeout(loginTimer)
  window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  window.removeEventListener(LOGGED_IN_EVENT, onLoggedIn)
})
</script>

<template>
  <LoginView v-if="session.ready && !session.user" />
  <AppShell v-else-if="session.ready && session.user" />
  <ConfirmDialog />
  <!-- 顶部细进度条：只提示「正在加载」，不遮挡内容。 -->
  <div
    v-if="initialLoading && session.ready && session.user"
    class="route-progress"
    aria-hidden="true"
  />
  <Transition name="coffee-splash-fade">
    <CoffeeSplash v-if="splashVisible" :message="splashMessage" />
  </Transition>
</template>
