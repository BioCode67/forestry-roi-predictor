<script setup>
import { computed, inject } from 'vue'
import { fmt } from '../lib/api'

const meta = inject('meta')
const farm = inject('farm')

const CATS = [
  ['지역별', '지역'],
  ['업종별', '영림 업종'],
  ['임지규모별', '임지 규모'],
  ['전/겸업별', '전업 / 겸업'],
  ['연령별', '경영주 연령대'],
  ['가구원수별', '가구원 수'],
]

const MONEY = [
  ['임업경영비', '연간 임업경영비', 0, 500000000, 1000000,
    '종묘·비료·농약·고용노력·감가상각 등 임업 생산에 투입하는 연간 비용'],
  ['임업외소득', '임업외소득', -100000000, 500000000, 1000000, ''],
  ['기초_자본(순재산)', '기초 자본(순재산)', 0, 5000000000, 10000000, ''],
  ['연초보유', '연초 보유 현금', 0, 1000000000, 1000000, ''],
]

const options = (key) => {
  const d = meta.value?.codebook?.[key]
  return d ? Object.entries(d).map(([code, label]) => ({ code: Number(code), label })) : []
}

const years = [2019, 2020, 2021, 2022, 2023]

const totalScale = computed(() =>
  fmt.won(Number(farm.임업경영비) + Number(farm['기초_자본(순재산)'])))

const label = (key) => meta.value?.codebook?.[key]?.[farm[key]] ?? '—'
</script>

<template>
  <div v-if="!meta" class="stack stack--sm">
    <div class="skeleton" style="height:13px;width:52%"></div>
    <div class="skeleton" style="height:34px"></div>
    <div class="skeleton" style="height:34px"></div>
    <div class="skeleton" style="height:34px"></div>
  </div>

  <template v-else>
    <div class="sidebar__group">
      <div class="sidebar__title">임가 제원</div>
      <div v-for="[key, label] in CATS" :key="key" class="field">
        <label class="field__label">{{ label }}</label>
        <select class="select" v-model.number="farm[key]">
          <option v-for="o in options(key)" :key="o.code" :value="o.code">{{ o.label }}</option>
        </select>
      </div>
      <p class="field__hint">임가경제조사 코드 체계와 동일한 구분입니다.</p>
    </div>

    <div class="sidebar__group">
      <div class="sidebar__title">경영 규모</div>
      <div v-for="[key, label, min, max, step, hint] in MONEY" :key="key" class="field">
        <label class="field__label">{{ label }}</label>
        <div class="input-money">
          <input class="input" type="number" v-model.number="farm[key]"
                 :min="min" :max="max" :step="step" />
          <span class="input-money__unit">원</span>
        </div>
        <input class="range mt-sm" type="range" v-model.number="farm[key]"
               :min="min" :max="max" :step="step" />
        <p class="field__hint">
          {{ fmt.won(farm[key]) }}<template v-if="hint"> · {{ hint }}</template>
        </p>
      </div>
    </div>

    <div class="sidebar__group">
      <div class="sidebar__title">기준 연도</div>
      <div class="chips">
        <button v-for="y in years" :key="y" class="chip"
                :class="{ 'chip--active': farm.조사연도 === y }"
                @click="farm.조사연도 = y">{{ y }}</button>
      </div>
    </div>

    <div class="note note--info fs-xs">
      입력값을 바꾸면 모든 화면이 즉시 다시 계산됩니다.
      현재 경영 규모 합계 <b>{{ totalScale }}</b>
    </div>

    <!-- 아래가 비어 보이지 않도록, 지금 조건과 계산 근거를 함께 밝힙니다 -->
    <div class="sb-foot">
      <p class="sb-foot__head">지금 조건 요약</p>
      <dl class="sb-foot__list">
        <div><dt>지역</dt><dd>{{ label('지역별') }}</dd></div>
        <div><dt>업종</dt><dd>{{ label('업종별') }}</dd></div>
        <div><dt>임지</dt><dd>{{ label('임지규모별') }}</dd></div>
        <div><dt>기준 연도</dt><dd>{{ farm.조사연도 }}년</dd></div>
      </dl>

      <p class="sb-foot__head" style="margin-top:18px">계산에 쓰인 자료</p>
      <ul class="sb-foot__src">
        <li>임가경제조사 2019~2023</li>
        <li>임산물생산비조사 2018~2024</li>
        <li>임산물생산조사 2022~2024</li>
        <li>임업경영실태조사 2018·2020</li>
      </ul>
      <p class="sb-foot__note">
        전국 임가를 조사한 국가승인통계로 계산한 참고 예측입니다.
        실제 수익은 산의 상태와 그해 날씨·시세에 따라 달라집니다.
      </p>
    </div>
  </template>
</template>

<style scoped>
.sb-foot { margin-top: 22px; padding-top: 20px; border-top: 1px solid var(--border); }
.sb-foot__head {
  font-size: 0.7rem; font-weight: 750; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--text-subtle); margin-bottom: 10px;
}
.sb-foot__list { margin: 0; display: flex; flex-direction: column; gap: 7px; }
.sb-foot__list > div { display: flex; justify-content: space-between; gap: 10px; font-size: 0.82rem; }
.sb-foot__list dt { color: var(--text-subtle); margin: 0; }
.sb-foot__list dd { margin: 0; font-weight: 620; text-align: right; }
.sb-foot__src {
  margin: 0; padding-left: 15px; display: flex; flex-direction: column; gap: 5px;
  font-size: 0.79rem; color: var(--text-muted);
}
.sb-foot__note {
  margin-top: 16px; font-size: 0.76rem; line-height: 1.6; color: var(--text-subtle);
  padding-left: 11px; border-left: 2px solid var(--border-strong);
}
</style>
