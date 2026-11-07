<script setup lang="ts">
import { onMounted } from 'vue'
import { useSession } from './stores/session'
import LoginView from './views/LoginView.vue'
import AppShell from './components/AppShell.vue'

const session = useSession()
onMounted(() => session.restore())
</script>

<template>
  <div v-if="!session.ready" class="boot-screen">
    <div class="boot-mark">智</div>
    <p>正在连接服务…</p>
  </div>
  <LoginView v-else-if="!session.user" />
  <AppShell v-else />
</template>
