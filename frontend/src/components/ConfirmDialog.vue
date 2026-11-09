<script setup lang="ts">
import { useConfirm } from '../composables/useConfirm'

const { current, settle } = useConfirm()
</script>

<template>
  <div
    v-if="current"
    style="position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 20px; background: rgba(8, 15, 30, 0.55)"
    @click.self="settle(false)"
  >
    <div class="card" role="dialog" aria-modal="true" style="width: 100%; max-width: 460px">
      <h2 style="margin-top: 0">请确认</h2>
      <p>{{ current.message }}</p>
      <div class="row" style="justify-content: flex-end; gap: 8px; margin-top: 20px">
        <button class="btn btn-ghost" type="button" @click="settle(false)">取消</button>
        <button class="btn btn-primary" type="button" @click="settle(true)">
          {{ current.confirmText }}
        </button>
      </div>
    </div>
  </div>
</template>
