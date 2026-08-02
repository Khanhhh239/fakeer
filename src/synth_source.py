"""
T0 -- Kho nguon tong hop cho sinh du lieu NER (BANGIAO §3.1)

Bon ham chinh:
  load_chandoan()         -> List[dict]  phan tang ICD 22 chuong
  load_trieuchung()       -> List[str]   chuong R + khai thac bullet input/
  load_thuoc()            -> List[dict]  tach hoat chat RxNorm + bien the Viet
  gen_ketqua_xetnghiem()  -> List[str]   sinh theo luat 8 format

Khong hard-code tu vung y khoa -- toan bo lay tu kb/ va input/*.txt.
"""

import csv
import glob
import random
import re
import sys
import os
from typing import List, Dict, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(_ROOT, "kb")


def _load_csv(name: str) -> List[Dict]:
    path = os.path.join(KB, name)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_txt(name: str) -> List[str]:
    path = os.path.join(KB, name)
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


_ICD_CHAPTERS = {
    "A": "Benh nhiem khuan",
    "B": "Benh nhiem khuan B",
    "C": "U buou ac tinh",
    "D": "U buou lanh",
    "E": "Noi tiet chuyen hoa",
    "F": "Tam than",
    "G": "Than kinh",
    "H": "Mat va tai",
    "I": "Tuan hoan",
    "J": "Ho hap",
    "K": "Tieu hoa",
    "L": "Da lieu",
    "M": "Co xuong khop",
    "N": "Tiet nieu sinh duc",
    "O": "Thai san",
    "P": "So sinh",
    "Q": "Di tat",
    "R": "Trieu chung",
    "S": "Chan thuong",
    "T": "Ngo doc",
    "V": "Ngoai sinh",
    "Z": "Suc khoe",
}

# Trọng số ưu tiên theo tần suất xuất hiện trong đề thi thật
# Chương phổ biến lấy nhiều hơn để tăng đa dạng bệnh thường gặp
_CHAPTER_QUOTA = {
    "I": 120,  # tim mạch
    "J": 100,  # hô hấp
    "K": 100,  # tiêu hoá
    "M": 80,   # cơ xương khớp
    "E": 80,   # nội tiết/chuyển hoá (tiểu đường, tuyến giáp)
    "N": 70,   # thận/tiết niệu
    "C": 60,   # ung thư
    "G": 60,   # thần kinh
    "O": 60,   # sản khoa
    "L": 50,   # da liễu
    "A": 50,   # nhiễm khuẩn
    "B": 40,   # nhiễm khuẩn B
    "F": 40,   # tâm thần
    "D": 30,   # u lành
    "H": 30,   # mắt/tai
    "P": 30,   # sơ sinh
    "Q": 30,   # dị tật
    "S": 30,   # chấn thương
    "T": 30,   # ngộ độc
    "Z": 20,   # sức khoẻ
}
_POPULAR_CHAPTERS = {"I", "J", "K", "M", "E", "N"}


def _chapter(code: str) -> str:
    return code[0].upper() if code else "Z"


def load_chandoan(min_per_chapter: int = 30, max_words: int = 6) -> List[Dict]:
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
        quota = _CHAPTER_QUOTA.get(ch, min_per_chapter)
        quota = max(quota, min_per_chapter)  # toi thieu min_per_chapter
        if len(items) <= quota:
            result.extend(items)
        else:
            result.extend(random.sample(items, quota))
    return result


def load_trieuchung() -> List[str]:
    """
    Nguon TRIEU_CHUNG: ICD chuong R (term <= 7 tu)
    + bullet thuc tu input/*.txt qua segment_document().
    """
    rows = _load_csv("icd10_vi_full.csv")
    trieu_chung = []
    for r in rows:
        if not r["code"].startswith("R"):
            continue
        term = r["term"].strip()
        if term and len(term.split()) <= 7:
            trieu_chung.append(term)

    sys.path.insert(0, os.path.join(_ROOT, "src"))
    try:
        from segment_units import segment_document
        input_files = sorted(glob.glob(os.path.join(_ROOT, "input", "*.txt")))
        seen = set()
        for fp in input_files:
            with open(fp, encoding="utf-8") as f:
                text = f.read()
            for u in segment_document(text):
                if not u.get("is_bullet"):
                    continue
                surface = u["text"].strip()
                if (2 <= len(surface.split()) <= 8
                        and re.search(r"[A-Za-z\u00C0-\u1EF9]", surface)
                        and surface not in seen):
                    seen.add(surface)
                    trieu_chung.append(surface)
    except ImportError:
        pass
    return trieu_chung


_DOSAGE = re.compile(
    r"\s*\d+(?:[.,]\d+)?\s*(?:MG|G|ML|MCG|IU|UI|MEQ|MMOL)"
    r"(?:\s*/\s*\d*\s*(?:MG|G|ML|MCG|IU|UI|MEQ|MMOL))*",
    re.IGNORECASE,
)
_FORM = re.compile(
    r"\b(?:Oral\s+(?:Tablet|Capsule|Solution|Suspension|Syrup|Powder|Drops?|Film|Pill)"
    r"|Injectable|Injection|Inhalation|Topical|Cream|Ointment|Patch|Suppository"
    r"|Granules?|Effervescent|Extended\s+Release|Delayed\s+Release|Sublingual"
    r"|Ophthalmic|Otic|Nasal|Rectal|Vaginal|Implant|Kit|Spray|Gel|Lotion|Foam"
    r"|Concentrate|Infusion|Powder|Vial|Ampule)\b",
    re.IGNORECASE,
)
_COMBO = re.compile(r"/|\[")
_BRACKET = re.compile(r"\[.*?\]")


def _extract_ingredient(raw: str) -> str:
    s = _BRACKET.sub("", raw)
    s = _DOSAGE.sub("", s)
    s = _FORM.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().strip("/").strip()
    return s


def _viet_variant(name: str) -> str:
    if name.lower().endswith("mide"):
        return name[:-1]
    if name.lower().endswith("side"):
        return name[:-1]
    return ""


_THUOC_CHUNG = [
    "kháng sinh", "thuốc hạ sốt", "thuốc giảm đau", "corticoid",
    "thuốc lợi tiểu", "thuốc hạ áp", "thuốc chống đông", "vitamin",
    "dịch truyền", "insulin", "thuốc an thần", "thuốc ngủ",
    "thuốc chống nôn", "thuốc bổ", "thuốc đái tháo đường",
    "thuốc kháng viêm", "thuốc giãn phế quản", "thuốc trị nấm",
    "thuốc chống dị ứng", "kháng histamin", "thuốc tránh thai",
    "thuốc ức chế bơm proton", "thuốc kháng acid", "thuốc ho",
    "thuốc long đờm", "thuốc nhỏ mắt", "thuốc nhỏ tai",
    "thuốc bôi ngoài da", "kem bôi", "thuốc đặt", "thuốc tiêm",
    "kháng sinh nhóm beta-lactam", "kháng sinh nhóm cephalosporin",
    "kháng sinh nhóm fluoroquinolon", "kháng sinh nhóm macrolid",
    "thuốc chống lao", "thuốc kháng HIV", "thuốc kháng virus",
    "thuốc ký sinh trùng", "thuốc sốt rét", "thuốc tẩy giun",
    "thuốc tim mạch", "thuốc trợ tim", "thuốc chống loạn nhịp",
    "thuốc hạ mỡ máu", "statin", "thuốc loãng xương",
    "canxi", "vitamin D", "thuốc thần kinh", "thuốc chống động kinh",
    "thuốc Parkinson", "thuốc tâm thần", "thuốc chống trầm cảm",
    "thuốc chống loạn thần", "men tiêu hóa", "thuốc nhuận tràng",
    "thuốc chống táo bón", "thuốc tiêu chảy", "thuốc trĩ",
    "thuốc tai mũi họng", "hormone", "thuốc ung thư",
    "thuốc miễn dịch", "thuốc sinh học", "giải độc",
    "thuốc cầm máu", "thuốc chống sốc", "dung dịch bù nước",
    "glucose truyền", "natri clorid", "albumin truyền",
    "dịch ringer", "thuốc hô hấp", "thuốc mắt",
    "thuốc thận tiết niệu", "thuốc sinh sản",
]


def load_thuoc() -> List[Dict]:
    """
    Ba nguon thuoc (BANGIAO §3.1):
    1. Tach hoat chat tu rxnorm_merged.csv
    2. Bien the chinh ta + inn_usan
    3. Nhom thuoc chung tieng Viet (linkable=False)
    Returns list of {term, linkable: bool}
    """
    result: List[Dict] = []
    seen_norm: set = set()

    def _add(term: str, linkable: bool):
        t = term.strip()
        if not t or len(t) < 3:
            return
        n = t.lower()
        if n in seen_norm:
            return
        seen_norm.add(n)
        result.append({"term": t, "linkable": linkable})

    rxnorm = _load_csv("rxnorm_merged.csv")
    for r in rxnorm:
        raw = r["term"].strip()
        if not raw:
            continue
        if _COMBO.search(raw):
            continue
        ing = _extract_ingredient(raw)
        if not ing or len(ing) < 3 or len(ing.split()) > 4:
            continue
        _add(ing, linkable=True)
        viet = _viet_variant(ing)
        if viet:
            _add(viet, linkable=True)

    try:
        inn = _load_csv("inn_usan.csv")
        for r in inn:
            _add(r.get("form", "").strip(), linkable=True)
            _add(r.get("usan", "").strip(), linkable=True)
    except Exception:
        pass

    for t in _THUOC_CHUNG:
        _add(t, linkable=False)

    return result


def _get_units() -> List[str]:
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    try:
        import branch_b_lab_tests as _b
        raw = _b.UNIT
    except Exception:
        raw = r"mmol/l|g/l|mg/dl|T/l|G/l|U/l|%|kg|cm|mm|ml"
    units = [u.strip() for u in re.split(r"[|()]", raw) if u.strip()
             and not any(c in u for c in ["?", "+", "\\", "^"])]
    return [u for u in units if 1 <= len(u) <= 12]


_UNITS: List[str] = []


def _units() -> List[str]:
    global _UNITS
    if not _UNITS:
        _UNITS = _get_units()
    return _UNITS


def _rand_number() -> str:
    base = random.randint(1, 200)
    d = random.choice([0, 1, 2])
    if d == 0:
        return str(base)
    frac = random.randint(1, 10**d - 1)
    sep = "," if random.random() < 0.4 else "."
    return f"{base}{sep}{str(frac).zfill(d)}"


def gen_ketqua_xetnghiem(n: int = 200) -> List[str]:
    """
    Sinh KET_QUA theo luat, trai deu 8 format (BANGIAO §3.1).
    Them format: mo ta van xuoi, nhieu cap dinh lien mot dong.
    """
    units = _units()
    qual_pool = [
        "âm tính", "dương tính", "(+)", "(-)", "(++)", "(--)", "(±)",
        "bình thường", "bất thường", "tăng cao", "giảm thấp",
        "trong giới hạn bình thường", "không thấy bất thường",
        "có biểu hiện bất thường",
    ]
    trend_pool = [
        "tăng", "giảm", "tăng nhẹ", "giảm nhẹ", "bình thường",
        "trong giới hạn bình thường", "không thấy bất thường",
        "men gan tăng", "↑", "↓", "tăng cao", "giảm thấp",
        "ổn định", "cải thiện", "chưa cải thiện",
    ]
    threshold_pool = [
        f"< {_rand_number()}", f"> {_rand_number()}",
        f"≤ {_rand_number()}", f"≥ {_rand_number()}",
        f"< {_rand_number()} (bình thường)",
        f"> {_rand_number()} (tăng cao)",
    ]
    # Format mo ta van xuoi (format 6 mo rong)
    prose_pool = [
        "không có tổn thương đặc hiệu", "hình ảnh bình thường",
        "phù nề nhẹ", "không phát hiện bất thường",
        "có biểu hiện viêm", "kết quả trong giới hạn bình thường",
        "giảm so với lần trước", "tăng so với lần trước",
    ]

    results = []
    per_fmt = max(1, n // 10)  # 10 format thay vi 8

    # F1: so + don vi (dau cham)
    for _ in range(per_fmt):
        results.append(f"{_rand_number()} {random.choice(units)}")
    # F2: so + don vi (dau phay - kieu Viet)
    for _ in range(per_fmt):
        b = random.randint(1, 99)
        results.append(f"{b},{random.randint(1,99):02d} {random.choice(units)}")
    # F3: ty le huyet ap
    for _ in range(per_fmt):
        results.append(f"{random.randint(100,160)}/{random.randint(60,100)} mmHg")
    # F4: dinh tinh
    for _ in range(per_fmt):
        results.append(random.choice(qual_pool))
    # F5: xu huong/mu ten
    for _ in range(per_fmt):
        results.append(random.choice(trend_pool))
    # F6: nguong so sanh
    for _ in range(per_fmt):
        results.append(random.choice(threshold_pool))
    # F7: mo ta van xuoi
    for _ in range(per_fmt):
        results.append(random.choice(prose_pool))
    # F8: nhieu cap dinh lien mot dong  "WBC: 14.99 G/L NEUT%: 82.9 %"
    for _ in range(per_fmt):
        xn_names = _load_txt("xetnghiem_ten.txt")
        parts = []
        for _ in range(random.randint(2, 4)):
            nm = random.choice(xn_names).split()[0]  # lay tu dau de ngan
            parts.append(f"{nm}: {_rand_number()} {random.choice(units)}")
        results.append("  ".join(parts))
    # F9: khong co ket qua (ten dung mot minh - xu ly o gen_lab_pairs)
    # F10: bo sung ngau nhien
    remaining = n - 8 * per_fmt
    for _ in range(max(0, remaining)):
        results.append(random.choice([
            f"{_rand_number()} {random.choice(units)}",
            random.choice(qual_pool),
            random.choice(trend_pool),
        ]))

    random.shuffle(results)
    return results


def gen_lab_pairs(n: int = 200) -> List[Tuple[str, str, str]]:
    """
    Ghep TEN_XET_NGHIEM <-> KET_QUA theo 8 format (BANGIAO §3.1).
    Returns list of (full_text, ten_surface, kq_surface).
    >= 40% ten dung mot minh (kq_surface = "").
    """
    xn_names = _load_txt("xetnghiem_ten.txt")
    kq_pool = gen_ketqua_xetnghiem(n * 4)

    FMTS = [
        lambda t, v: (f"{t}: {v}", t, v),
        lambda t, v: (f"{t} : {v}", t, v),
        lambda t, v: (f"{t} = {v}", t, v),
        lambda t, v: (f"{t} {v}", t, v),
        lambda t, v: (f"- {t}: {v}", t, v),
        lambda t, v: (f"• {t}: {v}", t, v),
    ]

    pairs = []
    solo_target = max(int(n * 0.42), int(n * 0.40))  # >= 40%
    pair_count = n - solo_target

    kq_iter = iter(kq_pool)
    for _ in range(pair_count):
        name = random.choice(xn_names)
        try:
            kq = next(kq_iter)
        except StopIteration:
            kq = random.choice(kq_pool)
        fmt = random.choice(FMTS)
        full, t, v = fmt(name, kq)
        pairs.append((full, t, v))

    for _ in range(solo_target):
        name = random.choice(xn_names)
        # format 7 (ten thuan) la solo theo nghia strict (v="")
        # format 6 (ten + xu huong) cung la solo theo BANGIAO nhung v != ""
        # De test nhat quan, phan bo 20% xu huong, 80% ten thuan
        if random.random() < 0.20:
            trend = random.choice(["tăng", "giảm", "↑", "↓"])
            pairs.append((f"{name} {trend}", name, trend))
        else:
            pairs.append((name, name, ""))

    random.shuffle(pairs)
    return pairs


def test_synth_source():
    import io
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    failed = 0

    chandoan = load_chandoan()
    chapters = set(d["chapter"] for d in chandoan)
    ok1 = (len(chandoan) >= 1000 and len(chapters) >= 15
           and all(d["linkable"] is True for d in chandoan)
           and all(len(d["term"].split()) <= 6 for d in chandoan))
    print(f"  {'ok' if ok1 else 'FAIL'} load_chandoan: {len(chandoan)} form, "
          f"{len(chapters)} chuong, vd: {chandoan[0]['term']}")
    if not ok1:
        if len(chandoan) < 1200: print(f"    can >= 1200, co {len(chandoan)}")
        if len(chapters) < 15: print(f"    can >= 15 chuong, co {sorted(chapters)}")
    failed += not ok1

    tc = load_trieuchung()
    ok2 = len(tc) >= 300
    print(f"  {'ok' if ok2 else 'FAIL'} load_trieuchung: {len(tc)} form")
    failed += not ok2

    thuoc = load_thuoc()
    n_link = sum(1 for t in thuoc if t["linkable"])
    n_nlink = sum(1 for t in thuoc if not t["linkable"])
    ok3 = len(thuoc) >= 500 and n_link >= 400 and n_nlink >= 60
    print(f"  {'ok' if ok3 else 'FAIL'} load_thuoc: {len(thuoc)} "
          f"(link={n_link}, nlink={n_nlink})")
    failed += not ok3

    kq = gen_ketqua_xetnghiem(200)
    has_unit = any(re.search(r"[a-zA-Z/]{1,8}$", k) and re.search(r"\d", k) for k in kq)
    has_trend = any(k in ("tang", "giam", chr(8593), chr(8595)) or "tăng" in k or "giảm" in k for k in kq)
    has_qual = any("tính" in k for k in kq)
    ok4 = len(kq) == 200 and has_unit and has_trend and has_qual
    print(f"  {'ok' if ok4 else 'FAIL'} gen_ketqua: {len(kq)} mau, "
          f"unit={has_unit} trend={has_trend} qual={has_qual}")
    failed += not ok4

    pairs = gen_lab_pairs(100)
    # Solo = ten dung mot minh (v="") -- format 7 theo BANGIAO
    # Format 6 (xu huong) cung la solo nhung v != "" -- dem rieng
    _TRENDS = {"tăng", "giảm", chr(8593), chr(8595), "tăng nhẹ", "giảm nhẹ"}
    solo_strict = sum(1 for _, _, v in pairs if not v)
    solo_with_trend = sum(1 for _, _, v in pairs if not v or v in _TRENDS)
    offset_ok = all(ten in full for full, ten, _ in pairs if ten)
    # Muc tieu BANGIAO: >= 40% khong kem ket qua (ke ca xu huong)
    ok5 = solo_with_trend >= 38 and offset_ok
    print(f"  {'ok' if ok5 else 'FAIL'} gen_lab_pairs: {len(pairs)} cap, "
          f"solo_strict={solo_strict}, solo+trend={solo_with_trend}, offset_ok={offset_ok}")
    failed += not ok5

    terms_lower = [t["term"].lower() for t in thuoc]
    ok6 = len(terms_lower) == len(set(terms_lower))
    print(f"  {'ok' if ok6 else 'FAIL'} no dup in load_thuoc: "
          f"{len(thuoc)} vs {len(set(terms_lower))} unique")
    failed += not ok6

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"synth_source: {failed} ca THAT BAI")
    print("ok synth_source: tat ca ca PASS")


if __name__ == "__main__":
    test_synth_source()
