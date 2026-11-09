import { createRouter, createWebHashHistory } from 'vue-router'
import { useSession } from '../stores/session'

// hash 路由：静态部署时无需额外的服务端路由配置。
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue'), meta: { title: '首页' } },
    { path: '/analysis', name: 'analysis', component: () => import('../views/AnalysisView.vue'), meta: { title: '智能分析' } },
    { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue'), meta: { title: '商品比较' } },
    { path: '/qa', name: 'qa', component: () => import('../views/QAView.vue'), meta: { title: 'AI 问答' } },
    { path: '/history', name: 'history', component: () => import('../views/HistoryView.vue'), meta: { title: '历史记录' } },
    { path: '/catalog', name: 'catalog', component: () => import('../views/CatalogView.vue'), meta: { title: '商品维护', admin: true } },
    { path: '/knowledge-admin', name: 'knowledge-admin', component: () => import('../views/KnowledgeAdminView.vue'), meta: { title: '知识库管理', admin: true } },
    { path: '/overview', name: 'overview', component: () => import('../views/OverviewView.vue'), meta: { title: '全站概览', admin: true } },
    { path: '/users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { title: '用户管理', admin: true } },
    { path: '/eval', name: 'eval', component: () => import('../views/EvalView.vue'), meta: { title: '效果评测', admin: true } },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { title: '个人设置' } },
    { path: '/about', name: 'about', component: () => import('../views/AboutView.vue'), meta: { title: '关于' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 权限守卫：侧栏隐藏入口只是界面层，手动改 hash 仍能进 /users 等管理页。
// 真正的权限判定在后端（`AdminUser` 依赖），这里只避免普通用户落到满屏 403。
router.beforeEach(async (to) => {
  const session = useSession()
  if (!session.ready) await session.restore()
  if (to.meta.admin && !session.user?.is_admin) return { path: '/' }
  return true
})

/**
 * 预加载目标路由的代码块。
 *
 * 所有页面都是 `() => import(...)` 懒加载，首次进入要等网络往返 —— 这就是
 * 点导航时「先空一下再出现」的另一半原因。悬停/聚焦时提前触发同一个 import，
 * 浏览器与 Vite 都会缓存该模块，真正点击时基本是同步渲染。
 */
export function preloadRoute(path: string): void {
  try {
    const loader = router.resolve(path).matched[0]?.components?.default
    // 只有懒加载函数能当 Promise 用；同步/函数式组件调用后返回的是 VNode，
    // 直接 `.catch()` 会抛 TypeError。先探测返回值再决定要不要吞异常。
    if (typeof loader !== 'function') return
    const result = (loader as () => unknown)()
    if (result && typeof (result as Promise<unknown>).then === 'function') {
      void (result as Promise<unknown>).catch(() => {
        /* 预加载失败无所谓，点击时还会再试一次 */
      })
    }
  } catch {
    /* 路由解析失败同样忽略，不能让悬停动作影响导航 */
  }
}

export default router
