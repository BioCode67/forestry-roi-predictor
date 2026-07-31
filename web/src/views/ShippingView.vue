<script setup>
import { computed, inject, ref, watch } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import PageHead from '../components/PageHead.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { axisX, axisY, barH, barV, baseOption, palette, refLine, theme, tip, vGrad } from '../lib/charts'

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

const strip = computed(() => {
  const e = m.value?.출하시기별_단가
  const ch = m.value?.판매처별_단가
  const st = m.value?.저장경험별_단가
  if (!e && !ch) return []
  return [
    e && { label: '값 가장 잘 받는 시기', value: e.최고시기,
      note: `kg당 ${fmt.int(e.최고단가)}원` },
    e && { label: '가장 쌀 때와 차이', value: fmt.dec(e.격차_배, 2), unit: '배',
      note: `${e.최저시기} ${fmt.int(e.최저단가)}원` },
    ch && { label: '값 더 주는 판매처', value: ch.최고판매처,
      note: `kg당 ${fmt.int(ch.계열단가[ch.최고판매처])}원` },
    st && { label: '저장고 쓰는 농가', value: fmt.signed(st.단가차_pct, 0), unit: '%',
      note: '단가 차이' },
  ].filter(Boolean)
})

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
  // 오차막대는 custom 시리즈라 축 범위 계산에 안 들어간다. 구간 상한을 직접
  // 축 최댓값에 반영하지 않으면 막대 위 라벨과 오차막대 윗머리가 잘린다.
  const top = Math.max(...vals, ...names.map((n) => (ci[n] ? ci[n][1] : 0)))
  const yMax = Math.ceil(top * 1.14 / 500) * 500
  return baseOption({
    grid: { left: 8, right: 14, top: 40, bottom: 8, containLabel: true },
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
    yAxis: axisY({ name: 'kg당 원', max: yMax, axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: (v) => fmt.int(v) } }),
    series: [
      barV(vals, { highlight: hi, label: (p) => `${fmt.int(p.value)}원`, width: '46%' }),
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
    series: [barH(rows.map((r) => r[1]),
      { highlight: rows.length - 1, label: (p) => `${fmt.int(p.value)}원` })],
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
          yAxis: axisY({ name: '시세 수준 (1년 평균=100)' }),
          series: [{
            ...barV(d.map((r) => r.가격지수), {
              highlight: d.findIndex((r) => r.월 === it.추천월), width: '56%' }),
            markLine: refLine(100, '1년 평균'),
          }],
        }),
      }
    })
})
</script>

<template>
  <div>
    <PageHero
      src="/img/harvest.jpg"
      eyebrow="출하 전략"
      title="언제, 어디에 팔면 좋을까요"
      lead="같은 물건이라도 파는 시기와 파는 곳에 따라 받는 값이 달라집니다. 전국 농가가 실제로 언제·어디에 팔았고 얼마를 받았는지 조사한 자료로 계산했습니다."
    />

    <StatStrip :items="strip" />

  <main class="content" style="padding-top:6px">
    <div class="container">

      <!-- ① 임업통계 기반 -->
      <div v-if="m?.출하시기별_단가" class="section">
        <div class="card">
          <div class="card__head">
            <h3>언제 팔 때 값을 가장 잘 받나요</h3>
            <span class="badge badge--green">임업경영실태조사 {{ m.조사연도 }}</span>
          </div>
          <div class="card__body">
            <p class="fs-sm muted" style="margin-bottom:12px">
              농가마다 파는 시기 비중이 다릅니다. 그 차이를 이용해 시기별로 kg당 얼마를 받는지 되짚어
              계산했습니다. 막대 위아래 선은 <b>계산의 여유 폭</b>으로, 짧을수록 확실한 숫자입니다.
            </p>

            <div class="grid grid--32">
              <EChart v-if="shipOption" :option="shipOption" height="320px" />
              <div class="stack stack--md">
                <div class="grid grid--2" style="gap:10px">
                  <MetricCard accent label="값 가장 잘 받는 시기"
                    :value="m.출하시기별_단가.최고시기"
                    :delta="`${fmt.int(m.출하시기별_단가.최고단가)}원/kg`" delta-dir="up" />
                  <MetricCard label="가장 쌀 때와 비교하면"
                    :value="fmt.dec(m.출하시기별_단가.격차_배, 2)" unit="배"
                    :delta="`${m.출하시기별_단가.최저시기} ${fmt.int(m.출하시기별_단가.최저단가)}원`"
                    delta-dir="flat" />
                </div>
                <div class="table-wrap">
                  <table>
                    <thead><tr><th>파는 시기</th><th class="num">kg당 받는 값</th><th class="num">이때 파는 비중</th></tr></thead>
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
                  자료가 적어 계산에서 뺀 시기: {{ m.출하시기별_단가.제외계열.join(', ') }}
                </p>
              </div>
            </div>

            <div class="note note--warn mt-md fs-sm">
              <strong>참고하실 점</strong> — 이 숫자는 저장 경험이 있는 농가가 답한 자료를 바탕으로 합니다.
              저장고를 갖춘 농가는 규모나 품질도 다를 수 있어서, "이 시기에 팔면 무조건 이만큼 받는다"는
              뜻이 아니라 "이런 경향이 있다"로 봐 주세요.
            </div>
          </div>
        </div>
      </div>

      <!-- ② 판매처 · 저장 · 인증 -->
      <div v-if="m" class="grid grid--2 section">
        <div v-if="m.판매처별_단가" class="card">
          <div class="card__head"><h3>어디에 팔 때 값을 더 받나요</h3></div>
          <div class="card__body">
            <EChart v-if="channelOption" :option="channelOption" height="270px" />
            <p class="caveat mt-sm">
              {{ m.판매처별_단가.최고판매처 }}가 가장 높고 {{ m.판매처별_단가.최저판매처 }}가 가장 낮아
              {{ m.판매처별_단가.격차_배 }}배 차이납니다. 농가마다 파는 곳 비중이 다른 점을 이용해 계산했습니다.
            </p>
          </div>
        </div>

        <div class="card">
          <div class="card__head"><h3>저장고와 인증이 값에 미치는 영향</h3></div>
          <div class="card__body">
            <div class="grid grid--2" style="gap:10px">
              <MetricCard v-if="m.저장경험별_단가" label="저장고 쓰는 농가는"
                :value="fmt.signed(m.저장경험별_단가.단가차_pct)" unit="%"
                :delta="`${fmt.int(m.저장경험별_단가['저장경험 있음'].단가중앙값)}원 vs ${fmt.int(m.저장경험별_단가['저장경험 없음'].단가중앙값)}원`"
                :delta-dir="m.저장경험별_단가.단가차_pct >= 0 ? 'up' : 'down'" />
              <MetricCard v-if="m.공식인증_프리미엄" label="인증 받은 농가는"
                :value="fmt.signed(m.공식인증_프리미엄.프리미엄_pct)" unit="%"
                :delta="`${fmt.int(m.공식인증_프리미엄['인증 보유'].단가중앙값)}원 vs ${fmt.int(m.공식인증_프리미엄['인증 없음'].단가중앙값)}원`"
                :delta-dir="m.공식인증_프리미엄.프리미엄_pct >= 0 ? 'up' : 'down'" />
            </div>
            <p class="caveat mt-md">
              저장고를 지을 여력이 있거나 인증을 받은 농가는 원래 규모와 품질이 다를 수 있습니다.
              그러니 "저장고만 지으면 이만큼 오른다"기보다 "그런 농가들이 실제로 더 받고 있다"로 읽어 주세요.
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
                  <MetricCard accent label="가장 비싼 달" :value="`${c.item.추천월}월`"
                    :delta="`지수 ${fmt.dec(c.item.추천월_가격지수, 0)}`" delta-dir="up" />
                  <MetricCard label="가장 싼 달" :value="`${c.item.최저월}월`"
                    :delta="`지수 ${fmt.dec(c.item.최저월_가격지수, 0)}`" delta-dir="down" />
                  <MetricCard label="비쌀 때와 쌀 때 차이"
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
  </div>
</template>
