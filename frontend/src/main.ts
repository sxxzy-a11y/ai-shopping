import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/index.css'

const app = createApp(App)

// 兜底错误出口。没有它，渲染期异常和未捕获的 Promise 拒绝在控制台之外
// 完全无痕，线上只能看到「页面白了一下」。
// 统一加前缀，便于浏览器巡检脚本按关键字识别。
app.config.errorHandler = (err, _instance, info) => {
  console.error('[zhigou] 组件错误:', info, err)
}

window.addEventListener('unhandledrejection', (event) => {
  console.error('[zhigou] 未处理的异步错误:', event.reason)
})

app.use(createPinia()).use(router).mount('#app')
