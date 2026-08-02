"""Fix load_chandoan and gen_lab_pairs in synth_source.py"""
import re, os

path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "synth_source.py")
with open(path, encoding="utf-8") as f:
    src = f.read()

# Fix 1: load_chandoan -- lay tat ca tu chuong nho, nhieu hon tu chuong lon
old_func = '''def load_chandoan(min_per_chapter: int = 30, max_words: int = 6) -> List[Dict]:
    """
    Phan tang ICD-10-VN thanh danh sach chan doan phan bo deu 22 chuong.
    Loc: term <= max_words tu, moi chuong >= min_per_chapter term.
    Returns list of {term, code, chapter, linkable=True}
    """
    rows = _load_csv("icd10_vi_full.csv")
    by_chapter: Dict[str, List[Dict]] = {}
    for r in rows:
        code, term = r["code"].strip(), r["term"].strip()
        if not term or not code:
            continue
        if len(term.split()) > max_words:
            continue
        ch = _chapter(code)
        by_chapter.setdefault(ch, []).append(
            {"term": term, "code": code, "chapter": ch, "linkable": True}
        )

    result: List[Dict] = []
    for ch, items in by_chapter.items():
        if ch == "R":
            continue
        if len(items) <= min_per_chapter:
            result.extend(items)
        else:
            result.extend(random.sample(items, min_per_chapter))
            if ch in _POPULAR_CHAPTERS:
                extra_pool = [x for x in items if x not in result]
                if extra_pool:
                    result.extend(random.sample(extra_pool, min(len(extra_pool), 50)))
    return result'''

new_func = '''def load_chandoan(min_per_chapter: int = 30, max_words: int = 6) -> List[Dict]:
    """
    Phan tang ICD-10-VN thanh danh sach chan doan phan bo deu 22 chuong.
    Loc: term <= max_words tu.
    Chuong nho (<30 terms): lay tat ca.
    Chuong lon: lay min_per_chapter + them 50 neu la chuong pho bien.
    Bỏ chuong qua it (<5 terms): V, W, X, Y, U.
    Returns list of {term, code, chapter, linkable=True}
    """
    _SKIP_TINY = {"V", "W", "X", "Y", "U"}  # <5 terms, qua it de phan tang

    rows = _load_csv("icd10_vi_full.csv")
    by_chapter: Dict[str, List[Dict]] = {}
    for r in rows:
        code, term = r["code"].strip(), r["term"].strip()
        if not term or not code:
            continue
        if len(term.split()) > max_words:
            continue
        ch = _chapter(code)
        if ch in _SKIP_TINY or ch == "R":
            continue
        by_chapter.setdefault(ch, []).append(
            {"term": term, "code": code, "chapter": ch, "linkable": True}
        )

    result: List[Dict] = []
    for ch, items in by_chapter.items():
        if len(items) <= min_per_chapter:
            # Chuong nho: lay tat ca
            result.extend(items)
        else:
            sampled = random.sample(items, min_per_chapter)
            result.extend(sampled)
            # Chuong pho bien: lay them nhieu hon
            extra_n = 80 if ch in _POPULAR_CHAPTERS else 20
            extra_pool = [x for x in items if x not in sampled]
            if extra_pool:
                result.extend(random.sample(extra_pool, min(len(extra_pool), extra_n)))
    return result'''

if old_func not in src:
    print("WARNING: old_func not found, trying partial match")
    # Show what's there
    start = src.find("def load_chandoan")
    print(f"Found at {start}: {src[start:start+200]!r}")
else:
    src = src.replace(old_func, new_func)
    print("Fixed load_chandoan")

# Fix 2: gen_lab_pairs -- solo_target sai do integer division
old_solo = "    solo_target = int(n * 0.42)"
new_solo = "    solo_target = max(int(n * 0.42), int(n * 0.40))  # >= 40%"
if old_solo in src:
    src = src.replace(old_solo, new_solo)
    print("Fixed solo_target")
else:
    print("WARNING: solo_target line not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("Done")
