<script setup lang="ts">
import { ref } from 'vue'
import { useSession } from '../stores/session'

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
      <div class="login-brand">
        <div class="mark">智</div>
        <div>
          <h1>智购参谋</h1>
        </div>
      </div>
      <p class="login-sub">SMARTBUY ADVISOR</p>

      <form @submit.prevent="submit">
        <div class="field">
          <label for="username">用户名</label>
          <input id="username" v-model="username" class="input" autocomplete="username" placeholder="请输入用户名" required />
        </div>
        <div class="field">
          <label for="password">密码</label>
          <input id="password" v-model="password" class="input" type="password" autocomplete="current-password" placeholder="请输入密码" required />
        </div>

        <p v-if="session.error" class="notice error" style="margin-bottom: 14px">{{ session.error }}</p>

        <button class="btn btn-primary btn-block" type="submit" :disabled="busy">
          <span v-if="busy" class="spinner" /> {{ busy ? '登录中…' : '登录' }}
        </button>
      </form>

      <div class="divider"></div>
      <p class="small muted" style="margin: 0; line-height: 1.7">
        为保障账号安全，长时间未操作后需要重新登录。<br />
        商品价格与参数为整理所得参考值，请以官方渠道为准。
      </p>
    </div>
  </div>
</template>
