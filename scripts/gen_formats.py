"""知识库格式生成器：从 MD 生成 TXT + PDF"""
import re, fitz
from pathlib import Path

ROOT = Path("data/knowledge")

def clean_txt(md):
    out = []
    for line in md.split("\n"):
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        if line.startswith("# "): out.extend(["", "=" * 60, "  " + line[2:], "=" * 60])
        elif line.startswith("## "): out.extend(["", "--- " + line[3:] + " ---"])
        elif line.startswith("### "): out.extend(["", "  [" + line[4:] + "]"])
        elif re.match(r"^\|[\s\-:|]+\|$", line): continue
        elif line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            out.append("  " + "  |  ".join(cells))
        elif re.match(r"^[\-\s]+$", line): continue
        elif line.startswith("- ") or line.startswith("* "): out.append("  * " + line[2:])
        elif re.match(r"^\d+\.\s", line): out.append("  " + line)
        elif line.startswith("> "): out.append("  " + line[2:])
        elif line.strip(): out.append("  " + line)
        else: out.append("")
    return "\n".join(out)

def gen_pdf(md, path_str):
    doc = fitz.open()
    paras, cur = [], []
    for l in md.split("\n"):
        if not l.strip():
            if cur: paras.append(cur); cur = []
        else: cur.append(l)
    if cur: paras.append(cur)
    m, lh, ph = 50, 18, 842
    page = doc.new_page(); y = m
    for para in paras:
        fst = para[0]
        if fst.startswith("# "):
            y += lh * 2
            if y + lh * 2 > ph - m: page = doc.new_page(); y = m
            page.insert_text((m, y), fst[2:], fontname="china-s", fontsize=14); y += lh * 2
        elif fst.startswith("## "):
            y += lh
            if y + lh > ph - m: page = doc.new_page(); y = m
            page.insert_text((m, y), fst[3:], fontname="china-s", fontsize=12); y += lh * 1.5
        elif fst.startswith("### "):
            y += lh * 0.5
            if y + lh > ph - m: page = doc.new_page(); y = m
            page.insert_text((m, y), fst[4:], fontname="china-s", fontsize=11); y += lh * 1.2
        else:
            for l in para:
                if y + lh > ph - m: page = doc.new_page(); y = m
                if l.startswith("|"):
                    cells = [c.strip() for c in l.split("|") if c.strip()]
                    page.insert_text((m + 10, y), "  |  ".join(cells), fontname="china-ss", fontsize=8)
                elif l.startswith("- ") or l.startswith("* "):
                    page.insert_text((m + 10, y), "  * " + l[2:], fontname="china-ss", fontsize=10)
                elif re.match(r"^\d+\.\s", l):
                    page.insert_text((m + 10, y), l, fontname="china-ss", fontsize=10)
                elif l.strip():
                    page.insert_text((m, y), l, fontname="china-ss", fontsize=10)
                y += lh
            y += lh * 0.5
    doc.save(path_str)
    doc.close()

if __name__ == "__main__":
    for f in ROOT.rglob("*.md"):
        md = f.read_text(encoding="utf-8")
        tp = f.with_suffix(".txt"); tp.write_text(clean_txt(md), encoding="utf-8")
        pp = f.with_suffix(".pdf"); gen_pdf(md, str(pp))
    for ext in ["md", "txt", "pdf"]:
        n = len(list(ROOT.rglob(f"*.{ext}")))
        print(f"{n} {ext}")
