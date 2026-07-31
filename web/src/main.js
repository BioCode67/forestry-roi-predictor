import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './styles/main.css'

const routes = [
  { path: '/', component: () => import('./views/HomeView.vue'), meta: { title: '내 산 수익 알아보기' } },
  { path: '/detail', component: () => import('./views/FarmView.vue'), meta: { title: '자세한 진단' } },
  { path: '/item', component: () => import('./views/ItemView.vue'), meta: { title: '작물별 자세히' } },
  { path: '/shipping', component: () => import('./views/ShippingView.vue'), meta: { title: '언제 팔면 좋을까' } },
  { path: '/market', component: () => import('./views/MarketView.vue'), meta: { title: '내 작물 값은 얼마' } },
  { path: '/insight', component: () => import('./views/InsightView.vue'), meta: { title: '어떻게 더 벌까' } },
  { path: '/model', component: () => import('./views/ModelView.vue'), meta: { title: '예측이 얼마나 맞나' } },
  { path: '/about', component: () => import('./views/AboutView.vue'), meta: { title: '쓰인 자료' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = to.meta?.title
    ? `${to.meta.title} · 우리 산 수익 계산기`
    : '우리 산 수익 계산기'
})

createApp(App).use(router).mount('#app')
