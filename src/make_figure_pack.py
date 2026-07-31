"""
제출본 도표 모음 만들기 — docs/제출본_그림모음.zip

문서에는 그림이 이미 박혀 있습니다. 이 zip은 발표자료에 쓰거나 한컴에서 따로
배치할 때를 위한 것입니다. 파일 이름에 문서와 같은 번호를 붙여, 어느 그림이
본문 어디에 들어가는지 헷갈리지 않게 합니다.

번호는 make_docx.py의 FIGURE 호출에서 읽어 옵니다. 손으로 맞추면 문서를 고칠
때마다 어긋납니다.

실행: python src/make_figure_pack.py
"""
from __future__ import annotations

import os
import re
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, "docs", "figures")
OUTDIR = os.path.join(ROOT, "docs", "figures_번호순")
ZIP = os.path.join(ROOT, "docs", "제출본_그림모음.zip")

HEAD = """제출본 도표 모음 — 팀 임과 함께

제출본(.docx)에는 이 그림들이 이미 문서 안에 삽입되어 있습니다.
한컴독스에서 파일을 바로 열면 그림이 그대로 따라옵니다.
복사해 붙여넣는 대신 [파일] - [불러오기]로 .docx를 여십시오.

아래는 그림을 따로 배치하거나 발표자료에 쓰실 경우를 위한 원본입니다.
모두 200dpi라 인쇄해도 깨지지 않습니다.

--------------------------------------------------------

"""


def safe(t: str) -> str:
    """파일 이름에 못 쓰는 글자를 걷어냅니다."""
    return re.sub(r'[\\/:*?"<>|]', "", t.replace("—", "-")).strip()[:52]


def main() -> None:
    src = open(os.path.join(ROOT, "src", "make_docx.py"), encoding="utf-8").read()
    figs = re.findall(
        r'FIGURE\(doc, "([^"]+)\.png",\s*\n?\s*"\[그림 (\d+)\] ([^"]+)"', src)
    if not figs:
        raise SystemExit("make_docx.py에서 FIGURE 호출을 못 찾았습니다.")

    os.makedirs(OUTDIR, exist_ok=True)
    for f in os.listdir(OUTDIR):
        os.remove(os.path.join(OUTDIR, f))

    lines = []
    for name, num, cap in figs:
        dst = os.path.join(OUTDIR, f"그림{int(num):02d}_{safe(cap)}.png")
        shutil.copy2(os.path.join(FIG, f"{name}.png"), dst)
        lines.append(f"그림 {num} — {cap}\n    파일: {os.path.basename(dst)}")
        print(f"  그림 {num:>2s}  {cap[:46]}")

    with open(os.path.join(OUTDIR, "00_읽어보기.txt"), "w", encoding="utf-8") as f:
        f.write(HEAD + "\n".join(lines) + "\n")

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(OUTDIR)):
            z.write(os.path.join(OUTDIR, f), f)
    print(f"\n[saved] {ZIP}  ({os.path.getsize(ZIP)/1e6:.2f} MB · {len(figs)}장)")


if __name__ == "__main__":
    main()
