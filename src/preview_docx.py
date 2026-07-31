"""
docx 미리보기 — 만들어진 파일의 XML을 그대로 읽어 HTML로 옮깁니다.

이 컨테이너에는 워드도 리브레오피스도 없어 문서를 열어 볼 수 없습니다. 그렇다고
"의도한 대로 되었겠지" 하고 넘기면 색이 안 들어갔거나 표가 깨진 채로 제출됩니다.
그래서 document.xml에 실제로 들어간 값 — 칸 배경색, 테두리, 글자색, 굵기, 그림 —
을 읽어 화면으로 옮깁니다. 확인하는 대상이 의도가 아니라 파일 그 자체입니다.

한컴독스의 실제 렌더링과 완전히 같지는 않습니다. 색과 구조가 제대로 들어갔는지
보는 용도입니다.

실행: python src/preview_docx.py [문서.docx] [-o 출력.html]
"""
from __future__ import annotations

import argparse
import base64
import html
import os
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "docs", "제출본_임과함께_데이터분석부문.docx")

EMU_PER_CM = 360000


def rels(z: zipfile.ZipFile) -> dict:
    root = ET.fromstring(z.read("word/_rels/document.xml.rels"))
    ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    return {r.get("Id"): r.get("Target") for r in root.iter(ns + "Relationship")}


def img_tag(z, rel_map, rid, cx_emu) -> str:
    target = rel_map.get(rid)
    if not target:
        return ""
    path = "word/" + target.lstrip("/")
    try:
        blob = z.read(path)
    except KeyError:
        return f"<div class='miss'>그림 없음: {html.escape(path)}</div>"
    ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
    b64 = base64.b64encode(blob).decode()
    cm = (cx_emu or 0) / EMU_PER_CM
    style = f"width:{cm:.2f}cm" if cm else "max-width:100%"
    return (f"<img src='data:image/{ext};base64,{b64}' style='{style}' "
            f"data-kb='{len(blob)//1024}' />")


def run_html(z, rel_map, run) -> str:
    # 그림이 들어 있는 run
    for blip in run.iter(A + "blip"):
        ext = run.find(f".//{{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}}inline")
        cx = None
        for e in run.iter(A + "ext"):
            cx = int(e.get("cx", 0))
            break
        return img_tag(z, rel_map, blip.get(R + "embed"), cx)

    text = "".join(t.text or "" for t in run.iter(W + "t"))
    # 한 run이 글자와 줄바꿈을 함께 가질 수 있다. 줄바꿈만 있는 경우만 보면
    # "제공하는\n임업"이 "제공하는임업"으로 붙어 버린다.
    br = "<br/>" if run.find(W + "br") is not None else ""
    if not text:
        return br
    rPr = run.find(W + "rPr")
    css = []
    if rPr is not None:
        if rPr.find(W + "b") is not None:
            css.append("font-weight:700")
        c = rPr.find(W + "color")
        if c is not None and c.get(W + "val") not in (None, "auto"):
            css.append(f"color:#{c.get(W + 'val')}")
        sz = rPr.find(W + "sz")
        if sz is not None:
            css.append(f"font-size:{int(sz.get(W + 'val'))/2:.1f}pt")
    return f"<span style='{';'.join(css)}'>{html.escape(text)}</span>{br}"


def para_html(z, rel_map, p) -> str:
    body = "".join(run_html(z, rel_map, r) for r in p.findall(W + "r"))
    pPr = p.find(W + "pPr")
    css = []
    if pPr is not None:
        # 문단 간격을 읽지 않으면 스타일시트 기본값(5pt)이 그대로 붙는다.
        # 코드처럼 줄이 붙어 있어야 하는 곳에서 쪽수가 두 배로 불어난다.
        sp = pPr.find(W + "spacing")
        if sp is not None:
            for attr, prop in (("before", "margin-top"), ("after", "margin-bottom")):
                v = sp.get(W + attr)
                if v is not None:
                    css.append(f"{prop}:{int(v)/20:.1f}pt")
            line = sp.get(W + "line")
            rule = sp.get(W + "lineRule")
            if line is not None:
                css.append(f"line-height:{int(line)/240:.2f}"
                           if rule in (None, "auto") else f"line-height:{int(line)/20:.1f}pt")
        ind = pPr.find(W + "ind")
        if ind is not None and ind.get(W + "left"):
            css.append(f"margin-left:{int(ind.get(W + 'left'))/567:.2f}cm")
        shd = pPr.find(W + "shd")
        if shd is not None and shd.get(W + "fill") not in (None, "auto"):
            css.append(f"background:#{shd.get(W + 'fill')};"
                       f"padding:{'2px 6px' if sp is not None and sp.get(W + 'after') == '0' else '9px 13px'};"
                       "border-radius:4px")
        j = pPr.find(W + "jc")
        if j is not None:
            css.append(f"text-align:{ {'center':'center','right':'right','both':'justify'}.get(j.get(W + 'val'), 'left')}")
        bdr = pPr.find(W + "pBdr")
        if bdr is not None:
            for side in ("left", "bottom"):
                e = bdr.find(W + side)
                if e is not None and e.get(W + "val") != "nil":
                    px = max(1, int(e.get(W + "sz", "8")) // 8)
                    css.append(f"border-{side}:{px}px solid #{e.get(W + 'color', '888888')}")
    if not body.strip():
        return "<div class='sp'></div>"
    return f"<p style='{';'.join(css)}'>{body}</p>"


def table_html(z, rel_map, tbl) -> str:
    out = ["<table>"]
    for tr in tbl.findall(W + "tr"):
        out.append("<tr>")
        for tc in tr.findall(W + "tc"):
            pr = tc.find(W + "tcPr")
            css = []
            if pr is not None:
                shd = pr.find(W + "shd")
                if shd is not None and shd.get(W + "fill") not in (None, "auto"):
                    css.append(f"background:#{shd.get(W + 'fill')}")
                bd = pr.find(W + "tcBorders")
                if bd is None:
                    # tcBorders가 없으면 표 스타일(Table Grid)이 정한 테두리를 씁니다.
                    # 여기서 아무것도 안 그리면 워드에는 있는 선이 PDF에서만 사라집니다.
                    css.append("border:1px solid #9AA6AD")
                if bd is not None:
                    for side in ("top", "bottom", "left", "right"):
                        e = bd.find(W + side)
                        if e is None or e.get(W + "val") == "nil":
                            css.append(f"border-{side}:0")
                        else:
                            px = max(1, int(e.get(W + "sz", "8")) // 8)
                            css.append(f"border-{side}:{px}px solid #{e.get(W + 'color', '888888')}")
                tw = pr.find(W + "tcW")
                if tw is not None and tw.get(W + "w"):
                    css.append(f"width:{int(tw.get(W + 'w'))/567:.2f}cm")
            inner = "".join(para_html(z, rel_map, p) for p in tc.findall(W + "p"))
            out.append(f"<td style='{';'.join(css)}'>{inner}</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def build(src: str, dst: str) -> None:
    z = zipfile.ZipFile(src)
    rel_map = rels(z)
    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")

    parts, n_tbl, n_img = [], 0, 0
    for el in body:
        if el.tag == W + "p":
            parts.append(para_html(z, rel_map, el))
            n_img += len(list(el.iter(A + "blip")))
        elif el.tag == W + "tbl":
            n_tbl += 1
            parts.append(table_html(z, rel_map, el))

    css = """
    body { margin:0; background:#e9ecee; font-family:'Malgun Gothic','NanumGothic',sans-serif; }
    .page { width:21cm; min-height:29.7cm; margin:22px auto; padding:1.7cm 1.9cm 1.5cm;
            background:#fff; box-shadow:0 3px 18px rgba(0,0,0,.13); box-sizing:border-box; }
    p { margin:0; line-height:1.32; font-size:10.5pt; word-break:keep-all; }
    .sp { height:6pt; }
    table { border-collapse:collapse; width:100%; margin:4pt 0 8pt; table-layout:fixed; }
    td { padding:2.6pt 5pt; vertical-align:middle; overflow-wrap:break-word; }
    td p { margin:0; font-size:9.1pt; line-height:1.14; }
    img { display:block; margin:6pt auto 2pt; }
    .miss { color:#c00; font-size:9pt; }
    """
    out = (f"<!doctype html><meta charset='utf-8'><title>제출본 미리보기</title>"
           f"<style>{css}</style><div class='page'>" + "".join(parts) + "</div>")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"[saved] {dst}")
    print(f"  표 {n_tbl}개 · 그림 {n_img}개 · 문단 {len(parts)}개")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default=DEFAULT)
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "docs", "_preview.html"))
    a = ap.parse_args()
    build(a.src, a.out)


if __name__ == "__main__":
    main()
