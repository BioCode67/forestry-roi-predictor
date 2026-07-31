<script setup>
import { computed, inject, ref, watch } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { axisX, axisY, baseOption, palette, theme } from '../lib/charts'

const meta = inject('meta')
const farm = inject('farm')

const mgmt = ref(null)
const ship = ref(null)
const loading = ref(true)
const error = ref('')

const SECTOR_TO_CROP = { 밤재배업: '밤', 떫은감재배업: '떫은감', 버섯재배업: '버섯' }
const sectorLabel = computed(() => meta.value?.codebook?.업종별?.[farm.업종별] ?? '')
const crop = computed(() => SECTOR_TO_CROP[sectorLabel.value])
const m = computed(() => (crop.value ? mgmt.value?.품목별?.[crop.value] : null))

api.management().then((d) => { mgmt.value = d }).catch(() => {})

watch(sectorLabel, async (s) => {
  if (!s) return
  loading.value = true
  error.value = ''
  try {
    ship.value = await api.shipping(s)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}, { immediate: true })

/* 임업통계 기반 출하시기 단가 */
const shipOption = computed(() => {
  const e = m.value?.출하시기별_단가
  if (!e) return null
  const t = theme()
  const unid = new Set(e.식별불가계열 || [])
  const names = Object.keys(e.계열단가).filter((k) => !unid.has(k))
  const vals = names.map((k) => e.계열단가[k])
  const hi = vals.indexOf(Math.max(...vals))
  const ci = e.신뢰구간_90pct || {}
  return baseOption({
    grid: { left: 8, right: 14, top: 30, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: {
      trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => {
        const n = ps[0].axisValue
        const c = ci[n]
        return `<b>${n}</b><br/>추정 단가 <b>${fmt.int(e.계열단가[n])}원/kg</b>` +
          (c ? `<br/>90% 구간 ${fmt.int(c[0])} ~ ${fmt.int(c[1])}원` : '') +
          `<br/>평균 출하비중 ${fmt.dec(e.평균구성비_pct[n], 0)}%`
      },
    },
    xAxis: axisX({ data: names }),
    yAxis: axisY({ name: '원/kg', axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: (v) => fmt.int(v) } }),
    series: [
      {
        type: 'bar', barWidth: '48%',
        data: vals.map((v, i) => ({
          value: v,
          itemStyle: { color: i === hi ? palette.forest : palette.grey,
            borderRadius: [5, 5, 0, 0], opacity: i === hi ? 1 : 0.7 },
        })),
        label: { show: true, position: 'top', formatter: (p) => `${fmt.int(p.value)}원`,
          color: t.muted, fontSize: 11.5, fontWeight: 600 },
      },
      {
        type: 'custom', silent: true,
        renderItem: (params, apiFn) => {
          const n = names[params.dataIndex]
          const c = ci[n]
          if (!c) return null
          const x = apiFn.coord([params.dataIndex, 0])[0]
          const lo = apiFn.coord([params.dataIndex, c[0]])[1]
          const hiY = apiFn.coord([params.dataIndex, c[1]])[1]
          const w = 8
          const style = { stroke: t.muted, lineWidth: 1.4, fill: null }
          return {
            type: 'group',
            children: [
              { type: 'line', shape: { x1: x, y1: lo, x2: x, y2: hiY }, style },
              { type: 'line', shape: { x1: x - w, y1: lo, x2: x + w, y2: lo }, style },
              { type: 'line', shape: { x1: x - w, y1: hiY, x2: x + w, y2: hiY }, style },
            ],
          }
        },
        data: names.map((_, i) => [i, 0]),
      },
    ],
  })
})

const channelOption = computed(() => {
  const e = m.value?.판매처별_단가
  if (!e) return null
  const t = theme()
  const unid = new Set(e.식별불가계열 || [])
  const rows = Object.entries(e.계열단가)
    .filter(([k]) => !unid.has(k))
    .sort((a, b) => a[1] - b[1])
  return baseOption({
    grid: { left: 8, right: 62, top: 8, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'item', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (p) => `${p.name}<br/><b>${fmt.int(p.value)}원/kg</b><br/>평균 비중 ${
        fmt.dec(e.평균구성비_pct[p.name], 0)}%` },
    xAxis: axisY({ axisLabel: { show: false }, splitLine: { show: false } }),
    yAxis: axisX({ data: rows.map((r) => r[0]),
      axisLabel: { color: t.muted, fontSize: 11.5 } }),
    series: [{
      type: 'bar', barWidth: '58%',
      data: rows.map((r, i) => ({
        value: r[1],
        itemStyle: { color: i === rows.length - 1 ? palette.forest : palette.grey,
          borderRadius: [0, 4, 4, 0], opacity: i === rows.length - 1 ? 1 : 0.72 },
      })),
      label: { show: true, position: 'right', formatter: (p) => `${fmt.int(p.value)}원`,
        color: t.muted, fontSize: 11 },
    }],
  })
})

/* KAMIS 월별 가격지수 */
const kamisCharts = computed(() => {
  if (ship.value?.status !== 'ok') return []
  return (ship.value.items || [])
    .filter((it) => it.가격데이터)
    .map((it) => {
      const t = theme()
      const d = it.가격데이터
      return {
        item: it,
        option: baseOption({
          grid: { left: 8, right: 14, top: 26, bottom: 8, containLabel: true },
          legend: { show: false },
          tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
            borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
            formatter: (ps) => `${ps[0].axisValue}월<br/>지수 <b>${fmt.dec(ps[0].value)}</b><br/>${
              fmt.int(d[ps[0].dataIndex].평균도매가격)}원/kg` },
          xAxis: axisX({ data: d.map((r) => r.월) }),
          yAxis: axisY({ name: '가격지수 (전체 월 평균=100)' }),
          series: [{
            type: 'bar', barWidth: '58%',
            data: d.map((r) => ({
              value: r.가격지수,
              itemStyle: { color: r.월 === it.추천월 ? palette.forest : palette.grey,
                borderRadius: [4, 4, 0, 0], opacity: r.월 === it.추천월 ? 1 : 0.62 },
            })),
            markLine: { symbol: 'none', silent: true,
              lineStyle: { color: t.axis, type: 'dashed' },
              label: { formatter: '평균', color: t.subtle, fontSize: 10.5 },
              data: [{ yAxis: 100 }] },
          }],
        }),
      }
    })
})
</script>

<template>
  <main class="content">
    <div class="container">
      <SectionHead
        title="출하 전략"
        :desc="`${sectorLabel} 기준. 임업통계로 시기별 수취 단가를 추정하고, KAMIS 도매가로 월별 계절성을 보완합니다.`"
        badge="임업경영실태조사 × KAMIS" badge-kind="sky"
      />

      <!-- ① 임업통계 기반 -->
      <div v-if="m?.출하시기별_단가" class="section">
        <div class="card">
          <div class="card__head">
            <h3>출하시기별 추정 수취 단가</h3>
            <span class="badge badge--green">임업경영실태조사 {{ m.조사연도 }}</span>
          </div>
          <div class="card__body">
            <p class="fs-sm muted" style="margin-bottom:12px">
              임가별로 관측되는 건 연간 평균 단가 하나뿐입니다. 임가마다 출하시기 구성비가 다르다는 점을
              이용해 <span class="mono">단가 = Σ β·구성비</span> 를 비음수 최소제곱으로 추정했습니다.
              막대의 오차선은 부트스트랩 90% 구간입니다.
            </p>

            <div class="grid grid--32">
              <EChart v-if="shipOption" :option="shipOption" height="320px" />
              <div class="stack stack--md">
                <div class="grid grid--2" style="gap:10px">
                  <MetricCard accent label="최적 출하시기"
                    :value="m.출하시기별_단가.최고시기"
                    :delta="`${fmt.int(m.출하시기별_단가.최고단가)}원/kg`" delta-dir="up" />
                  <MetricCard label="최저 시기 대비"
                    :value="fmt.dec(m.출하시기별_단가.격차_배, 2)" unit="배"
                    :delta="`${m.출하시기별_단가.최저시기} ${fmt.int(m.출하시기별_단가.최저단가)}원`"
                    delta-dir="flat" />
                </div>
                <div class="table-wrap">
                  <table>
                    <thead><tr><th>출하시기</th><th class="num">추정단가</th><th class="num">평균비중</th></tr></thead>
                    <tbody>
                      <tr v-for="(v, k) in m.출하시기별_단가.계열단가" :key="k"
                          :class="{ 'strong-row': k === m.출하시기별_단가.최고시기 }">
                        <td>{{ k }}</td>
                        <td class="num">{{ fmt.int(v) }}원</td>
                        <td class="num">{{ fmt.dec(m.출하시기별_단가.평균구성비_pct[k], 0) }}%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-if="m.출하시기별_단가.제외계열?.length" class="caveat">
                  식별 불안정으로 제외: {{ m.출하시기별_단가.제외계열.join(', ') }}
                </p>
              </div>
            </div>

            <div class="note note--warn mt-md fs-sm">
              <strong>해석 유의</strong> — {{ m.출하시기별_단가.주의 }}
            </div>
          </div>
        </div>
      </div>

      <!-- ② 판매처 · 저장 · 인증 -->
      <div v-if="m" class="grid grid--2 section">
        <div v-if="m.판매처별_단가" class="card">
          <div class="card__head"><h3>판매처별 수취 단가</h3></div>
          <div class="card__body">
            <EChart v-if="channelOption" :option="channelOption" height="270px" />
            <p class="caveat mt-sm">
              판매처 구성비 회귀 추정치입니다. 최고 {{ m.판매처별_단가.최고판매처 }} ·
              최저 {{ m.판매처별_단가.최저판매처 }} ({{ m.판매처별_단가.격차_배 }}배).
            </p>
          </div>
        </div>

        <div class="card">
          <div class="card__head"><h3>저장·인증의 단가 효과</h3></div>
          <div class="card__body">
            <div class="grid grid--2" style="gap:10px">
              <MetricCard v-if="m.저장경험별_단가" label="저장 경험 단가차"
                :value="fmt.signed(m.저장경험별_단가.단가차_pct)" unit="%"
                :delta="`${fmt.int(m.저장경험별_단가['저장경험 있음'].단가중앙값)}원 vs ${fmt.int(m.저장경험별_단가['저장경험 없음'].단가중앙값)}원`"
                :delta-dir="m.저장경험별_단가.단가차_pct >= 0 ? 'up' : 'down'" />
              <MetricCard v-if="m.공식인증_프리미엄" label="공식인증 프리미엄"
                :value="fmt.signed(m.공식인증_프리미엄.프리미엄_pct)" unit="%"
                :delta="`${fmt.int(m.공식인증_프리미엄['인증 보유'].단가중앙값)}원 vs ${fmt.int(m.공식인증_프리미엄['인증 없음'].단가중앙값)}원`"
                :delta-dir="m.공식인증_프리미엄.프리미엄_pct >= 0 ? 'up' : 'down'" />
            </div>
            <p class="caveat mt-md">
              저장 설비·자금 여력이나 인증 취득이 가능한 임가는 애초에 규모·품질이 다를 수 있습니다.
              위 차이는 상관관계이며 순효과가 아닙니다.
            </p>
          </div>
        </div>
      </div>

      <!-- ③ KAMIS -->
      <SectionHead title="KAMIS 월별 도매가 기반 계절성" badge="공공데이터 융복합" badge-kind="amber"
        desc="KAMIS 일일 가격조사 대상 63개 품목 중 임산물은 단감·느타리·새송이·팽이버섯뿐입니다." />

      <DataState :loading="loading" :error="error">
        <div v-if="ship?.status === 'not_applicable'" class="note note--info">
          {{ ship.message }}
        </div>
        <template v-else-if="ship">
          <div v-if="ship.message" class="note note--warn" style="margin-bottom:14px">{{ ship.message }}</div>
          <div class="grid grid--2">
            <div v-for="c in kamisCharts" :key="c.item.품목" class="card">
              <div class="card__head">
                <h3>{{ c.item.품목 }}</h3>
                <span class="badge" :class="c.item.전략유형 === '생산시기 조절' ? 'badge--amber' : 'badge--green'">
                  {{ c.item.전략유형 }}
                </span>
              </div>
              <div class="card__body">
                <div class="grid grid--3" style="gap:10px;margin-bottom:12px">
                  <MetricCard accent label="최고 가격월" :value="`${c.item.추천월}월`"
                    :delta="`지수 ${fmt.dec(c.item.추천월_가격지수, 0)}`" delta-dir="up" />
                  <MetricCard label="최저 가격월" :value="`${c.item.최저월}월`"
                    :delta="`지수 ${fmt.dec(c.item.최저월_가격지수, 0)}`" delta-dir="down" />
                  <MetricCard label="월간 최대 격차"
                    :value="fmt.dec(c.item['최고최저_격차_pct'], 1)" unit="%p" />
                </div>
                <EChart :option="c.option" height="230px" />
                <p class="fs-sm muted mt-sm">{{ c.item.추천근거 }}</p>
                <p v-if="c.item.주의" class="caveat mt-sm">{{ c.item.주의 }}</p>
              </div>
            </div>
          </div>
          <div v-if="!kamisCharts.length && ship.items?.length" class="grid grid--2">
            <div v-for="it in ship.items" :key="it.품목" class="card">
              <div class="card__head"><h3>{{ it.품목 }}</h3></div>
              <div class="card__body">
                <p class="fs-sm muted">{{ it.추천근거 }}</p>
                <p class="fs-sm mt-sm">
                  수확기 {{ it.수확기.join('·') }}월 · 저장성 {{ it.저장성 }}
                </p>
                <p v-if="it.주의" class="caveat mt-sm">{{ it.주의 }}</p>
              </div>
            </div>
          </div>
        </template>
      </DataState>
    </div>
  </main>
</template>
