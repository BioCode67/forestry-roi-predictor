<script setup>
/**
 * 한 작목에 몰아도 될까요 — 작목 조합의 위험 분산.
 *
 * 화면의 순서는 임가가 떠올릴 법한 질문을 따라갑니다.
 *   1) 내 작목은 해마다 얼마나 흔들리나
 *   2) 섞으면 정말 줄어드나
 *   3) 그런데 그보다 훨씬 큰 게 따로 있지 않나  ← 여기가 결론
 */
import { computed, ref } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { axisX, axisY, baseOption, mix, palette, theme, vGrad } from '../lib/charts'

const pf = ref(null)
const loading = ref(true)
const error = ref('')

api.portfolio()
  .then((d) => { pf.value = d })
  .catch((e) => { error.value = e.message })
  .finally(() => { loading.value = false })

const best = computed(() => pf.value?.최고효율)
const single = computed(() => pf.value?.단일_최고효율)

/** 결론이 되는 대비: 작목을 바꿔 줄일 수 있는 몫 vs 그러지 못하는 몫 */
const ratio = computed(() => {
  const b = best.value
  return b && b.연도변동_pct > 0 ? b.임가격차_pct / b.연도변동_pct : null
})

const strip = computed(() => {
  if (!pf.value) return []
  const b = best.value, s = single.value
  return [
    s && { label: '한 작목만 할 때 가장 나은 선택', value: s.품목,
      note: `수익 ${fmt.dec(s.기대수익_pct, 0)}% · 해마다 ±${fmt.dec(s.연도변동_pct, 0)}%` },
    b && { label: '섞었을 때 흔들리는 폭', value: fmt.dec(b.연도변동_pct, 1), unit: '%',
      note: `한 작목만 할 때 ±${fmt.dec(s?.연도변동_pct, 0)}%` },
    pf.value.분산효과_pct != null && { label: '섞어서 나아지는 정도',
      value: fmt.signed(pf.value.분산효과_pct, 0), unit: '%', note: '위험 대비 수익 기준' },
    ratio.value && { label: '작목보다 큰 변수', value: `${fmt.dec(ratio.value, 0)}배`,
      note: '같은 작목 안 임가 간 격차' },
  ].filter(Boolean)
})

/* ── ① 위험-수익 지도 ────────────────────────────────────────────────── */
const mapOption = computed(() => {
  if (!pf.value) return null
  const t = theme()
  const cloud = pf.value.표본.map((p) => [p.vol, p.ret])
  // 효율선은 수익 순으로 담겨 있어 아래쪽 절반은 '같은 위험에 덜 버는' 구간이다.
  // 흔들림이 가장 작은 지점부터 위쪽만 남겨야 '알뜰한 조합'이라는 이름과 맞는다.
  const fr = pf.value.효율선
  const knee = fr.reduce((m, p, i) => (p.vol < fr[m].vol ? i : m), 0)
  const line = fr.slice(knee).map((p) => [p.vol, p.ret])
  const below = fr.slice(0, knee + 1).map((p) => [p.vol, p.ret])
  const items = pf.value.품목.map((r) => ({
    value: [r.연도변동_pct, r.기대수익_pct], name: r.품목,
  }))
  const b = best.value
  return baseOption({
    grid: { left: 8, right: 26, top: 34, bottom: 8, containLabel: true },
    legend: { data: ['가능한 조합', '가장 알뜰한 조합들', '한 작목만 할 때'], top: 0, right: 0 },
    tooltip: {
      trigger: 'item',
      backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder, borderWidth: 1,
      textStyle: { color: t.text, fontSize: 12.5 },
      extraCssText: 'box-shadow:0 10px 30px rgba(0,0,0,.14);border-radius:10px;',
      formatter: (p) => {
        const [vol, ret] = p.value
        const head = p.name ? `<b>${p.name}</b><br/>` : ''
        return `${head}해마다 흔들리는 폭 <b>±${fmt.dec(vol)}%</b>`
          + `<br/>기대 수익률 <b>${fmt.dec(ret)}%</b>`
      },
    },
    xAxis: axisY({
      name: '해마다 흔들리는 폭 (작을수록 안정)', nameLocation: 'middle', nameGap: 34,
      axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => `±${v}%` },
    }),
    yAxis: axisY({ name: '기대 수익률', axisLabel: { color: t.subtle, fontSize: 11.5, formatter: '{value}%' } }),
    series: [
      {
        name: '가능한 조합', type: 'scatter', data: cloud, symbolSize: 6,
        itemStyle: { color: mix(palette.grey, 0.32) }, silent: true, animationDuration: 700,
      },
      {
        name: '가장 알뜰한 조합들', type: 'line', data: line, smooth: 0.2,
        symbol: 'circle', symbolSize: 7,
        lineStyle: { width: 3, color: palette.forest },
        itemStyle: { color: '#fff', borderColor: palette.forest, borderWidth: 2.4 },
        animationDuration: 900,
        markPoint: b ? {
          symbol: 'pin', symbolSize: 52,
          itemStyle: { color: palette.forest },
          label: { color: '#fff', fontSize: 10.5, fontWeight: 700, formatter: '알뜰' },
          data: [{ coord: [b.연도변동_pct, b.기대수익_pct] }],
        } : undefined,
      },
      {
        // 굳이 그리는 이유: 이 아래로는 같은 위험을 지고도 덜 번다는 걸 보여 준다
        name: '', type: 'line', data: below, smooth: 0.2, symbol: 'none', silent: true,
        lineStyle: { width: 1.6, color: mix(palette.grey, 0.55), type: 'dashed' },
        tooltip: { show: false }, animationDuration: 700,
      },
      {
        name: '한 작목만 할 때', type: 'scatter', data: items, symbolSize: 15,
        itemStyle: { color: palette.amber, borderColor: '#fff', borderWidth: 2 },
        label: {
          show: true, position: 'right', distance: 9, color: t.muted,
          fontSize: 11.5, fontWeight: 650, formatter: (p) => p.name,
        },
        animationDuration: 900, animationDelay: 300,
      },
    ],
  })
})

/* ── ② 두 종류의 위험 ────────────────────────────────────────────────── */
const riskOption = computed(() => {
  if (!pf.value) return null
  const t = theme()
  const rows = [...pf.value.품목].sort((a, b) => b.임가격차_pct - a.임가격차_pct)
  return baseOption({
    grid: { left: 8, right: 18, top: 34, bottom: 8, containLabel: true },
    legend: { data: ['해마다 달라지는 폭', '같은 해 임가끼리 벌어지는 폭'], top: 0, right: 0 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder, borderWidth: 1,
      textStyle: { color: t.text, fontSize: 12.5 },
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(46,125,79,.07)' } },
      formatter: (ps) => `<b>${ps[0].axisValue}</b><br/>`
        + ps.map((p) => `${p.marker}${p.seriesName} ±${fmt.dec(p.value)}%`).join('<br/>')
        + '<br/><span style="opacity:.7;font-size:11px">아래쪽은 작목을 섞어도 줄지 않습니다</span>',
    },
    xAxis: axisX({ data: rows.map((r) => r.품목) }),
    yAxis: axisY({ name: '흔들리는 폭 (%)', axisLabel: { color: t.subtle, fontSize: 11.5, formatter: '±{value}%' } }),
    series: [
      {
        name: '해마다 달라지는 폭', type: 'bar', barWidth: '30%',
        data: rows.map((r) => r.연도변동_pct),
        itemStyle: { color: vGrad(palette.forest), borderRadius: [6, 6, 0, 0] },
        animationDuration: 620,
      },
      {
        name: '같은 해 임가끼리 벌어지는 폭', type: 'bar', barWidth: '30%',
        data: rows.map((r) => r.임가격차_pct),
        itemStyle: { color: vGrad(palette.amber, 0.9, 0.42), borderRadius: [6, 6, 0, 0] },
        animationDuration: 620, animationDelay: 100,
      },
    ],
  })
})

/* ── ③ 조합 구성 ────────────────────────────────────────────────────── */
const mixOption = computed(() => {
  if (!best.value) return null
  const t = theme()
  const rows = [...best.value.구성].reverse()
  return baseOption({
    grid: { left: 8, right: 46, top: 12, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { show: false },
    xAxis: axisY({ show: false, max: Math.max(...rows.map((r) => r.비중_pct)) * 1.25 }),
    yAxis: axisX({ type: 'category', data: rows.map((r) => r.품목) }),
    series: [{
      type: 'bar', barWidth: '54%',
      data: rows.map((r, i) => ({
        value: r.비중_pct,
        itemStyle: {
          // 비중이 큰 작목일수록 진하게 — 하나를 나눈 것이지 서로 다른 범주가 아니다
          color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: mix(palette.forest, 0.34 + 0.34 * (i / Math.max(rows.length - 1, 1))) },
              { offset: 1, color: mix(palette.forest, 0.5 + 0.5 * (i / Math.max(rows.length - 1, 1))) }] },
          borderRadius: [0, 6, 6, 0],
        },
      })),
      label: { show: true, position: 'right', distance: 8, color: t.muted,
        fontSize: 11.5, fontWeight: 650, formatter: (p) => `${fmt.dec(p.value, 0)}%` },
      animationDuration: 620, animationDelay: (i) => i * 60,
    }],
  })
})

const showMethod = ref(false)
</script>

<template>
  <div>
    <PageHero
      src="/img/ridge.jpg"
      eyebrow="위험 관리"
      title="한 가지 작목에만 몰아도 괜찮을까요"
      lead="수익이 가장 높은 작목이 늘 가장 좋은 선택은 아닙니다. 그해 시세와 작황에 따라 크게 흔들린다면, 좋은 해와 나쁜 해의 차이가 그대로 살림의 차이가 되기 때문입니다. 여러 작목을 섞으면 그 폭이 얼마나 줄어드는지 실제 조사 자료로 계산했습니다."
    />

    <StatStrip :items="strip" />

    <main class="content" style="padding-top:6px">
      <div class="container">
        <DataState :loading="loading" :error="error">
          <template v-if="pf">

            <!-- ① 위험-수익 지도 -->
            <div class="card">
              <div class="card__head">
                <h3>수익과 흔들림을 함께 놓고 보기</h3>
                <span class="badge badge--grey">작목 조합 6,000가지</span>
              </div>
              <div class="card__body">
                <p class="lede">
                  오른쪽으로 갈수록 해마다 크게 흔들리고, 위로 갈수록 많이 법니다.
                  <b>주황 점</b>은 한 작목만 했을 때, <b>회색 점</b>은 여러 작목을 이런저런 비율로
                  섞어 봤을 때입니다. <b>초록 선</b>은 같은 수익이라면 가장 덜 흔들리는 조합들을
                  이은 것으로, 이 선의 왼쪽 위로는 갈 수 없습니다.
                </p>
                <EChart v-if="mapOption" :option="mapOption" height="400px" />
                <p class="caveat mt-sm">
                  회색 점 하나하나가 작목 비율 조합 하나입니다. 주황 점이 초록 선보다 오른쪽에 있다면,
                  같은 수익을 더 안정적으로 낼 방법이 있다는 뜻입니다.
                </p>
              </div>
            </div>

            <!-- ② 조합 -->
            <div class="card mt-lg">
              <div class="card__head"><h3>가장 알뜰한 조합은 이렇습니다</h3></div>
              <div class="card__body">
                <div class="grid grid--32">
                  <EChart v-if="mixOption" :option="mixOption" height="240px" />
                  <div class="stack stack--md">
                    <div class="grid grid--2" style="gap:10px">
                      <MetricCard accent label="섞었을 때 흔들리는 폭"
                        :value="fmt.dec(best.연도변동_pct, 1)" unit="%"
                        :delta="`한 작목만 할 때는 ±${fmt.dec(single?.연도변동_pct, 0)}%`" delta-dir="up" />
                      <MetricCard label="그때 기대 수익률"
                        :value="fmt.dec(best.기대수익_pct, 0)" unit="%"
                        :delta="`${single?.품목} 혼자면 ${fmt.dec(single?.기대수익_pct, 0)}%`" delta-dir="flat" />
                    </div>
                    <div class="note note--good fs-sm">
                      수익은 조금 낮아지지만 흔들림이 더 크게 줄어, 위험 대비 수익이
                      <b>{{ fmt.signed(pf.분산효과_pct, 0) }}%</b> 나아집니다.
                      한 해 농사를 망쳐도 살림이 통째로 흔들리지는 않는다는 뜻입니다.
                    </div>
                    <div v-if="pf.보수가정" class="note note--info fs-sm">
                      <strong>뒤집히지 않는지 확인했습니다</strong> — 작목들이 실은 서로 비슷하게
                      움직인다고 보수적으로 잡아도({{ pf.보수가정.가정 }})
                      가장 알뜰한 조합은
                      {{ pf.보수가정.구성.map((c) => `${c.품목} ${Math.round(c.비중_pct)}%`).join(' · ') }}로,
                      역시 한 작목에 몰지 않는 쪽입니다.
                    </div>
                  </div>
                </div>
                <p class="caveat mt-md">
                  당장 이 비율로 나누시라는 뜻이 아닙니다. 작목을 바꾸려면 나무를 새로 심어 수확까지
                  여러 해가 걸리고, 표고는 만본당·나머지는 ha당 기준이라 면적을 그대로 쪼갠다는
                  얘기도 아닙니다. "한 작목에 몰면 얼마나 위험한가"를 가늠하는 자료로 봐 주세요.
                </p>
              </div>
            </div>

            <!-- ③ 두 종류의 위험 — 결론 -->
            <div class="card mt-lg">
              <div class="card__head">
                <h3>그런데 이보다 훨씬 큰 게 따로 있습니다</h3>
                <span class="badge badge--amber">가장 중요한 대목</span>
              </div>
              <div class="card__body">
                <p class="lede">
                  수익이 흩어지는 이유는 두 가지입니다. 하나는 <b>그해 시세와 작황</b>이고,
                  다른 하나는 <b>같은 해에 같은 작목을 해도 임가마다 결과가 다르다</b>는 점입니다.
                  작목을 섞어 줄일 수 있는 건 앞의 것뿐입니다. 뒤의 것은 산의 상태, 기술, 판로의
                  차이라서 무엇을 심든 따라옵니다.
                </p>
                <EChart v-if="riskOption" :option="riskOption" height="330px" />
                <div v-if="ratio" class="note note--warn mt-md">
                  <strong>임가 간 격차가 해마다의 변동보다 {{ fmt.dec(ratio, 0) }}배 큽니다.</strong>
                  무엇을 심을지 고르는 것보다 <b>어떻게 하느냐</b>가 수익을 훨씬 크게 가릅니다.
                  이 사이트가 전국 평균이 아니라 임가별로 따로 계산하는 이유가 여기 있습니다.
                  <div class="fs-sm mt-sm">
                    같은 작목 안에서 내가 어디쯤인지는 <RouterLink to="/detail">자세한 진단</RouterLink>에서,
                    무엇을 바꾸면 나아지는지는 <RouterLink to="/insight">수익 개선</RouterLink>에서 보실 수 있습니다.
                  </div>
                </div>
              </div>
            </div>

            <!-- ④ 작목별 표 + 방법 -->
            <div class="card mt-lg">
              <div class="card__head">
                <h3>작목별 숫자</h3>
                <button class="chip" @click="showMethod = !showMethod">
                  {{ showMethod ? '계산 방법 접기' : '어떻게 계산했나요' }}
                </button>
              </div>
              <div class="card__body">
                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>작목</th>
                        <th class="num">기대 수익률</th>
                        <th class="num">해마다 흔들리는 폭</th>
                        <th class="num">임가끼리 벌어지는 폭</th>
                        <th class="num">조사 임가</th>
                        <th class="num">조사 연도</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in pf.품목" :key="r.품목">
                        <td>{{ r.품목 }}</td>
                        <td class="num">{{ fmt.dec(r.기대수익_pct, 0) }}%</td>
                        <td class="num">±{{ fmt.dec(r.연도변동_pct, 0) }}%</td>
                        <td class="num">±{{ fmt.dec(r.임가격차_pct, 0) }}%</td>
                        <td class="num">{{ fmt.int(r.표본수) }}곳</td>
                        <td class="num">{{ r.조사연도[0] }}~{{ r.조사연도[r.조사연도.length - 1] }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <template v-if="showMethod">
                  <div class="note note--info mt-md fs-sm">{{ pf.방법 }}</div>

                  <h4 class="sub mt-md">작목끼리 같이 움직이는 정도</h4>
                  <p class="caveat" style="margin-bottom:10px">
                    두 작목이 같은 해에 함께 잘되면 +1, 반대로 움직이면 −1에 가깝습니다.
                    그런데 겹치는 조사 연도가 3년뿐인 짝이 있어, 그런 값은 우연히 극단으로 나오기
                    쉽습니다. 그래서 겹친 해가 적을수록 0쪽으로 끌어당겨 보수적으로 썼습니다.
                  </p>
                  <div class="table-wrap">
                    <table>
                      <thead>
                        <tr><th>작목 짝</th><th class="num">겹친 연도</th>
                          <th class="num">그대로 계산하면</th><th class="num">실제로 쓴 값</th></tr>
                      </thead>
                      <tbody>
                        <tr v-for="d in pf.상관" :key="`${d.a}-${d.b}`">
                          <td>{{ d.a }} · {{ d.b }}</td>
                          <td class="num">{{ d.공통연도 }}년</td>
                          <td class="num" style="opacity:.6">{{ fmt.signed(d.원상관, 2) }}</td>
                          <td class="num">{{ fmt.signed(d.수축후, 2) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </template>
              </div>
            </div>

            <div class="note note--info mt-lg fs-sm">{{ pf.한계 }}</div>
            <p class="caveat mt-sm">{{ pf.출처 }}</p>

          </template>
        </DataState>
      </div>
    </main>
  </div>
</template>

<style scoped>
.lede {
  font-size: 0.95rem; line-height: 1.75; color: var(--text-muted);
  margin-bottom: 16px; max-width: 74ch;
}
.sub { font-size: 0.92rem; font-weight: 700; margin: 0 0 4px; }
</style>
