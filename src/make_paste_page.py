"""
붙여넣기용 페이지 — docs/제출본_붙여넣기용.html

한컴독스에 이미 손으로 써 넣은 부분이 있으면 문서를 통째로 여는 것이 도움이 되지
않습니다. 필요한 절만 골라 가져가야 합니다. 그래서 절마다 복사 단추를 붙인
페이지를 만듭니다.

내용은 만들어진 .docx에서 읽습니다. 본문을 두 곳에 두면 한쪽만 고치고 넘어가는
일이 반드시 생깁니다. 문서가 원본이고 이 페이지는 그것을 옮긴 것입니다.

복사는 서식이 있는 상태(text/html)와 글자만(text/plain) 두 벌을 함께 넣습니다.
한컴은 앞쪽을 받아 표와 색을 그대로 살립니다.

실행: python src/make_paste_page.py
"""
from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET
import zipfile

from preview_docx import W, para_html, rels, table_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "제출본_임과함께_데이터분석부문.docx")
OUT = os.path.join(ROOT, "docs", "제출본_붙여넣기용.html")
OUT_WEB = os.path.join(ROOT, "docs", "_paste_web.html")

# 한컴이 붙여넣기에서 그대로 받는 글꼴로 맞춥니다. 웹폰트를 심어 봐야
# 한글 문서는 어차피 자기 글꼴로 다시 그립니다.
DOC_FONT = "'맑은 고딕','Malgun Gothic','Apple SD Gothic Neo',sans-serif"

SECTION_RE = re.compile(r"^([1-5])\)\s*(.+)$")


def is_h1(p) -> str | None:
    """절 제목(1) ~ 5))이면 그 글자를 돌려줍니다."""
    text = "".join(t.text or "" for t in p.iter(W + "t")).strip()
    m = SECTION_RE.match(text)
    return text if m else None


def split_sections(z, rel_map, body):
    """표지와 다섯 개 절로 나눕니다."""
    secs = [{"id": "cover", "num": "표지", "title": "표지 · 요약표", "html": []}]
    for el in body:
        if el.tag == W + "p":
            title = is_h1(el)
            if title:
                num, rest = title.split(")", 1)
                secs.append({"id": f"s{num}", "num": f"{num})",
                             "title": rest.strip(), "html": []})
            secs[-1]["html"].append(para_html(z, rel_map, el))
        elif el.tag == W + "tbl":
            secs[-1]["html"].append(table_html(z, rel_map, el))
    for s in secs:
        s["html"] = "".join(s["html"])
    return secs



# 붙임1(신청서)에 들어갈 문구. 본문(붙임3)이 아니라 양식 칸을 채우는 글이라
# 문서에서 뽑아 올 수 없어 여기 둡니다. 수치는 models/*.json과 대조한 값입니다.
FORM_HTML = """
<p style="font-weight:700;font-size:11pt;color:#23593A">기획 개요 (분석·활용 개요)</p>
<p>현행 임업통계는 전국·지역·업종 단위의 거시 평균으로 공표되어, 개별 임가가 “내 조건에서
얼마를 벌 수 있는가”에 답하지 못합니다. 실제로 지역별×업종별 단순 평균을 예측기로 세워
검증하니 설명력이 R² 0.043에 그쳤습니다. 개별 임가 성과의 4.3%밖에 설명하지 못한다는
뜻입니다.</p>
<p>본 과제는 임가경제조사·임산물생산비조사·임산물생산조사·임업경영실태조사 4종의
마이크로데이터를 계층으로 결합했습니다. 임가 단위 종합 수익성은 Model A가, 품목 단위
정밀 진단은 Model B가 맡으며, 두 모델 모두 CUDA XGBoost와 Optuna 교차검증으로
최적화했습니다. 그 결과 Model A는 현행 방식 대비 <b>4.05배</b>(R² 0.174), Model B는
<b>5.95배</b>(R² 0.624)의 설명력을 확보했습니다. 나아가 임가경제조사가 패널 자료라는 점을
확인하고 직전 연도 실적을 결합하자 <b>10.2배</b>(R² 0.280)까지 올랐습니다.</p>
<p>여기에 KAMIS 도매가격·산림청 보조금 세부사업·기상청 지상관측을 융복합해, 언제·어디에
팔지, 등급을 어떻게 관리할지, 어떤 보조사업을 쓸지까지 금액으로 환산해 제시합니다.
결과물은 임가가 네 가지만 고르면 답이 나오는 웹 서비스(FastAPI + Vue 3)와 전 과정을
재현할 수 있는 분석 코드입니다.</p>

<p style="font-weight:700;font-size:11pt;color:#23593A;margin-top:14pt">기획서 요약</p>
<p>① 임업통계 4종을 임가 단위·품목 단위 2계층 모델로 결합해 개별 임가 수익성을 예측</p>
<p>② 현행 공표 방식(단순 평균) 대비 설명력 4.05배 향상, 평균절대오차 10.2% 감소</p>
<p>③ 임가경제조사의 패널 구조를 복원해 설명력을 10.2배까지 확대 — 새 조사 항목 없이
연도 간 대조표만으로 얻는 개선</p>
<p>④ 1차 학습에서 나온 R² 0.91이 데이터 누수임을 자체 적발해 0.62로 교정 (피처–타깃 상관
0.885 → 0.344), 경위를 그대로 기재</p>
<p>⑤ 잡음이 큰 지표임을 감추지 않고 예측구간을 함께 제시 (구간 포함률 78.2%)</p>
<p>⑥ 출하시기 1.82배·품질등급 4.22배(밤)·지역 9.79배(잣, 시군구 17곳) 격차를 실측해 개선
여지를 금액으로 환산</p>
<p>⑦ 임가용 웹 서비스와 전 과정 재현 가능한 코드를 함께 제출</p>
"""

PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>제출본 붙여넣기 — 임과 함께</title>
<style>
:root {{
  --ground:#EDF1EE; --paper:#FCFDFC; --ink:#17201B; --muted:#58665D;
  --faint:#7C8C82; --line:#D8E1DA; --line-soft:#E7EDE9;
  --forest:#2E7D4F; --forest-deep:#23593A; --forest-wash:#E8F1EB;
  --amber:#A9600A; --amber-wash:#FBF2E3;
  --shadow:0 1px 2px rgba(23,32,27,.05), 0 12px 32px rgba(23,32,27,.08);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --ground:#0D1411; --paper:#151E19; --ink:#E4EDE7; --muted:#9CAFA3;
    --faint:#7E9188; --line:#26332C; --line-soft:#1E2922;
    --forest:#6FBF8E; --forest-deep:#2C6E48; --forest-wash:#17291F;
    --amber:#D9A05B; --amber-wash:#2A2114;
    --shadow:0 1px 2px rgba(0,0,0,.3), 0 14px 36px rgba(0,0,0,.4);
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0D1411; --paper:#151E19; --ink:#E4EDE7; --muted:#9CAFA3;
  --faint:#7E9188; --line:#26332C; --line-soft:#1E2922;
  --forest:#6FBF8E; --forest-deep:#2C6E48; --forest-wash:#17291F;
  --amber:#D9A05B; --amber-wash:#2A2114;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 14px 36px rgba(0,0,0,.4);
}}
:root[data-theme="light"] {{
  --ground:#EDF1EE; --paper:#FCFDFC; --ink:#17201B; --muted:#58665D;
  --faint:#7C8C82; --line:#D8E1DA; --line-soft:#E7EDE9;
  --forest:#2E7D4F; --forest-deep:#23593A; --forest-wash:#E8F1EB;
  --amber:#A9600A; --amber-wash:#FBF2E3;
  --shadow:0 1px 2px rgba(23,32,27,.05), 0 12px 32px rgba(23,32,27,.08);
}}

* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:{doc_font};
  font-size:15px; line-height:1.62; letter-spacing:-.003em;
  -webkit-font-smoothing:antialiased;
}}
h1,h2,h3 {{ margin:0; text-wrap:balance; word-break:keep-all; }}
p, li, td {{ word-break:keep-all; overflow-wrap:break-word; }}

/* ── 머리 ─────────────────────────────────────────────── */
.top {{
  border-bottom:1px solid var(--line); background:var(--paper);
  position:sticky; top:0; z-index:20;
}}
.top__in {{
  max-width:1220px; margin:0 auto; padding:18px 24px;
  display:flex; align-items:baseline; gap:16px; flex-wrap:wrap;
}}
.eyebrow {{
  font-size:11px; font-weight:700; letter-spacing:.14em;
  text-transform:uppercase; color:var(--forest);
}}
.top h1 {{ font-size:19px; font-weight:750; letter-spacing:-.02em; }}
.top__note {{ font-size:13px; color:var(--muted); margin-left:auto; }}

/* ── 얼개 ─────────────────────────────────────────────── */
.wrap {{
  max-width:1220px; margin:0 auto; padding:26px 24px 90px;
  display:grid; grid-template-columns:266px minmax(0,1fr); gap:30px;
  align-items:start;
}}
@media (max-width:940px) {{ .wrap {{ grid-template-columns:1fr; }} }}

/* ── 왼쪽 조작판 ─────────────────────────────────────── */
.rail {{ position:sticky; top:76px; display:flex; flex-direction:column; gap:14px; }}
@media (max-width:940px) {{ .rail {{ position:static; }} }}
.panel {{
  background:var(--paper); border:1px solid var(--line);
  border-radius:12px; padding:16px 17px;
}}
.panel__t {{
  font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase;
  color:var(--faint); margin-bottom:11px;
}}
.how {{ font-size:12.6px; color:var(--muted); line-height:1.66; }}
.how b {{ color:var(--ink); font-weight:700; }}
.how ol {{ margin:8px 0 0; padding-left:17px; display:flex; flex-direction:column; gap:5px; }}

.navlist {{ display:flex; flex-direction:column; gap:2px; }}
.navitem {{
  display:flex; align-items:center; gap:9px; width:100%;
  padding:8px 9px; border:0; border-radius:8px; background:none;
  font:inherit; font-size:13.4px; color:var(--ink); text-align:left;
  cursor:pointer; text-decoration:none;
  transition:background .13s ease;
}}
.navitem:hover {{ background:var(--forest-wash); }}
.navitem__n {{
  flex:none; width:24px; font-size:11.5px; font-weight:750;
  color:var(--forest); font-variant-numeric:tabular-nums;
}}
.navitem__c {{ flex:none; margin-left:auto; font-size:11px; color:var(--faint); }}
.navitem.is-done .navitem__c {{ color:var(--forest); font-weight:700; }}

.btn {{
  display:inline-flex; align-items:center; justify-content:center; gap:7px;
  width:100%; padding:10px 14px; border-radius:9px;
  border:1px solid var(--forest-deep); background:var(--forest-deep); color:#fff;
  font:inherit; font-size:13.4px; font-weight:650; cursor:pointer;
  transition:filter .13s ease, transform .08s ease;
}}
.btn:hover {{ filter:brightness(1.1); }}
.btn:active {{ transform:translateY(1px); }}
.btn--ghost {{
  background:none; color:var(--ink); border-color:var(--line);
}}
.btn--ghost:hover {{ background:var(--forest-wash); border-color:var(--forest); }}
.btn:focus-visible, .navitem:focus-visible {{
  outline:2px solid var(--forest); outline-offset:2px;
}}

.warn {{
  background:var(--amber-wash); border:1px solid color-mix(in srgb, var(--amber) 32%, transparent);
  border-radius:10px; padding:12px 14px; font-size:12.4px; line-height:1.62; color:var(--ink);
}}
.warn b {{ color:var(--amber); }}

/* ── 문서 ─────────────────────────────────────────────── */
.doc {{ display:flex; flex-direction:column; gap:18px; }}
.sec {{
  background:var(--paper); border:1px solid var(--line);
  border-radius:12px; box-shadow:var(--shadow); overflow:hidden;
  scroll-margin-top:82px;
}}
.sec__bar {{
  display:flex; align-items:center; gap:12px; flex-wrap:wrap;
  padding:13px 20px; border-bottom:1px solid var(--line-soft);
  background:linear-gradient(180deg, var(--forest-wash), transparent);
}}
.sec__num {{
  font-size:12px; font-weight:750; color:var(--forest);
  font-variant-numeric:tabular-nums;
}}
.sec__t {{ font-size:15px; font-weight:720; letter-spacing:-.018em; }}
.sec__meta {{ font-size:11.6px; color:var(--faint); font-variant-numeric:tabular-nums; }}
.sec__act {{ margin-left:auto; display:flex; gap:8px; }}
.sec__act .btn {{ width:auto; padding:7px 13px; font-size:12.4px; }}

.body {{ padding:22px 26px 26px; background:#fff; color:#17201B; }}
@media (prefers-color-scheme: dark) {{ .body {{ background:#F7F9F7; }} }}
:root[data-theme="dark"] .body {{ background:#F7F9F7; }}
:root[data-theme="light"] .body {{ background:#fff; }}

.body p {{ margin:0 0 5pt; font-size:10.5pt; line-height:1.34; }}
.body .sp {{ height:6pt; }}
.body table {{
  border-collapse:collapse; width:100%; margin:5pt 0 9pt; table-layout:fixed;
}}
.body td {{ padding:2.8pt 5pt; vertical-align:middle; }}
.body td p {{ margin:0; font-size:9.1pt; line-height:1.16; }}
.body img {{ display:block; margin:7pt auto 3pt; max-width:100%; height:auto; }}
.tablescroll {{ overflow-x:auto; }}

.toast {{
  position:fixed; left:50%; bottom:30px; transform:translate(-50%, 14px);
  background:var(--forest-deep); color:#fff; padding:11px 20px; border-radius:999px;
  font-size:13.4px; font-weight:600; box-shadow:0 8px 26px rgba(0,0,0,.24);
  opacity:0; pointer-events:none; transition:opacity .2s ease, transform .2s ease;
  z-index:60;
}}
.toast.on {{ opacity:1; transform:translate(-50%, 0); }}
@media (prefers-reduced-motion: reduce) {{
  * {{ transition:none !important; }}
}}
</style>
</head>
<body>

<header class="top">
  <div class="top__in">
    <span class="eyebrow">임과 함께</span>
    <h1>제출본 붙여넣기</h1>
    <span class="top__note">2026년 임업통계 활용 경진대회 · 데이터 분석 부문</span>
  </div>
</header>

<div class="wrap">
  <aside class="rail">
    <div class="panel">
      <div class="panel__t">쓰는 법</div>
      <div class="how">
        한컴독스에 이미 써 넣으신 부분이 있으면, 필요한 절만 골라 가져가십시오.
        <ol>
          <li>아래에서 절을 고릅니다</li>
          <li><b>이 절 복사</b>를 누릅니다</li>
          <li>한컴독스에서 <b>Ctrl+V</b></li>
        </ol>
      </div>
    </div>

    <div class="panel">
      <div class="panel__t">절 고르기</div>
      <nav class="navlist">{nav}</nav>
    </div>

    <button class="btn" data-copy-all>문서 전체 복사</button>

    <div class="warn">
      <b>그림이 안 따라오면</b> — 붙여넣기로 그림까지 옮기는 것은 한컴 판본에 따라
      됩니다. 안 되면 본문만 붙여넣고, 그림은 <b>제출본_그림모음.zip</b>에서
      번호에 맞춰 넣으십시오. 표와 색은 어느 판본에서든 그대로 옵니다.
    </div>
  </aside>

  <main class="doc">{sections}</main>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
const FONT = {doc_font_js};

function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('on');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove('on'), 2100);
}}

/* 붙여넣는 쪽이 글꼴 정보를 못 받으면 한컴이 제 나름대로 고른다.
   겉을 글꼴 지정으로 한 번 감싸서 문서와 같은 결로 들어가게 한다. */
function wrap(inner) {{
  return '<div style="font-family:' + FONT + ';font-size:10.5pt;color:#17201B">'
       + inner + '</div>';
}}

async function copyHTML(node, label) {{
  const rich = wrap(node.innerHTML);
  const plain = node.innerText;
  try {{
    if (navigator.clipboard && window.ClipboardItem) {{
      await navigator.clipboard.write([new ClipboardItem({{
        'text/html':  new Blob([rich],  {{ type: 'text/html'  }}),
        'text/plain': new Blob([plain], {{ type: 'text/plain' }}),
      }})]);
      toast(label + ' 복사했습니다 — 한컴독스에서 Ctrl+V');
      return true;
    }}
  }} catch (e) {{ /* 아래 대체 방법으로 넘어간다 */ }}

  /* ClipboardItem을 못 쓰는 브라우저 — 눈에 안 보이는 곳에 붙여 두고 선택해 복사한다 */
  const holder = document.createElement('div');
  holder.style.cssText = 'position:fixed;left:-9999px;top:0;white-space:normal';
  holder.innerHTML = rich;
  document.body.appendChild(holder);
  const range = document.createRange();
  range.selectNodeContents(holder);
  const sel = getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  const ok = document.execCommand('copy');
  sel.removeAllRanges();
  holder.remove();
  toast(ok ? label + ' 복사했습니다 — 한컴독스에서 Ctrl+V'
           : '복사하지 못했습니다. 본문을 직접 끌어 선택해 주십시오.');
  return ok;
}}

document.querySelectorAll('[data-copy]').forEach((btn) => {{
  btn.addEventListener('click', async () => {{
    const sec = document.getElementById(btn.dataset.copy);
    const ok = await copyHTML(sec.querySelector('.body'), btn.dataset.label);
    if (ok) {{
      btn.textContent = '복사됨';
      setTimeout(() => {{ btn.textContent = '이 절 복사'; }}, 2100);
      const nav = document.querySelector('[data-nav="' + btn.dataset.copy + '"]');
      if (nav) {{ nav.classList.add('is-done'); nav.querySelector('.navitem__c').textContent = '완료'; }}
    }}
  }});
}});

document.querySelector('[data-copy-all]').addEventListener('click', async () => {{
  const all = document.createElement('div');
  document.querySelectorAll('.sec .body').forEach((b) => all.append(...b.cloneNode(true).childNodes));
  document.body.appendChild(all);
  all.style.cssText = 'position:fixed;left:-9999px;top:0';
  await copyHTML(all, '문서 전체를');
  all.remove();
}});
</script>
</body>
</html>
"""


def build() -> None:
    z = zipfile.ZipFile(SRC)
    rel_map = rels(z)
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    secs = split_sections(z, rel_map, body)
    secs.insert(0, {"id": "form", "num": "붙임1",
                    "title": "신청서 — 기획 개요 · 기획서 요약", "html": FORM_HTML})

    nav, blocks = [], []
    for s in secs:
        n_img = s["html"].count("<img")
        n_tbl = s["html"].count("<table")
        meta = " · ".join(filter(None, [
            f"표 {n_tbl}개" if n_tbl else "",
            f"그림 {n_img}장" if n_img else "",
        ])) or "본문"
        nav.append(
            f'<a class="navitem" data-nav="{s["id"]}" href="#{s["id"]}">'
            f'<span class="navitem__n">{html.escape(s["num"])}</span>'
            f'<span>{html.escape(s["title"])}</span>'
            f'<span class="navitem__c">—</span></a>')
        blocks.append(f"""
  <section class="sec" id="{s['id']}">
    <div class="sec__bar">
      <span class="sec__num">{html.escape(s['num'])}</span>
      <span class="sec__t">{html.escape(s['title'])}</span>
      <span class="sec__meta">{meta}</span>
      <span class="sec__act">
        <button class="btn btn--ghost" data-copy="{s['id']}"
                data-label="{html.escape(s['num'] + ' ' + s['title'])}을">이 절 복사</button>
      </span>
    </div>
    <div class="body tablescroll">{s['html']}</div>
  </section>""")

    page = PAGE.format(nav="".join(nav), sections="".join(blocks),
                       doc_font=DOC_FONT, doc_font_js=repr(DOC_FONT))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)

    # 웹에 올릴 판본 — 겉 뼈대(<html>/<head>/<body>)는 올리는 쪽이 씌워 주므로
    # 알맹이만 남깁니다. <style>과 <script>는 본문 안에 두어도 됩니다.
    inner = page[page.index("<style>"):page.index("</head>")] \
        + page[page.index("<body>") + len("<body>"):page.index("</body>")]
    with open(OUT_WEB, "w", encoding="utf-8") as f:
        f.write("<title>제출본 붙여넣기 — 임과 함께</title>\n" + inner)
    print(f"[saved] {OUT_WEB}")
    print(f"[saved] {OUT}  ({os.path.getsize(OUT)/1e6:.2f} MB)")
    for s in secs:
        print(f"  {s['num']:5s} {s['title'][:34]:36s} "
              f"표 {s['html'].count('<table')}개 · 그림 {s['html'].count('<img')}장")


if __name__ == "__main__":
    build()
