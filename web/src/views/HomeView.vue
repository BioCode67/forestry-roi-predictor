<script setup>
/**
 * 임가가 처음 만나는 화면.
 * 네 가지만 고르면 "얼마 쓰면 얼마 남는다"를 금액으로 먼저 답한다.
 * 퍼센트·통계 용어는 뒤로 미루고, 실행할 수 있는 제안을 앞세운다.
 */
import { computed, inject, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import Answer from '../components/Answer.vue'
import TipList from '../components/TipList.vue'
import Term from '../components/Term.vue'
import EChart from '../components/EChart.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { SCALE_HINT, SECTOR_EASY } from '../lib/terms'
import { axisX, axisY, baseOption, palette, theme } from '../lib/charts'

const meta = inject('meta')
const farm = inject('farm')

const res = ref(null)
const mgmt = ref(null)
const loading = ref(false)
const error = ref('')

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
  timer = setTimeout(run, 240)
}, { deep: true, immediate: true })

api.management().then((d) => { mgmt.value = d }).catch(() => {})

const opts = (key) => {
  const d = meta.value?.codebook?.[key]
  return d ? Object.entries(d).map(([code, label]) => ({ code: Number(code), label })) : []
}
const sectorLabel = computed(() => meta.value?.codebook?.업종별?.[farm.업종별] ?? '')
const regionLabel = computed(() => meta.value?.codebook?.지역별?.[farm.지역별] ?? '')
const sectorEasy = computed(() => SECTOR_EASY[sectorLabel.value] || sectorLabel.value)

/* ------------------------------------------------------------- 결과 해석 */
/** 색은 '돈이 남는가'로만 정한다. 평균보다 낮다는 이유로 경고색을 쓰면 과하게 읽힌다. */
const verdict = computed(() => {
  if (!res.value) return null
  return res.value.income > 0 ? { tone: 'neutral' } : { tone: 'warn' }
})

const rank = computed(() => {
  if (res.value?.percentile == null) return null
  return Math.max(1, Math.round(100 - res.value.percentile))
})

/* 실행 제안 — 모델 결과와 통계 분석을 임가 언어로 옮긴다 */
const SECTOR_TO_CROP = { 밤재배업: '밤', 떫은감재배업: '떫은감', 버섯재배업: '버섯' }
const crop = computed(() => SECTOR_TO_CROP[sectorLabel.value])
const m = computed(() => (crop.value ? mgmt.value?.품목별?.[crop.value] : null))

const tips = computed(() => {
  const out = []
  const r = res.value
  if (!r) return out

  // ① 돈 쓰는 규모 조정
  const c = r.curve || []
  if (c.length) {
    const best = c.reduce((a, b) => (b.income > a.income ? b : a), c[0])
    const gain = best.income - r.income
    if (gain > 300000 && Math.abs(best.cost - r.cost) > 1000000) {
      const dir = best.cost > r.cost ? '더 쓰시면' : '덜 쓰시면'
      const diff = Math.abs(best.cost - r.cost)
      out.push({
        icon: '💰', title: `한 해 쓰는 돈을 ${fmt.won(diff)} ${dir} 더 남습니다`,
        desc: `지금 ${fmt.won(r.cost)} 쓰시는데, ${fmt.won(best.cost)} 정도가 가장 많이 남는 지점으로 보입니다. `
          + `그렇게 하면 남는 돈이 ${fmt.won(r.income)}에서 ${fmt.won(best.income)}으로 늘어납니다.`,
      })
    }
  }

  // ② 파는 시기
  const ship = m.value?.출하시기별_단가
  if (ship?.최고시기) {
    out.push({
      icon: '📅', title: `${ship.최고시기}에 파실 때 값을 가장 잘 받습니다`,
      desc: `이 시기에 kg당 약 ${fmt.int(ship.최고단가)}원이고, 가장 낮은 ${ship.최저시기}에는 `
        + `${fmt.int(ship.최저단가)}원입니다. ${ship.격차_배}배 차이입니다. `
        + `다만 ${ship.최저시기}에 파는 농가가 가장 많습니다.`,
      tone: 'info',
    })
  }

  // ③ 파는 곳
  const ch = m.value?.판매처별_단가
  if (ch?.최고판매처) {
    const v = ch.계열단가
    out.push({
      icon: '🏪', title: `${ch.최고판매처}로 파실 때 값을 더 받습니다`,
      desc: `${ch.최고판매처} kg당 ${fmt.int(v[ch.최고판매처])}원, `
        + `${ch.최저판매처} ${fmt.int(v[ch.최저판매처])}원으로 ${ch.격차_배}배 차이납니다.`,
      tone: 'info',
    })
  }

  // ④ 저장 · 인증
  const st = m.value?.저장경험별_단가
  if (st?.단가차_pct > 5) {
    out.push({
      icon: '🏬', title: `저장고를 쓰는 농가가 kg당 ${fmt.dec(st.단가차_pct, 0)}% 더 받습니다`,
      desc: '수확 직후 한꺼번에 내놓지 않고 시세를 보며 나눠 파는 것이 유리합니다. '
        + '다만 저장 설비를 갖춘 농가가 원래 규모도 크다는 점은 감안해 주세요.',
    })
  }
  const ce = m.value?.공식인증_프리미엄
  if (ce?.프리미엄_pct > 5) {
    out.push({
      icon: '🏅', title: `친환경·GAP 인증을 받은 농가가 kg당 ${fmt.dec(ce.프리미엄_pct, 0)}% 더 받습니다`,
      desc: '인증 취득을 검토해 보실 만합니다.',
    })
  }

  // ⑤ 작목 비교
  const s = r.sectors || []
  if (s.length) {
    const top = s[0]
    const mine = s.find((x) => x.sector === sectorLabel.value)
    if (mine && top.roi > mine.roi * 1.4) {
      out.push({
        icon: '🌱', title: `같은 조건이면 ${SECTOR_EASY[top.sector] || top.sector} 쪽이 더 남는 것으로 나옵니다`,
        desc: '바로 바꾸시라는 뜻은 아닙니다. 나무를 새로 심으면 수확까지 몇 해가 걸리고 '
          + '기술도 달라서, 참고 자료로만 봐 주세요.',
        tone: 'warn',
      })
    }
  }
  return out
})

/* ------------------------------------------------------------------ 차트 */
const bandOption = computed(() => {
  const r = res.value
  if (!r?.band) return null
  const t = theme()
  const [lo, , hi] = r.band.map((v) => v / 100 * r.cost)
  const pad = Math.max((hi - lo) * 0.12, 1)
  return baseOption({
    grid: { left: 12, right: 18, top: 44, bottom: 28, containLabel: true },
    legend: { show: false },
    tooltip: { show: false },
    xAxis: axisY({
      min: lo - pad, max: hi + pad,
      axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.won(v) },
      splitLine: { lineStyle: { color: t.grid, type: [4, 4] } },
    }),
    yAxis: axisX({ data: [''], axisLine: { show: false }, axisLabel: { show: false } }),
    series: [{
      type: 'custom',
      renderItem: (params, apiFn) => {
        const y = apiFn.coord([0, 0])[1]
        const xLo = apiFn.coord([lo, 0])[0]
        const xHi = apiFn.coord([hi, 0])[0]
        const xMid = apiFn.coord([r.income, 0])[0]
        const h = 38
        return {
          type: 'group',
          children: [
            { type: 'rect', shape: { x: xLo, y: y - h / 2, width: xHi - xLo, height: h, r: 9 },
              style: { fill: 'rgba(46,125,79,.22)' } },
            { type: 'line', shape: { x1: xMid, y1: y - h / 2 - 8, x2: xMid, y2: y + h / 2 + 8 },
              style: { stroke: palette.forest, lineWidth: 3 } },
            { type: 'text', style: { text: `예상 ${fmt.won(r.income)}`, x: xMid, y: y - h / 2 - 26,
              textAlign: 'center', fill: palette.forest, fontSize: 13, fontWeight: 700 } },
            { type: 'text', style: { text: `안 풀리면\n${fmt.won(lo)}`, x: xLo, y: y + h / 2 + 8,
              textAlign: 'left', fill: t.subtle, fontSize: 11.5, lineHeight: 15 } },
            { type: 'text', style: { text: `잘 풀리면\n${fmt.won(hi)}`, x: xHi, y: y + h / 2 + 8,
              textAlign: 'right', fill: t.subtle, fontSize: 11.5, lineHeight: 15 } },
          ],
        }
      },
      data: [[0, 0]],
    }],
  })
})

const curveOption = computed(() => {
  const c = res.value?.curve || []
  if (!c.length) return null
  const t = theme()
  const best = c.reduce((a, b) => (b.income > a.income ? b : a), c[0])
  return baseOption({
    grid: { left: 8, right: 20, top: 40, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: {
      trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `한 해 ${fmt.won(Number(ps[0].axisValue))} 쓰면<br/>`
        + `<b>${fmt.won(ps[0].value[1])}</b> 남습니다`,
    },
    xAxis: axisX({ type: 'value', splitLine: { show: false }, name: '한 해에 쓰는 돈',
      nameLocation: 'middle', nameGap: 30,
      axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.won(v) } }),
    yAxis: axisY({ name: '남는 돈',
      axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.won(v) } }),
    series: [{
      type: 'line', smooth: 0.25, symbol: 'none',
      data: c.map((p) => [p.cost, p.income]),
      lineStyle: { width: 3, color: palette.forest },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
        { offset: 0, color: 'rgba(46,125,79,.2)' }, { offset: 1, color: 'rgba(46,125,79,0)' }] } },
      markPoint: {
        symbol: 'pin', symbolSize: 46, itemStyle: { color: palette.amber },
        label: { fontSize: 10, color: '#fff', fontWeight: 700, formatter: '최대' },
        data: [{ coord: [best.cost, best.income] }],
      },
      markLine: {
        symbol: 'none', silent: true,
        lineStyle: { color: t.axis, type: 'dashed' },
        label: { formatter: '지금', color: t.subtle, fontSize: 11 },
        data: [{ xAxis: res.value.cost }],
      },
    }],
  })
})

/* 금액 입력을 만원 단위로 다루면 자릿수 실수가 줄어든다 */
const costMan = computed({
  get: () => Math.round(farm.임업경영비 / 10000),
  set: (v) => { farm.임업경영비 = Math.max(0, Number(v) || 0) * 10000 },
})
const COST_PRESETS = [300, 700, 1500, 3000, 6000]
</script>

<template>
  <main class="content">
    <div class="container" style="max-width:1080px">
      <div style="margin-bottom:22px">
        <h1>내 산에서 한 해에 얼마나 남을까요?</h1>
        <p class="section__desc" style="font-size:0.95rem">
          아래 네 가지만 고르시면, 전국 임가 조사 자료로 계산한 예상 금액을 알려드립니다.
          숫자를 바꾸시면 결과도 바로 바뀝니다.
        </p>
      </div>

      <!-- 입력 -->
      <div class="card" style="margin-bottom:22px">
        <div class="card__body" style="padding-top:18px">
          <div class="grid grid--4">
            <div class="field">
              <label class="field__label">① 무엇을 하십니까</label>
              <select class="select" v-model.number="farm.업종별">
                <option v-for="o in opts('업종별')" :key="o.code" :value="o.code">
                  {{ SECTOR_EASY[o.label] || o.label }}
                </option>
              </select>
              <p class="field__hint">{{ sectorLabel }}</p>
            </div>
            <div class="field">
              <label class="field__label">② 어디십니까</label>
              <select class="select" v-model.number="farm.지역별">
                <option v-for="o in opts('지역별')" :key="o.code" :value="o.code">{{ o.label }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field__label">③ 산이 얼마나 되십니까</label>
              <select class="select" v-model.number="farm.임지규모별">
                <option v-for="o in opts('임지규모별')" :key="o.code" :value="o.code">{{ o.label }}</option>
              </select>
              <p class="field__hint">{{ SCALE_HINT[farm.임지규모별] }}</p>
            </div>
            <div class="field">
              <label class="field__label">④ 한 해에 얼마나 쓰십니까</label>
              <div class="input-money">
                <input class="input" type="number" v-model.number="costMan" min="0" step="50" />
                <span class="input-money__unit">만원</span>
              </div>
              <div class="chips mt-sm">
                <button v-for="p in COST_PRESETS" :key="p" class="chip"
                        :class="{ 'chip--active': costMan === p }"
                        @click="costMan = p">{{ fmt.int(p) }}만</button>
              </div>
              <p class="field__hint">
                묘목·비료·농약·품삯·기계값 등 1년치 <Term k="임업경영비" label="드는 돈" />
              </p>
            </div>
          </div>

          <details style="margin-top:6px">
            <summary class="fs-sm muted" style="cursor:pointer">
              더 정확하게 — 연령·가구원수·다른 소득도 넣기
            </summary>
            <div class="grid grid--4 mt-md">
              <div class="field">
                <label class="field__label">경영주 연세</label>
                <select class="select" v-model.number="farm.연령별">
                  <option v-for="o in opts('연령별')" :key="o.code" :value="o.code">{{ o.label }}</option>
                </select>
              </div>
              <div class="field">
                <label class="field__label">가족 수</label>
                <select class="select" v-model.number="farm.가구원수별">
                  <option v-for="o in opts('가구원수별')" :key="o.code" :value="o.code">{{ o.label }}</option>
                </select>
              </div>
              <div class="field">
                <label class="field__label">임업 말고 버는 돈 (연)</label>
                <div class="input-money">
                  <input class="input" type="number" :value="Math.round(farm.임업외소득 / 10000)"
                         @input="farm.임업외소득 = ($event.target.value || 0) * 10000" step="50" />
                  <span class="input-money__unit">만원</span>
                </div>
              </div>
              <div class="field">
                <label class="field__label">가진 재산 (땅·시설 등)</label>
                <div class="input-money">
                  <input class="input" type="number" :value="Math.round(farm['기초_자본(순재산)'] / 10000)"
                         @input="farm['기초_자본(순재산)'] = ($event.target.value || 0) * 10000" step="1000" />
                  <span class="input-money__unit">만원</span>
                </div>
              </div>
            </div>
          </details>
        </div>
      </div>

      <DataState :loading="loading && !res" :error="error">
        <template v-if="res">
          <!-- 답 -->
          <Answer :tone="verdict?.tone">
            {{ regionLabel }}에서 {{ sectorEasy }}를 하시면서 한 해 {{ fmt.won(res.cost) }}을 쓰시면,
            <b>{{ fmt.won(res.income) }}</b> 정도 남을 것으로 보입니다.
            <template #sub>
              날씨와 시세에 따라 달라집니다. 잘 풀리면
              <b>{{ fmt.won(res.band ? res.band[2] / 100 * res.cost : res.income) }}</b>,
              안 풀리면
              <b>{{ fmt.won(res.band ? res.band[0] / 100 * res.cost : res.income) }}</b> 사이로 봅니다.
              <template v-if="rank">
                같은 농사를 짓는 농가 100곳 중 <b>{{ rank }}번째</b> 수준입니다.
              </template>
            </template>
          </Answer>

          <!-- 폭 -->
          <div v-if="res.band" class="card mt-lg">
            <div class="card__head">
              <h3>얼마나 오르내릴 수 있나요</h3>
              <span class="badge badge--grey">10곳 중 8곳이 이 범위</span>
            </div>
            <div class="card__body">
              <EChart v-if="bandOption" :option="bandOption" height="130px" />
              <p class="fs-sm muted mt-sm">
                날씨·병충해·시세는 미리 알 수 없어서 하나의 숫자로 딱 잘라 말씀드리기 어렵습니다.
                그래서 <Term k="예측구간" label="이 정도 범위" />로 알려드립니다.
                실제로 열 곳 중 여덟 곳은 이 안에 들어옵니다.
              </p>
            </div>
          </div>

          <!-- 제안 -->
          <div v-if="tips.length" class="section mt-lg">
            <div class="section__head"><h2>이렇게 하시면 더 나아집니다</h2></div>
            <TipList :tips="tips" />
          </div>

          <!-- 돈 쓰는 규모와 남는 돈 -->
          <div class="card mt-lg">
            <div class="card__head"><h3>돈을 얼마나 쓰면 가장 많이 남을까요</h3></div>
            <div class="card__body">
              <p class="fs-sm muted" style="margin-bottom:10px">
                다른 조건은 그대로 두고 한 해에 쓰는 돈만 바꿔봤을 때, 남는 돈이 어떻게 달라지는지입니다.
              </p>
              <EChart v-if="curveOption" :option="curveOption" height="300px" />
            </div>
          </div>

          <!-- 더 보기 -->
          <div class="card mt-lg">
            <div class="card__head"><h3>더 자세히 알아보기</h3></div>
            <div class="card__body">
              <div class="grid grid--3" style="gap:10px">
                <RouterLink class="linkcard" to="/shipping">
                  <b>언제 팔면 좋을까</b>
                  <span>시기별·판매처별로 받는 값이 얼마나 다른지 봅니다</span>
                </RouterLink>
                <RouterLink class="linkcard" to="/market">
                  <b>내 작물 값은 얼마인가</b>
                  <span>지역별 kg당 값과 최근 몇 해 흐름을 봅니다</span>
                </RouterLink>
                <RouterLink class="linkcard" to="/insight">
                  <b>어떻게 더 벌 수 있나</b>
                  <span>등급·나무 나이·잘하는 농가와의 차이를 봅니다</span>
                </RouterLink>
              </div>
              <p class="caveat mt-md">
                이 결과는 전국 임가를 조사한 통계로 계산한 <b>참고 예측</b>입니다.
                실제 수익은 산의 상태, 그해 날씨, 시세에 따라 달라집니다.
                계산 근거가 궁금하시면 <RouterLink to="/model">예측이 얼마나 맞는지</RouterLink> 와
                <RouterLink to="/about">쓰인 자료</RouterLink> 를 보실 수 있습니다.
              </p>
            </div>
          </div>
        </template>
      </DataState>
    </div>
  </main>
</template>

<style scoped>
.linkcard {
  display: flex; flex-direction: column; gap: 4px;
  padding: 15px 17px; border-radius: var(--r-md);
  border: 1px solid var(--border); background: var(--surface-2);
  text-decoration: none; color: var(--text);
  transition: border-color .15s, transform .15s, box-shadow .15s;
}
.linkcard:hover {
  border-color: var(--forest-400); text-decoration: none;
  transform: translateY(-1px); box-shadow: var(--shadow-md);
}
.linkcard b { font-size: 0.95rem; font-weight: 680; }
.linkcard span { font-size: 0.82rem; color: var(--text-muted); line-height: 1.5; }
details summary::-webkit-details-marker { color: var(--text-subtle); }
</style>
