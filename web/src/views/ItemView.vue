<script setup>
import { computed, inject, reactive, ref, watch } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import PageHero from '../components/PageHero.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { areaGrad, axisX, axisY, baseOption, palette, theme, tip, vGrad } from '../lib/charts'

const meta = inject('meta')

const res = ref(null)
const dist = ref(null)
const loading = ref(false)
const error = ref('')
const ready = ref(false)

const form = reactive({
  품목: '밤', 지역별: 37, 경영수준별: 2, 규모별: 1,
  경영비: 5000000, 비료비: null, 농약비: null, 총노동시간: null,
})

const items = computed(() => meta.value?.items || [])
const unit = computed(() => (form.품목.includes('표고') ? '만본' : 'ha'))

const cb = computed(() => meta.value?.cost_codebook || {})
const opts = (key) => {
  const d = cb.value[key]
  return d ? Object.entries(d).map(([code, label]) => ({ code: Number(code), label })) : []
}

/** 선택한 품목의 중앙값을 기본 입력으로 채운다 */
function fillMedians(it) {
  const med = meta.value?.item_medians?.[it]
  if (!med) return
  form.경영비 = Math.round(med['경영비'] ?? 5000000)
  form.비료비 = med['비료비_단위당'] != null ? Math.round(med['비료비_단위당']) : null
  form.농약비 = med['농약비_단위당'] != null ? Math.round(med['농약비_단위당']) : null
  form.총노동시간 = med['총노동시간_합계_단위당'] != null
    ? Math.round(med['총노동시간_합계_단위당']) : null
}
watch(() => form.품목, fillMedians)

// meta는 비동기로 도착한다. 목록이 채워지는 시점에 기본값도 함께 넣어야
// 첫 화면부터 그 품목의 실제 중앙값으로 예측이 돈다.
watch(items, (l) => {
  if (!l.length) return
  if (!l.includes(form.품목)) form.품목 = l[0]
  fillMedians(form.품목)
  ready.value = true
}, { immediate: true })

let timer = null
async function run() {
  if (!ready.value) return
  loading.value = true
  error.value = ''
  try {
    res.value = await api.predictItem({ ...form })
  } catch (e) {
    error.value = e.message
    res.value = null
  } finally {
    loading.value = false
  }
}
function schedule() {
  clearTimeout(timer)
  timer = setTimeout(run, 220)
}
watch(form, schedule, { deep: true })
watch(ready, (v) => { if (v) schedule() }, { immediate: true })

api.itemDistribution().then((d) => { dist.value = d }).catch(() => {})

/* ------------------------------------------------------------------ 차트 */
const structOption = computed(() => {
  const rows = res.value?.structure?.rows?.filter((r) => r.mine != null || r.leader != null)
  if (!rows?.length) return null
  const t = theme()
  return baseOption({
    grid: { left: 8, right: 14, top: 32, bottom: 8, containLabel: true },
    legend: { data: ['귀 임가', '선도임가 중앙값'] },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `<b>${ps[0].axisValue}</b><br/>` +
        ps.map((p) => `${p.marker}${p.seriesName} ${fmt.dec(p.value)}%`).join('<br/>') },
    xAxis: axisX({ data: rows.map((r) => r.item) }),
    yAxis: axisY({ name: '경영비 대비 비중 (%)', axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: '{value}%' } }),
    series: [
      { name: '귀 임가', type: 'bar', barWidth: '34%', data: rows.map((r) => r.mine),
        itemStyle: { color: vGrad(palette.forest), borderRadius: [6, 6, 0, 0] },
        animationDuration: 620 },
      { name: '선도임가 중앙값', type: 'bar', barWidth: '34%', data: rows.map((r) => r.leader),
        itemStyle: { color: vGrad(palette.grey, 0.55, 0.28), borderRadius: [6, 6, 0, 0] },
        animationDuration: 620, animationDelay: 90 },
    ],
  })
})

const overspend = computed(() => {
  const rows = res.value?.structure?.rows || []
  return rows.filter((r) => r.gap != null && r.gap > 2).sort((a, b) => b.gap - a.gap)
})

const curveOption = computed(() => {
  const c = res.value?.curve || []
  if (!c.length) return null
  const t = theme()
  return baseOption({
    grid: { left: 8, right: 8, top: 32, bottom: 8, containLabel: true },
    legend: { data: ['예측 ROI', '예상 소득'] },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `경영비 ${fmt.won(Number(ps[0].axisValue))}<br/>` +
        ps.map((p) => `${p.marker}${p.seriesName} <b>${
          p.seriesName === '예측 ROI' ? fmt.pct(p.value[1]) : fmt.won(p.value[1])}</b>`).join('<br/>') },
    xAxis: axisX({ type: 'value', splitLine: { show: false },
      axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.won(v) } }),
    yAxis: [
      axisY({ name: 'ROI (%)', axisLabel: { color: t.subtle, fontSize: 11.5, formatter: '{value}%' } }),
      axisY({ name: `소득 (원/${unit.value})`, position: 'right', splitLine: { show: false },
        axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.won(v) } }),
    ],
    series: [
      { name: '예측 ROI', type: 'line', smooth: 0.25, symbol: 'none',
        data: c.map((p) => [p.cost, p.roi]),
        lineStyle: { width: 3, color: palette.forest },
        areaStyle: { color: areaGrad(palette.forest, 0.2) },
        markLine: { symbol: 'none', silent: true,
          label: { formatter: '현재', color: t.subtle, fontSize: 11 },
          lineStyle: { color: t.axis, type: 'dashed' }, data: [{ xAxis: form.경영비 }] } },
      { name: '예상 소득', type: 'line', smooth: 0.25, symbol: 'none', yAxisIndex: 1,
        data: c.map((p) => [p.cost, p.income]),
        lineStyle: { width: 2, color: palette.amber, type: 'dotted' } },
    ],
  })
})

const distOption = computed(() => {
  if (!dist.value?.length) return null
  const t = theme()
  const q = (a, p) => {
    const s = [...a].sort((x, y) => x - y)
    const i = (s.length - 1) * p
    const lo = Math.floor(i), hi = Math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)
  }
  const rows = dist.value.map((d) => {
    const v = d.values
    const q1 = q(v, 0.25), q3 = q(v, 0.75), iqr = q3 - q1
    const lo = Math.max(Math.min(...v), q1 - 1.5 * iqr)
    const hi = Math.min(Math.max(...v), q3 + 1.5 * iqr)
    return { item: d.item, box: [lo, q1, q(v, 0.5), q3, hi], n: d.n }
  })
  return baseOption({
    grid: { left: 8, right: 14, top: 20, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'item', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (p) => {
        if (!p.value?.length) return ''
        const [, lo, q1, med, q3, hi] = p.value
        return `<b>${p.name}</b><br/>중앙값 ${fmt.dec(med)}%<br/>` +
          `사분위 ${fmt.dec(q1)} ~ ${fmt.dec(q3)}%<br/>범위 ${fmt.dec(lo)} ~ ${fmt.dec(hi)}%`
      } },
    xAxis: axisX({ data: rows.map((r) => r.item) }),
    yAxis: axisY({ name: '단위면적당 ROI (%)', axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: '{value}%' } }),
    series: [
      { type: 'boxplot', data: rows.map((r) => r.box), boxWidth: [20, 50],
        itemStyle: { color: 'rgba(46,125,79,.2)', borderColor: palette.forest,
          borderWidth: 2, shadowColor: 'rgba(46,125,79,.18)', shadowBlur: 6 },
        emphasis: { itemStyle: { color: 'rgba(46,125,79,.34)', borderWidth: 2.6 } },
        animationDuration: 700 },
      { type: 'line', symbol: 'none', silent: true, tooltip: { show: false },
        data: rows.map(() => res.value?.roi ?? null),
        lineStyle: { color: palette.amber, type: 'dashed', width: 2 } },
    ],
  })
})
</script>

<template>
  <div>
    <PageHero
      src="/img/path.jpg"
      eyebrow="작물별 정밀"
      title="작물마다 자세히 들여다보기"
      lead="임산물생산비조사는 비목별 지출과 작업 공정별 노동시간까지 담고 있어, 임가 단위 모델보다 훨씬 정밀한 진단이 가능합니다."
    />

  <main class="content">
    <div class="container">

      <div v-if="!items.length" class="note note--info">
        Model B가 아직 학습되지 않았습니다.
        <code class="mono">python src/preprocess_cost.py &amp;&amp; python src/train_cost.py</code>
      </div>

      <template v-else>
        <!-- 입력 -->
        <div class="card">
          <div class="card__head"><h3>재배 조건 입력</h3></div>
          <div class="card__body">
            <div class="grid grid--4">
              <div class="field">
                <label class="field__label">품목</label>
                <select class="select" v-model="form.품목">
                  <option v-for="i in items" :key="i">{{ i }}</option>
                </select>
              </div>
              <div class="field">
                <label class="field__label">지역</label>
                <select class="select" v-model.number="form.지역별">
                  <option v-for="o in opts('지역별')" :key="o.code" :value="o.code">{{ o.label }}</option>
                </select>
              </div>
              <div class="field">
                <label class="field__label">경영수준</label>
                <select class="select" v-model.number="form.경영수준별">
                  <option v-for="o in opts('경영수준별')" :key="o.code" :value="o.code">{{ o.label }}</option>
                </select>
              </div>
              <div class="field">
                <label class="field__label">재배규모</label>
                <select class="select" v-model.number="form.규모별">
                  <option v-for="o in opts('규모별')" :key="o.code" :value="o.code">{{ o.label }}</option>
                </select>
              </div>
            </div>
            <div class="grid grid--4">
              <div class="field">
                <label class="field__label">경영비 (원/{{ unit }})</label>
                <div class="input-money">
                  <input class="input" type="number" v-model.number="form.경영비" min="0" step="100000" />
                  <span class="input-money__unit">원</span>
                </div>
              </div>
              <div class="field">
                <label class="field__label">비료비 (원/{{ unit }})</label>
                <div class="input-money">
                  <input class="input" type="number" v-model.number="form.비료비" min="0" step="50000" />
                  <span class="input-money__unit">원</span>
                </div>
              </div>
              <div class="field">
                <label class="field__label">농약비 (원/{{ unit }})</label>
                <div class="input-money">
                  <input class="input" type="number" v-model.number="form.농약비" min="0" step="50000" />
                  <span class="input-money__unit">원</span>
                </div>
              </div>
              <div class="field">
                <label class="field__label">총 노동시간 ({{ unit }}당)</label>
                <input class="input" type="number" v-model.number="form.총노동시간" min="0" step="10" />
              </div>
            </div>
            <p class="field__hint">
              입력하지 않은 항목은 해당 품목의 중앙값으로 채워 예측합니다.
              밤·대추·떫은감은 ha당, 표고는 만본당 기준입니다.
            </p>
          </div>
        </div>

        <DataState :loading="loading && !res" :error="error">
          <template v-if="res">
            <div class="grid grid--4 mt-lg">
              <MetricCard accent :label="`예측 ROI (${unit}당)`" :value="fmt.dec(res.roi)" unit="%" />
              <MetricCard :label="`예상 소득 (원/${unit})`" :value="fmt.won(res.income)" />
              <MetricCard v-if="res.peer_median != null" :label="`${form.품목} 전체 중앙값`"
                :value="fmt.dec(res.peer_median)" unit="%"
                :delta="`${fmt.signed(res.roi - res.peer_median)}%p`"
                :delta-dir="res.roi >= res.peer_median ? 'up' : 'down'" />
              <MetricCard v-if="res.leader_median != null" label="선도임가 중앙값"
                :value="fmt.dec(res.leader_median)" unit="%"
                :delta="`${fmt.signed(res.roi - res.leader_median)}%p`"
                :delta-dir="res.roi >= res.leader_median ? 'up' : 'down'" />
            </div>

            <div class="grid grid--2 mt-lg">
              <div class="card">
                <div class="card__head"><h3>비목 구성 — 선도임가 대비</h3></div>
                <div class="card__body">
                  <EChart v-if="structOption" :option="structOption" height="290px" />
                  <div v-if="overspend.length" class="note note--warn mt-md fs-sm">
                    <strong>비목 과다 투입 신호</strong> —
                    {{ overspend.map(r => `${r.item} +${fmt.dec(r.gap)}%p`).join(', ') }}
                    만큼 선도임가보다 비중이 높습니다. 해당 비목의 절감 여지를 검토하세요.
                  </div>
                  <p v-if="res.structure?.leader_n" class="caveat mt-sm">
                    선도임가 표본 {{ fmt.int(res.structure.leader_n) }}호 기준 중앙값입니다.
                  </p>
                </div>
              </div>

              <div class="card">
                <div class="card__head"><h3>품목별 ROI 분포</h3></div>
                <div class="card__body">
                  <EChart v-if="distOption" :option="distOption" height="290px" />
                  <p class="caveat mt-sm">
                    점선은 현재 입력 조건의 예측값입니다. ROI는 비율 지표이므로 단위 분모가 다른
                    품목 간에도 비교가 가능합니다.
                  </p>
                </div>
              </div>
            </div>

            <div class="card mt-lg">
              <div class="card__head"><h3>경영비 반응곡선</h3></div>
              <div class="card__body">
                <EChart v-if="curveOption" :option="curveOption" height="320px" />
              </div>
            </div>
          </template>
        </DataState>
      </template>
    </div>
  </main>
  </div>
</template>
