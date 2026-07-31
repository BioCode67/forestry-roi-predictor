<script setup>
import { computed, inject, ref } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import PageHero from '../components/PageHero.vue'
import { fmt } from '../lib/api'
import { axisX, axisY, baseOption, palette, theme } from '../lib/charts'

const meta = inject('meta')
const tab = ref('a')

const bench = computed(() =>
  tab.value === 'a' ? meta.value?.benchmark_a : meta.value?.benchmark_b)
const q = computed(() => meta.value?.quantile?.[tab.value === 'a' ? 'roi' : 'cost'])

const METRICS = [
  { key: 'R2', label: 'R²', hint: '↑ 높을수록 우수', dec: 4 },
  { key: 'RMSE', label: 'RMSE', hint: '↓ 낮을수록 우수', dec: 2 },
  { key: 'MAE', label: 'MAE', hint: '↓ 낮을수록 우수', dec: 2 },
]

function benchOption(metricKey, dec) {
  const b = bench.value
  if (!b?.rows?.length) return null
  const t = theme()
  return baseOption({
    grid: { left: 8, right: 14, top: 26, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `${ps[0].axisValue}<br/><b>${fmt.dec(ps[0].value, dec)}</b>` },
    xAxis: axisX({ data: b.rows.map((r) => r.label),
      axisLabel: { color: t.subtle, fontSize: 10.5, interval: 0, width: 90, overflow: 'break' } }),
    yAxis: axisY(),
    series: [{
      type: 'bar', barWidth: '46%',
      data: b.rows.map((r, i) => ({
        value: r[metricKey],
        itemStyle: { color: i === b.rows.length - 1 ? palette.forest : palette.grey,
          opacity: i === b.rows.length - 1 ? 1 : 0.62, borderRadius: [5, 5, 0, 0] },
      })),
      label: { show: true, position: 'top', color: t.muted, fontSize: 11, fontWeight: 600,
        formatter: (p) => fmt.dec(p.value, dec) },
    }],
  })
}

const importanceOption = computed(() => {
  const imp = bench.value?.importance
  if (!imp?.length) return null
  const t = theme()
  const rows = [...imp].reverse()
  return baseOption({
    grid: { left: 8, right: 20, top: 8, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'item', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (p) => `${p.name}<br/>Gain <b>${fmt.int(p.value)}</b>` },
    xAxis: axisY({ axisLabel: { show: false }, splitLine: { show: false } }),
    yAxis: axisX({ data: rows.map((r) => r[0]), axisLabel: { color: t.muted, fontSize: 11 } }),
    series: [{
      type: 'bar', barWidth: '66%',
      data: rows.map((r) => r[1]),
      itemStyle: { color: palette.forest, opacity: 0.85, borderRadius: [0, 4, 4, 0] },
    }],
  })
})
</script>

<template>
  <div>
    <PageHero
      src="/img/ridge.jpg"
      eyebrow="모델 성능"
      title="이 계산이 얼마나 맞나요"
      lead="현행 산림청 공표 방식(단순 그룹 평균)을 같은 평가셋에서 예측기로 세워 비교했습니다. 학습에 한 번도 쓰이지 않은 자료로 산출한 값입니다."
    />

  <main class="content">
    <div class="container">

      <div class="tabs">
        <button class="tab" :class="{ 'tab--active': tab === 'a' }" @click="tab = 'a'">
          Model A · 임가경제조사
        </button>
        <button class="tab" :class="{ 'tab--active': tab === 'b' }" @click="tab = 'b'">
          Model B · 임산물생산비조사
        </button>
      </div>

      <div v-if="!bench" class="note note--info">
        해당 모델이 아직 학습되지 않았습니다.
      </div>

      <template v-else>
        <div class="grid grid--4">
          <MetricCard accent label="제안 모델 R²"
            :value="fmt.dec(bench.rows.at(-1).R2, 4)"
            :delta="bench.improvement ? `${fmt.signed(bench.improvement.R2_delta, 4)} vs 베이스라인` : ''"
            delta-dir="up" />
          <MetricCard label="RMSE 감소"
            :value="fmt.dec(bench.improvement?.RMSE_reduction_pct)" unit="%" delta-dir="up" />
          <MetricCard label="MAE 감소"
            :value="fmt.dec(bench.improvement?.MAE_reduction_pct)" unit="%" delta-dir="up" />
          <MetricCard v-if="bench.cv_oof" label="교차검증 OOF R²"
            :value="fmt.dec(bench.cv_oof.R2, 4)"
            :delta="`RMSE ${fmt.dec(bench.cv_oof.RMSE, 2)}`" delta-dir="flat"
            hint="Test 성능과 유사하면 과적합이 없다는 뜻입니다." />
        </div>

        <div class="grid grid--3 mt-lg">
          <div v-for="m in METRICS" :key="m.key" class="card">
            <div class="card__head">
              <h3>{{ m.label }}</h3>
              <span class="badge badge--grey">{{ m.hint }}</span>
            </div>
            <div class="card__body">
              <EChart :option="benchOption(m.key, m.dec)" height="250px" />
            </div>
          </div>
        </div>

        <div class="card mt-lg">
          <div class="card__head"><h3>벤치마크 상세</h3></div>
          <div class="card__body">
            <div class="table-wrap">
              <table>
                <thead>
                  <tr><th>모델</th><th class="num">R²</th><th class="num">RMSE (%p)</th><th class="num">MAE (%p)</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(r, i) in bench.rows" :key="r.key" :class="{ 'strong-row': i === bench.rows.length - 1 }">
                    <td>{{ r.label }}</td>
                    <td class="num">{{ fmt.dec(r.R2, 4) }}</td>
                    <td class="num">{{ fmt.dec(r.RMSE, 2) }}</td>
                    <td class="num">{{ fmt.dec(r.MAE, 2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="note note--info mt-md fs-sm">
              임가 ROI는 기상·병충해·시장가격 등 관측되지 않은 요인의 영향을 크게 받는, 본질적으로
              잡음이 큰 변수입니다. R²의 절대 수준보다 <b>동일 데이터·동일 평가셋에서 현행 방식 대비
              얼마나 개선되는가</b>가 정책적으로 의미 있는 비교입니다.
            </div>
          </div>
        </div>

        <div v-if="q" class="card mt-lg">
          <div class="card__head">
            <h3>예측구간 신뢰도</h3>
            <span class="badge badge--sky">분위수 회귀</span>
          </div>
          <div class="card__body">
            <div class="grid grid--3" style="gap:10px">
              <MetricCard accent label="구간 포함률"
                :value="fmt.dec(q.coverage_80pct * 100)" unit="%"
                delta="명목 80%" delta-dir="flat" />
              <MetricCard label="구간폭 중앙값"
                :value="fmt.dec(q.median_interval_width, 0)" unit="%p" />
              <MetricCard label="P50 MAE" :value="fmt.dec(q.p50_mae, 2)" unit="%p" />
            </div>
            <p class="caveat mt-md">
              구간 포함률이 명목 80%에 가까우면 예측구간이 신뢰할 만하다는 뜻입니다.
              구간폭이 넓은 것은 모델 결함이 아니라 임가 ROI의 실제 산포를 반영한 결과입니다.
            </p>
          </div>
        </div>

        <div v-if="bench.per_item" class="card mt-lg">
          <div class="card__head"><h3>품목별 예측 정확도</h3></div>
          <div class="card__body">
            <div class="table-wrap">
              <table>
                <thead><tr><th>품목</th><th class="num">Test 표본</th><th class="num">R²</th><th class="num">RMSE</th><th class="num">MAE</th></tr></thead>
                <tbody>
                  <tr v-for="(v, k) in bench.per_item" :key="k">
                    <td>{{ k }}</td><td class="num">{{ fmt.int(v.n) }}</td>
                    <td class="num">{{ fmt.dec(v.R2, 3) }}</td>
                    <td class="num">{{ fmt.dec(v.RMSE, 1) }}</td>
                    <td class="num">{{ fmt.dec(v.MAE, 1) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="card mt-lg">
          <div class="card__head"><h3>변수 중요도 (XGBoost Gain 상위 15)</h3></div>
          <div class="card__body">
            <EChart v-if="importanceOption" :option="importanceOption" height="440px" />
          </div>
        </div>
      </template>
    </div>
  </main>
  </div>
</template>
