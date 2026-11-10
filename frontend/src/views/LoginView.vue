<script setup lang="ts">
import { ref } from 'vue'
import { useSession } from '../stores/session'

// 登录页视觉按 Uiverse.io by D3OXY（MIT）的硬边阴影表单风格重做，
// 交互逻辑不变：用户名 + 密码提交到 session.login。
const session = useSession()
const username = ref('')
const password = ref('')
const busy = ref(false)

async function submit() {
  if (busy.value) return
  busy.value = true
  await session.login(username.value, password.value)
  busy.value = false
}
</script>

<template>
  <div class="login-screen">
    <div class="login-card">
      <p class="login-title">
        智购参谋
        <span>SMARTBUY ADVISOR</span>
      </p>

      <div class="login-separator" aria-hidden="true">
        <div></div>
        <span>账号登录</span>
        <div></div>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <input
          id="username"
          v-model="username"
          class="login-input"
          autocomplete="username"
          placeholder="用户名"
          aria-label="用户名"
          required
        />
        <input
          id="password"
          v-model="password"
          class="login-input"
          type="password"
          autocomplete="current-password"
          placeholder="密码"
          aria-label="密码"
          required
        />

        <p v-if="session.error" class="login-error">{{ session.error }}</p>

        <button class="login-submit" type="submit" :disabled="busy">
          <span v-if="busy" class="spinner" />
          {{ busy ? '登录中…' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>
