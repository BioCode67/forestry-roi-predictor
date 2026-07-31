<script setup>
import { computed, inject } from 'vue'
import SectionHead from '../components/SectionHead.vue'
import PageHero from '../components/PageHero.vue'
import MetricCard from '../components/MetricCard.vue'
import { fmt } from '../lib/api'

const meta = inject('meta')
const health = inject('health')

const ds = computed(() => meta.value?.benchmark_a?.dataset)
const dsB = computed(() => meta.value?.benchmark_b?.dataset)

const SOURCES = [
  {
    kind: '임업통계 (필수)', badge: 'green',
    org: '통계청 MDIS / 산림청 · 한국임업진흥원',
    name: '임가경제조사 총괄(제공) 마이크로데이터',
    years: '2019 ~ 2023',
    use: 'Model A — 임가 단위 종합 수익성 예측',
  },
  {
    kind: '임업통계 (필수)', badge: 'green',
    org: '통계청 MDIS / 산림청 · 한국임업진흥원',
    name: '임산물생산비조사 — 밤 · 대추 · 떫은감 · 표고(노지/톱밥)',
    years: '2018 ~ 2024',
    use: 'Model B — 품목 단위 단위면적당 수익성, 비목·공정 진단',
  },
  {
    kind: '임업통계 (필수)', badge: 'green',
    org: '통계청 MDIS / 산림청',
    name: '임산물생산조사 전품목',
    years: '2022 ~ 2024',
    use: '전 임산물 시군구별 실측 단가 · 지역 격차 · 주산지 특화도',
  },
  {
    kind: '임업통계 (필수)', badge: 'green',
    org: '통계청 MDIS / 산림청',
    name: '임업경영실태조사 — 밤 · 떫은감 · 버섯 · 임업경영인',
    years: '2018, 2020',
    use: '출하시기 · 판매처 · 저장 · 인증의 수취 단가 효과',
  },
  {
    kind: '공공데이터 (융복합)', badge: 'amber',
    org: '한국농수산식품유통공사',
    name: 'KAMIS 농수산물유통정보 — 품목별 도매가격',
    years: '최근 12~15개월',
    use: '월별 가격 계절성 (단감 · 느타리 · 새송이 · 팽이버섯)',
  },
  {
    kind: '공공데이터 (융복합)', badge: 'amber',
    org: '산림청',
    name: '보조금 세부사업 정보',
    years: '2021-10-21 공개',
    use: '자부담 기준 실효 ROI 산출',
  },
]

const PIPELINE = [
  ['src/preprocess.py', '임가경제조사 적재·스키마 표준화·정제·파생변수'],
  ['src/preprocess_cost.py', '임산물생산비조사 정규화·품목별 IQR·비목 구성비'],
  ['src/train_optuna.py', 'Model A — 3종 벤치마크 + CUDA XGBoost 튜닝'],
  ['src/train_cost.py', 'Model B — 품목 단위 모델'],
  ['src/train_quantile.py', '분위수 회귀 예측구간 (P10/P50/P90)'],
  ['src/insights.py', '등급 단가 · 수령 곡선 · 선도임가 벤치마크'],
  ['src/production.py', '지역별 단가 · 특화도 · 가공 경제성'],
  ['src/management.py', '출하시기 · 판매처 수취단가 추정'],
  ['src/shipping.py', '임업통계 × KAMIS 융복합 출하 전략'],
  ['src/subsidy.py', '보조사업 자부담 기준 실효 ROI'],
  ['api/main.py', 'FastAPI 백엔드'],
  ['web/', 'Vue 3 프런트엔드'],
]
</script>

<template>
  <div>
    <PageHero
      src="/img/hero.jpg"
      eyebrow="데이터·방법론"
      title="어떤 자료로 어떻게 계산했나요"
      lead="산림청 국가승인통계 4종을 계층으로 결합하고, 공공데이터 3종을 융복합했습니다."
    />

  <main class="content">
    <div class="container">

      <div v-if="ds" class="grid grid--4">
        <MetricCard accent label="Model A 분석 표본" :value="fmt.int(ds.rows)" unit="임가-연도"
          :delta="`설명변수 ${ds.n_features}개`" delta-dir="flat" />
        <MetricCard v-if="dsB" label="Model B 분석 표본" :value="fmt.int(dsB.rows)" unit="관측"
          :delta="`설명변수 ${dsB.n_features}개`" delta-dir="flat" />
        <MetricCard label="분할" :value="`${fmt.int(ds.train)} / ${fmt.int(ds.valid)} / ${fmt.int(ds.test)}`"
          :delta="`Train / Valid / Test · seed ${ds.seed}`" delta-dir="flat" />
        <MetricCard label="목표변수" value="임업 ROI" unit="%"
          :delta="ds.target_definition" delta-dir="flat" />
      </div>

      <!-- 데이터 출처 -->
      <div class="card mt-lg">
        <div class="card__head"><h3>활용 데이터</h3></div>
        <div class="card__body">
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>구분</th><th>제공기관</th><th>데이터명</th><th class="nowrap">대상 연도</th><th>활용</th></tr>
              </thead>
              <tbody>
                <tr v-for="s in SOURCES" :key="s.name">
                  <td><span class="badge" :class="`badge--${s.badge}`">{{ s.kind }}</span></td>
                  <td class="fs-sm">{{ s.org }}</td>
                  <td class="fs-sm"><b>{{ s.name }}</b></td>
                  <td class="fs-sm nowrap">{{ s.years }}</td>
                  <td class="fs-sm muted">{{ s.use }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- 2계층 모델 -->
      <div class="grid grid--2 mt-lg">
        <div class="card">
          <div class="card__head"><h3>2계층 모델 구조</h3></div>
          <div class="card__body">
            <div class="stack stack--md">
              <div class="note note--good">
                <strong>Model A — 임가경제조사</strong><br />
                <span class="fs-sm">"내 임가 전체가 올해 얼마를 남길 수 있나?"<br />
                임가 단위 종합 수익성. 지역·업종·규모·자본 등 구조 변수 중심.</span>
              </div>
              <div class="note note--good">
                <strong>Model B — 임산물생산비조사</strong><br />
                <span class="fs-sm">"이 품목을 ha당 이렇게 투입하면 얼마가 남나? 비목 배분은 적정한가?"<br />
                비목별 지출과 작업 공정별 노동시간까지 반영.</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card__head"><h3>정보 누출 통제</h3></div>
          <div class="card__body">
            <p class="fs-sm">
              ROI = 임업소득 ÷ 임업경영비 이고 임업소득 = 임업총수입 − 임업경영비 이므로,
              <b>임업총수입 · 임업소득 및 이를 포함하는 모든 합계항목</b>(임가소득, 경상소득,
              임가순소득, 임가처분가능소득, 임가경제잉여)을 설명변수에서 전면 배제했습니다.
            </p>
            <p class="fs-sm mt-md">
              반면 <b>임업경영비는 유지</b>했습니다. ROI의 분모이기는 하나 분자인 임업총수입을
              결정하지 않으며, 임가가 영농계획 시점에 스스로 정하는 사전(ex-ante) 의사결정
              변수이기 때문입니다. 이 통제를 하지 않으면 R²가 1.0에 수렴하는 무의미한 모델이 됩니다.
            </p>
            <p class="fs-sm mt-md">
              Model B에서도 평가액·수확량·순수익·생산비합계·내급비를 전량 제외했습니다.
              다만 무기질·유기질 시비량은 산출이 아니라 <b>투입</b>이므로 유지했습니다.
            </p>
          </div>
        </div>
      </div>

      <!-- 방법론 -->
      <div class="card mt-lg">
        <div class="card__head"><h3>분석 절차</h3></div>
        <div class="card__body">
          <ol class="fs-sm stack stack--sm" style="padding-left:20px;margin:0">
            <li><b>적재</b> — MDIS 배포본의 CP949 인코딩·구분자 자동 탐지, 파일설계서(xlsx) 코드북 자동 파싱</li>
            <li><b>스키마 표준화</b> — 연도별 표기 흔들림 흡수 (2021년 영문 변수코드 접두사, 임외소득/임업외소득,
              지출액1·2 접미 숫자, ha당/만본당 단위, 경영수준별 5·6 ↔ 1·2 코드 조화)</li>
            <li><b>정제</b> — MDIS 결측코드 치환, 임업 미영위 임가 제외, ROI에 1.5×IQR·비용 항목에 3.0×IQR 규칙 적용</li>
            <li><b>탐색</b> — Optuna TPE, 목적함수는 학습셋 5-fold 교차검증 OOF RMSE.
              워커 스레드를 RTX A6000 2장에 라운드로빈 배정해 병렬 탐색</li>
            <li><b>평가</b> — 학습에 한 번도 쓰이지 않은 Test 10%로 R²·RMSE·MAE 산출</li>
            <li><b>불확실성</b> — 분위수 회귀로 P10/P50/P90을 학습해 구간으로 제시</li>
          </ol>
        </div>
      </div>

      <!-- 파이프라인 -->
      <div class="card mt-lg">
        <div class="card__head"><h3>구성</h3></div>
        <div class="card__body">
          <div class="table-wrap">
            <table>
              <thead><tr><th>파일</th><th>역할</th></tr></thead>
              <tbody>
                <tr v-for="[f, d] in PIPELINE" :key="f">
                  <td class="mono">{{ f }}</td><td class="fs-sm muted">{{ d }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- 한계 -->
      <div class="card mt-lg">
        <div class="card__head">
          <h3>분석의 한계</h3>
          <span class="badge badge--amber">명시</span>
        </div>
        <div class="card__body stack stack--md fs-sm">
          <p>
            <b>인과가 아닌 상관</b> — 저장 설비·공식인증·정책자금은 모두 임가가 선택한 결과이며,
            선택할 수 있었던 임가가 애초에 규모·자본·의지에서 다릅니다. 추정된 격차에는
            선택효과가 섞여 있습니다.
          </p>
          <p>
            <b>잡음이 큰 목표변수</b> — 임가 ROI는 기상·병충해·시장가격 등 조사되지 않은 요인의
            영향을 크게 받습니다. R²의 절대 수준보다 동일 평가셋에서 현행 방식 대비 개선폭이
            의미 있는 비교이며, 예측구간을 함께 제시하는 이유이기도 합니다.
          </p>
          <p>
            <b>연계키 부재</b> — 임가경제조사·임산물생산비조사·임산물생산조사·임업경영실태조사에
            임가 단위 연계키가 없어 조사 간 결합이 불가능합니다. 계층별 분석으로 우회했습니다.
          </p>
          <p>
            <b>KAMIS 취급 범위</b> — 일일 가격조사 대상 63개 품목 중 임산물은 단감·느타리·새송이·
            팽이버섯뿐이며, 기간 조회를 지원하지 않아 최근 1개 순환주기만 확보됩니다.
            밤·대추·떫은감·표고의 가격은 임산물생산조사(연 단위)로 대체했습니다.
          </p>
        </div>
      </div>

      <!-- 가동 상태 -->
      <div v-if="health" class="card mt-lg">
        <div class="card__head"><h3>시스템 상태</h3></div>
        <div class="card__body">
          <div class="row row--wrap" style="gap:8px">
            <span v-for="(v, k) in health.models" :key="k" class="badge"
                  :class="v ? 'badge--green' : 'badge--grey'">{{ k }} {{ v ? '가동' : '미학습' }}</span>
            <span v-for="(v, k) in health.datasets" :key="k" class="badge"
                  :class="v ? 'badge--sky' : 'badge--grey'">{{ k }} {{ v ? '연결' : '없음' }}</span>
          </div>
        </div>
      </div>
    </div>
  </main>
  </div>
</template>
