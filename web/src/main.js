import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './styles/main.css'

const routes = [
  { path: '/', component: () => import('./views/FarmView.vue'), meta: { title: '임가 진단' } },
  { path: '/item', component: () => import('./views/ItemView.vue'), meta: { title: '품목 정밀' } },
  { path: '/shipping', component: () => import('./views/ShippingView.vue'), meta: { title: '출하 전략' } },
  { path: '/market', component: () => import('./views/MarketView.vue'), meta: { title: '시장·단가' } },
  { path: '/insight', component: () => import('./views/InsightView.vue'), meta: { title: '수익 개선' } },
  { path: '/model', component: () => import('./views/ModelView.vue'), meta: { title: '모델 성능' } },
  { path: '/about', component: () => import('./views/AboutView.vue'), meta: { title: '데이터·방법론' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = to.meta?.title
    ? `${to.meta.title} · 임가 수익성 분석 플랫폼`
    : '임가 수익성 분석 플랫폼'
})

createApp(App).use(router).mount('#app')
