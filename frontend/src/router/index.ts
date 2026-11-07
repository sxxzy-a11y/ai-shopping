import { createRouter, createWebHashHistory } from 'vue-router'

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

export default router
