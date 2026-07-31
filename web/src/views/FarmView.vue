<script setup>
import { computed, inject, ref, watch } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import PageHero from '../components/PageHero.vue'
import DataState from '../components/DataState.vue'
import FarmSidebar from '../components/FarmSidebar.vue'
import { api, fmt } from '../lib/api'
import { axisX, axisY, baseOption, palette, theme } from '../lib/charts'

const meta = inject('meta')
const farm = inject('farm')

const res = ref(null)
const subsidy = ref(null)
const loading = ref(false)
const error = ref('')
const pickedProgram = ref(null)

let timer = null
async function run() {
  loading.value = true
  error.value = ''
  try {
    res.value = await api.predict({ ...farm })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(farm, () => {
  clearTimeout(timer)
  timer = setTimeout(run, 220)   // 슬라이더를 끌 때 요청이 몰리지 않도록 늦춘다
}, { deep: true, immediate: true })

api.subsidy().then((s) => {
  subsidy.value = s
}).catch(() => { subsidy.value = null })

const sectorLabel = computed(() => meta.value?.codebook?.업종별?.[farm.업종별] ?? '')
const regionLabel = computed(() => meta.value?.codebook?.지역별?.[farm.지역별] ?? '')

/** 같은 업종 임가의 분포 요약 — 내 위치를 숫자로 함께 보여준다 */
const peerStat = computed(() => {
  const v = res.value?.peer?.values
  if (!v?.length) return null
  const s = [...v].sort((a, b) => a - b)
  const q = (p) => {
    const i = (s.length - 1) * p
    const lo = Math.floor(i), hi = Math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)
  }
  return { median: q(0.5), q1: q(0.25), q3: q(0.75) }
})

const rank = computed(() => {
  if (res.value?.percentile == null) return null
  return Math.max(1, Math.round(100 - res.value.percentile))
})

const gapWon = computed(() => {
  if (!res.value?.baseline_income) return null
  return res.value.income - res.value.baseline_income
})

/* ------------------------------------------------------- 보조사업 실효 ROI */
const programs = computed(() => {
  if (!subsidy.value) return []
  const cats = subsidy.value.업종별_관련분류?.[sectorLabel.value] || []
  return subsidy.value.사업목록.filter(
    (p) => cats.includes(p.분류) && p.자부담비율 > 0,
  )
})
watch(programs, (list) => {
  if (list.length && !list.some((p) => p.사업명 === pickedProgram.value?.사업명)) {
    pickedProgram.value = list[0]
  }
})
const effective = computed(() => {
  if (!res.value || !pickedProgram.value) return null
  const sp = pickedProgram.value.자부담비율
  return {
    roi: res.value.roi * (100 / sp),
    own: res.value.cost * sp / 100,
    lever: 100 / sp,
  }
})

/* ------------------------------------------------------------------ 차트 */
const curveOption = computed(() => {
  const c = res.value?.curve || []
  if (!c.length) return null
  const t = theme()
  const best = c.reduce((a, b) => (b.income > a.income ? b : a), c[0])
  return baseOption({
    grid: { left: 8, right: 8, top: 34, bottom: 8, containLabel: true },
    legend: { data: ['예측 ROI', '예상 임업소득'] },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder, borderWidth: 1,
      textStyle: { color: t.text, fontSize: 12.5 },
      extraCssText: 'box-shadow:0 8px 24px rgba(0,0,0,.12);border-radius:9px;',
      formatter: (ps) => {
        const cost = Number(ps[0].axisValue)
        const rows = ps.map((p) => `${p.marker}${p.seriesName} <b>${
          p.seriesName === '예측 ROI' ? fmt.pct(p.value[1]) : fmt.won(p.value[1])
        }</b>`).join('<br/>')
        return `경영비 ${fmt.won(cost)}<br/>${rows}`
      },
    },
    xAxis: axisX({
      type: 'value',
      axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.won(v) },
      splitLine: { show: false },
    }),
    yAxis: [
      axisY({ name: 'ROI (%)', axisLabel: { color: t.subtle, fontSize: 11.5, formatter: '{value}%' } }),
      axisY({ name: '임업소득', position: 'right', splitLine: { show: false },
        axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.won(v) } }),
    ],
    series: [
      {
        name: '예측 ROI', type: 'line', smooth: 0.25, symbol: 'none',
        data: c.map((p) => [p.cost, p.roi]),
        lineStyle: { width: 3, color: palette.forest },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(46,125,79,.18)' },
              { offset: 1, color: 'rgba(46,125,79,0)' },
            ],
          },
        },
        markLine: {
          symbol: 'none', silent: true,
          label: { formatter: '현재 투입', color: t.subtle, fontSize: 11 },
          lineStyle: { color: t.axis, type: 'dashed' },
          data: [{ xAxis: farm.임업경영비 }],
        },
      },
      {
        name: '예상 임업소득', type: 'line', smooth: 0.25, symbol: 'none', yAxisIndex: 1,
        data: c.map((p) => [p.cost, p.income]),
        lineStyle: { width: 2, color: palette.amber, type: 'dotted' },
        markPoint: {
          symbolSize: 46,
          itemStyle: { color: palette.amber },
          label: { fontSize: 10, color: '#fff', formatter: '최대' },
          data: [{ coord: [best.cost, best.income] }],
        },
      },
    ],
  })
})

const bestPoint = computed(() => {
  const c = res.value?.curve || []
  if (!c.length) return null
  return c.reduce((a, b) => (b.income > a.income ? b : a), c[0])
})

const sectorOption = computed(() => {
  const s = res.value?.sectors || []
  if (!s.length) return null
  const t = theme()
  const rows = [...s].reverse()
  return baseOption({
    grid: { left: 8, right: 58, top: 8, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'item', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (p) => `${p.name}<br/><b>${fmt.pct(p.value)}</b>` },
    xAxis: axisY({ axisLabel: { show: false }, splitLine: { show: false } }),
    yAxis: axisX({ data: rows.map((r) => r.sector),
      axisLabel: { color: t.muted, fontSize: 11.5 } }),
    series: [{
      type: 'bar', barWidth: '62%',
      data: rows.map((r) => ({
        value: r.roi,
        itemStyle: {
          color: r.sector === sectorLabel.value ? palette.forest : palette.grey,
          borderRadius: [0, 4, 4, 0],
          opacity: r.sector === sectorLabel.value ? 1 : 0.72,
        },
      })),
      label: { show: true, position: 'right', formatter: (p) => fmt.pct(p.value, 0),
        color: t.muted, fontSize: 11 },
    }],
  })
})

const peerOption = computed(() => {
  const p = res.value?.peer
  if (!p?.bins?.length) return null
  const t = theme()
  return baseOption({
    grid: { left: 8, right: 12, top: 26, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `ROI ${fmt.dec(Number(ps[0].axisValue), 0)}%<br/>임가 <b>${ps[0].value}호</b>` },
    xAxis: axisX({ type: 'category', data: p.bins.map((b) => b.toFixed(0)),
      axisLabel: { color: t.subtle, fontSize: 11, formatter: (v) => `${v}%` } }),
    yAxis: axisY({ name: '임가 수', nameGap: 14, nameTextStyle: { align: 'left' } }),
    series: [{
      type: 'bar', data: p.counts, barCategoryGap: '12%',
      itemStyle: { color: palette.grey, opacity: 0.55, borderRadius: [3, 3, 0, 0] },
      markLine: {
        symbol: 'none', silent: true,
        lineStyle: { color: palette.forest, width: 2.5 },
        label: { formatter: `귀 임가 ${fmt.dec(res.value.roi, 0)}%`, color: palette.forest,
          fontSize: 11, fontWeight: 600, position: 'insideEndTop' },
        data: [{
          xAxis: p.bins.reduce((bi, b, i) =>
            Math.abs(b - res.value.roi) < Math.abs(p.bins[bi] - res.value.roi) ? i : bi, 0),
        }],
      },
    }],
  })
})

const effOption = computed(() => {
  if (!effective.value) return null
  const t = theme()
  return baseOption({
    grid: { left: 8, right: 14, top: 26, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `${ps[0].axisValue}<br/><b>${fmt.pct(ps[0].value)}</b>` },
    xAxis: axisX({ data: ['총 투입액 기준', '자부담 기준'] }),
    yAxis: axisY({ axisLabel: { color: t.subtle, fontSize: 11.5, formatter: '{value}%' } }),
    series: [{
      type: 'bar', barWidth: '46%',
      data: [
        { value: res.value.roi, itemStyle: { color: palette.grey, borderRadius: [5, 5, 0, 0] } },
        { value: effective.value.roi, itemStyle: { color: palette.forest, borderRadius: [5, 5, 0, 0] } },
      ],
      label: { show: true, position: 'top', formatter: (p) => fmt.pct(p.value),
        color: t.muted, fontSize: 11.5, fontWeight: 600 },
    }],
  })
})
</script>

<template>
  <div>
    <PageHero
      src="/img/mountain.jpg"
      eyebrow="자세한 진단"
      title="임가 맞춤형 수익성 진단"
      lead="임가경제조사 마이크로데이터로 학습한 모델의 상세 결과입니다."
    />

  <div class="layout">
    <aside class="sidebar"><FarmSidebar /></aside>

    <main class="content">
      <div class="container">
        <SectionHead
          title="임가 맞춤형 수익성 진단"
          :desc="`${regionLabel} · ${sectorLabel} 조건에서 임가경제조사 마이크로데이터로 학습한 모델이 예측한 결과입니다.`"
          badge="Model A · 임가경제조사"
          badge-kind="green"
        />

        <DataState :loading="loading && !res" :error="error">
          <template v-if="res">
            <div class="grid grid--4">
              <MetricCard
                accent label="예측 임업 ROI" :value="fmt.dec(res.roi)" unit="%"
                :delta="res.baseline_roi != null ? `${fmt.signed(res.roi - res.baseline_roi)}%p vs 지역·업종 평균` : ''"
                :delta-dir="res.baseline_roi != null && res.roi >= res.baseline_roi ? 'up' : 'down'"
                hint="ROI = 임업소득 ÷ 임업경영비 × 100"
              />
              <MetricCard label="예상 임업소득" :value="fmt.won(res.income)"
                :delta="`총수입 ${fmt.won(res.revenue)}`" delta-dir="flat" />
              <MetricCard label="투입 임업경영비" :value="fmt.won(res.cost)"
                :delta="`${fmt.wonFull(res.cost)}`" delta-dir="flat" />
              <MetricCard label="동종 업종 내 위치"
                :value="res.percentile != null ? `상위 ${fmt.dec(100 - res.percentile, 0)}` : '—'" unit="%"
                :delta="res.peer?.n ? `표본 ${fmt.int(res.peer.n)}호` : ''" delta-dir="flat" />
            </div>

            <!-- 예측구간 -->
            <div v-if="res.band" class="note note--warn mt-md">
              <strong>예측구간 (P10~P90)</strong> — ROI
              <b>{{ fmt.dec(res.band[0], 0) }}% ~ {{ fmt.dec(res.band[2], 0) }}%</b>
              (중앙값 {{ fmt.dec(res.band[1], 0) }}%), 임업소득으로는
              <b>{{ fmt.won(res.band[0] / 100 * res.cost) }} ~ {{ fmt.won(res.band[2] / 100 * res.cost) }}</b>.
              <div class="mt-sm fs-sm">
                임가 ROI는 기상·병충해·시장가격 등 조사되지 않는 요인의 영향을 크게 받습니다.
                위 점추정은 확정값이 아니라 분포의 중심이며, 실제 성과는 이 구간 안에서 움직일 가능성이
                <template v-if="res.coverage">약 80%입니다 (검증셋 실측 포함률 {{ fmt.dec(res.coverage * 100, 0) }}%).</template>
                <template v-else>높습니다.</template>
              </div>
            </div>

            <!-- 현행 방식 대비 -->
            <div v-if="gapWon != null && Math.abs(gapWon) > 1000" class="note note--info mt-md">
              현행 산림청 공표 방식은 <b>{{ regionLabel }} · {{ sectorLabel }}</b> 임가를 한 덩어리로 묶어
              ROI <b>{{ fmt.dec(res.baseline_roi) }}%</b>({{ fmt.won(res.baseline_income) }})로 일괄 안내합니다.
              본 모델은 귀 임가 고유 특성을 반영해 <b>{{ fmt.dec(res.roi) }}%</b>({{ fmt.won(res.income) }})로 예측하며,
              차이는 <b>{{ (gapWon >= 0 ? '+' : '−') + fmt.won(Math.abs(gapWon)) }}</b>입니다.
            </div>

            <!-- 경영비 반응곡선 -->
            <div class="grid grid--32 mt-lg">
              <div class="card">
                <div class="card__head">
                  <h3>임업경영비 투입 수준별 반응곡선</h3>
                  <span class="badge badge--grey">what-if</span>
                </div>
                <div class="card__body">
                  <p class="fs-sm muted" style="margin-bottom:10px">
                    다른 조건을 모두 고정하고 경영비만 바꿨을 때 모델이 예측하는 ROI와 임업소득입니다.
                  </p>
                  <EChart v-if="curveOption" :option="curveOption" height="330px" />
                  <div v-if="bestPoint && bestPoint.income - res.income > 100000"
                       class="note note--good mt-md">
                    <strong>경영비 최적화 제안</strong> — 현재 {{ fmt.won(res.cost) }}에서
                    <b>{{ fmt.won(bestPoint.cost) }}</b>로
                    {{ bestPoint.cost > res.cost ? '증액' : '감축' }}하면
                    예상 임업소득이 <b>{{ fmt.won(bestPoint.income - res.income) }}</b> 개선됩니다
                    (ROI {{ fmt.dec(res.roi) }}% → {{ fmt.dec(bestPoint.roi) }}%).
                  </div>
                  <div v-else class="note note--good mt-md">
                    <strong>경영비 최적화 제안</strong> — 현재 투입 수준이 예측 소득 최대 구간에 근접합니다.
                  </div>
                </div>
              </div>

              <div class="card">
                <div class="card__head"><h3>업종 전환 시뮬레이션</h3></div>
                <div class="card__body">
                  <p class="fs-sm muted" style="margin-bottom:10px">
                    지역·규모·자본을 그대로 두고 업종만 바꿨을 때의 반사실적 예측값입니다.
                  </p>
                  <EChart v-if="sectorOption" :option="sectorOption" height="300px" />
                </div>
              </div>
            </div>

            <!-- 분포 내 위치 -->
            <div class="grid grid--2 mt-lg">
              <div class="card">
                <div class="card__head">
                  <h3>{{ sectorLabel }} 임가 분포 내 위치</h3>
                  <span v-if="res.peer?.n" class="badge badge--grey">
                    표본 {{ fmt.int(res.peer.n) }}호
                  </span>
                </div>
                <div class="card__body">
                  <EChart v-if="peerOption" :option="peerOption" height="250px" />

                  <div class="grid grid--3 mt-md" style="gap:10px">
                    <MetricCard label="귀 임가" :value="fmt.dec(res.roi, 0)" unit="%" accent />
                    <MetricCard v-if="peerStat" label="같은 업종 중앙값"
                      :value="fmt.dec(peerStat.median, 0)" unit="%"
                      :delta="`${fmt.signed(res.roi - peerStat.median, 0)}%p`"
                      :delta-dir="res.roi >= peerStat.median ? 'up' : 'down'" />
                    <MetricCard v-if="peerStat" label="상위 25% 기준"
                      :value="fmt.dec(peerStat.q3, 0)" unit="%"
                      :delta="res.roi >= peerStat.q3 ? '이미 상위권입니다' : `${fmt.dec(peerStat.q3 - res.roi, 0)}%p 남았습니다`"
                      delta-dir="flat" />
                  </div>

                  <div v-if="peerStat" class="note note--info mt-md fs-sm">
                    같은 업종 임가 100곳을 잘 버는 순서로 줄 세우면 귀 임가는
                    <b>{{ rank }}번째</b>쯤입니다.
                    상위 25%에 들려면 ROI가 <b>{{ fmt.dec(peerStat.q3, 0) }}%</b> 이상이어야 하고,
                    지금 조건에서 경영비를 조정하면 어디까지 갈 수 있는지는
                    위 반응곡선에서 확인하실 수 있습니다.
                  </div>
                </div>
              </div>

              <!-- 보조사업 실효 ROI -->
              <div class="card">
                <div class="card__head">
                  <h3>보조사업 활용 시 실효 ROI</h3>
                  <span class="badge badge--sky">정책 연계</span>
                </div>
                <div class="card__body">
                  <template v-if="programs.length && effective">
                    <p class="fs-sm muted" style="margin-bottom:10px">
                      예측 ROI는 총 투입액 기준입니다. 보조사업을 쓰면 임가가 실제 부담하는 돈은
                      자부담액뿐이므로 자기 자금 기준 수익률에는 보조율만큼 지렛대가 걸립니다.
                    </p>
                    <div class="field">
                      <label class="field__label">보조사업</label>
                      <select class="select" @change="pickedProgram = programs[$event.target.selectedIndex]">
                        <option v-for="p in programs" :key="p.사업명">
                          {{ p.사업명 }} — 자부담 {{ p.자부담비율 }}%
                        </option>
                      </select>
                    </div>
                    <div class="grid grid--3" style="gap:10px">
                      <MetricCard label="자부담액" :value="fmt.won(effective.own)" />
                      <MetricCard label="실효 ROI" :value="fmt.dec(effective.roi)" unit="%" accent />
                      <MetricCard label="지렛대" :value="fmt.dec(effective.lever)" unit="배" />
                    </div>
                    <EChart v-if="effOption" :option="effOption" height="200px" class="mt-md" />
                    <div class="note note--warn mt-md fs-sm">
                      <strong>{{ pickedProgram.사업명 }}</strong> — 사후관리기간
                      {{ pickedProgram.사후관리기간_년 }}년. {{ subsidy.유의 }}
                    </div>
                    <p class="caveat mt-sm">{{ subsidy.기준시점 }}</p>
                  </template>
                  <p v-else class="muted fs-sm">이 업종에 직접 대응하는 보조사업 정보가 없습니다.</p>
                </div>
              </div>
            </div>
          </template>
        </DataState>
      </div>
    </main>
  </div>
  </div>
</template>
