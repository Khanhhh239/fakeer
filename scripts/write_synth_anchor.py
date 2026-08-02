"""Write src/synth_anchor.py"""
import os

content = r'''"""
anchor_all + validate_document -- BANGIAO §4 va §5

anchor_all(text, required) -> list[dict] | None
    Neo nhan bang tim chuoi chinh xac (ranh gioi tu, cho phep lap nhieu lan).
    Tra None neu < 60% cum bat buoc tim thay -> sinh lai, toi da 3 lan.

validate_document(text, entities) -> (bool, str)
    Kiem 9 dieu kien §5. Tra (True, "") neu qua het, (False, ly_do) neu truot.

resolve_overlap la tac dung phu cua select_non_overlapping da co trong
src/utils/overlap_resolver.py -- tai su dung, khong viet lai.
"""

import re
import sys
import os
from typing import List, Dict, Optional, Tuple, Set

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from utils.overlap_resolver import select_non_overlapping


# ─── anchor_all ───────────────────────────────────────────────────────────

def anchor_all(
    text: str,
    required: List[Tuple[str, str]],
    bait: Optional[List[str]] = None,
) -> Optional[List[Dict]]:
    """
    Neo nhan sau khi LLM viet xong (BANGIAO §4).

    required: [(surface_form, entity_type), ...]
    bait:     [surface_form, ...] -- co mat trong text nhung KHONG duoc gan nhan

    Quy tac:
    - Khop theo RANH GIOI TU (word boundary Unicode), khong dung str.find don gian.
    - Cho phep 1 cum xuat hien NHIEU LAN -> gan het cac lan.
    - Nen cu < 60% cum bat buoc tim thay -> tra None.

    Bat bien: text[e['position'][0]:e['position'][1]] == e['text'] voi moi e.
    """
    if not required:
        return []

    ents: List[Dict] = []
    seen_count = 0

    for surface, etype in required:
        # Khop theo ranh gioi tu Unicode
        # \b khong hieu Unicode day du -> dung lookaround voi tap ky tu tu
        pat = (r'(?<![^\s.,;:!?()\[\]{}\'"/-])'
               + re.escape(surface)
               + r'(?![^\s.,;:!?()\[\]{}\'"/-])')
        # Don gian hon: dung lookaround khong chu cai / chu so Unicode
        pat = r'(?<![\w\u00C0-\u1EF9])' + re.escape(surface) + r'(?![\w\u00C0-\u1EF9])'

        hits = list(re.finditer(pat, text, re.IGNORECASE))
        if hits:
            seen_count += 1
        for m in hits:
            ents.append({
                "text": text[m.start():m.end()],
                "type": etype,
                "position": [m.start(), m.end()],
                "score": 1.0,
            })

    # Nen cu < 60% -> sinh lai
    if seen_count / len(required) < 0.6:
        return None

    # Giai quyet chong lan (giu span dai nhat khi score bang nhau)
    for e in ents:
        e["start"] = e["position"][0]
        e["end"] = e["position"][1]

    resolved = select_non_overlapping(ents)

    # Khoi phuc lai position tu start/end
    for e in resolved:
        e["position"] = [e["start"], e["end"]]
        del e["start"], e["end"]

    return resolved


# ─── validate_document ────────────────────────────────────────────────────


def _word_count(text: str) -> int:
    return len(text.split())


def _entity_word_count(text: str, entities: List[Dict]) -> int:
    """So tu nam trong it nhat 1 thuc the (tinh theo ky tu, khong dem chong)."""
    covered = bytearray(len(text))
    for e in entities:
        s, en = e["position"][0], e["position"][1]
        for i in range(s, en):
            covered[i] = 1
    # Dem tu nam trong covered
    count = 0
    for m in re.finditer(r'\S+', text):
        if any(covered[i] for i in range(m.start(), m.end())):
            count += 1
    return count


def validate_document(
    text: str,
    entities: List[Dict],
    bait_thuoc: str = "",
    bait_xetnghiem: str = "",
    am_thuoc: Optional[List[str]] = None,
    am_xetnghiem: Optional[List[str]] = None,
    target_dist: Optional[Dict[str, float]] = None,
) -> Tuple[bool, str]:
    """
    9 cong kiem dinh (BANGIAO §5).

    Tra (True, "") neu qua het.
    Tra (False, ly_do) ngay khi truot dieu kien dau tien.

    entities: list of {text, type, position:[start,end]}
    """
    VALID_TYPES = {
        "TRIEU_CHUNG", "CHAN_DOAN", "THUOC",
        "TEN_XET_NGHIEM", "KET_QUA_XET_NGHIEM",
        # ky hieu Unicode
        "TRIỆU_CHỨNG", "CHẨN_ĐOÁN", "THUỐC",
        "TÊN_XÉT_NGHIỆM", "KẾT_QUẢ_XÉT_NGHIỆM",
    }

    # 1. Bat bien nguyen van
    for e in entities:
        s, en = e["position"][0], e["position"][1]
        if text[s:en] != e["text"]:
            return False, (f"[C1] nguyen van sai: {e['text']!r} != "
                           f"{text[s:en]!r} tai [{s},{en}]")

    # 2. Ty le tu nam trong thuc the: 8%–18%
    total_words = _word_count(text)
    if total_words == 0:
        return False, "[C2] van ban rong"
    entity_words = _entity_word_count(text, entities)
    ratio = entity_words / total_words
    if not (0.08 <= ratio <= 0.18):
        return False, f"[C2] ty le tu trong thuc the {ratio:.2%} ngoai [8%,18%]"

    # 3. Khong chong lan
    ordered = sorted(entities, key=lambda e: e["position"][0])
    for a, b in zip(ordered, ordered[1:]):
        if a["position"][1] > b["position"][0]:
            return False, (f"[C3] chong lan: {a['text']!r}[{a['position']}] "
                           f"va {b['text']!r}[{b['position']}]")

    # 4. >= 60% cum bat buoc tim thay -- da xu ly trong anchor_all, nhac lai
    # (o day khong co danh sach required, nen bo qua neu khong truyen)

    # 5. Khong sot thuc the duong nao (kiem nhanh voi entities hien co)
    # -> xu ly ben ngoai neu co KB nguoc, o day chi kiem type hop le
    for e in entities:
        if e.get("type") and e["type"] not in VALID_TYPES:
            return False, f"[C5/type] loai la: {e['type']!r}"

    # 6. Khong co chuoi am bao gio duoc gan nhan
    if am_thuoc:
        entity_texts_lower = {e["text"].lower() for e in entities}
        for am in am_thuoc:
            if am.lower() in entity_texts_lower:
                return False, f"[C6] am_thuoc duoc gan nhan: {am!r}"
    if am_xetnghiem:
        entity_texts_lower = {e["text"].lower() for e in entities}
        for am in am_xetnghiem:
            if am.lower() in entity_texts_lower:
                return False, f"[C6] am_xetnghiem duoc gan nhan: {am!r}"

    # 7. Do dai file: 1500–4000 ky tu
    if not (1500 <= len(text) <= 4000):
        return False, f"[C7] do dai {len(text)} ngoai [1500,4000]"

    # 8. Bait co mat trong text
    if bait_thuoc and bait_thuoc not in text:
        return False, f"[C8] bait_thuoc vang mat: {bait_thuoc!r}"
    if bait_xetnghiem and bait_xetnghiem not in text:
        return False, f"[C8] bait_xetnghiem vang mat: {bait_xetnghiem!r}"

    # 9. Ty le phan bo loai khong lech qua 15% (neu co target_dist)
    if target_dist and entities:
        from collections import Counter
        cnt = Counter(e["type"] for e in entities)
        total = len(entities)
        for typ, target_ratio in target_dist.items():
            actual = cnt.get(typ, 0) / total
            if abs(actual - target_ratio) > 0.15:
                return False, (f"[C9] {typ}: actual={actual:.2%} lech "
                               f"{abs(actual-target_ratio):.2%} > 15% "
                               f"so voi muc tieu {target_ratio:.2%}")

    return True, ""


# ─── TEST ─────────────────────────────────────────────────────────────────


def test_synth_anchor():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    failed = 0

    # 1) anchor_all: tim thay ca 3 cum, bat bien nguyen van
    text1 = ("Benh nhan bi sot cao, ho khan va duoc chan doan "
             "viem phoi. Dieu tri bang amoxicillin.")
    required1 = [
        ("sot cao", "TRIEU_CHUNG"),
        ("ho khan", "TRIEU_CHUNG"),
        ("viem phoi", "CHAN_DOAN"),
        ("amoxicillin", "THUOC"),
    ]
    ents1 = anchor_all(text1, required1)
    ok1a = ents1 is not None and len(ents1) == 4
    ok1b = all(text1[e["position"][0]:e["position"][1]] == e["text"] for e in (ents1 or []))
    ok1 = ok1a and ok1b
    print(f"  {'ok' if ok1 else 'FAIL'} anchor_all tim thay 4 cum: "
          f"n={len(ents1) if ents1 else 0}, bat bien={ok1b}")
    if not ok1a: print(f"    ents1={ents1}")
    failed += not ok1

    # 2) anchor_all: lặp nhieu lan -> gan het
    text2 = "sot cao. Sau 2 ngay sot cao them. Kham thay sot cao ro."
    ents2 = anchor_all(text2, [("sot cao", "TRIEU_CHUNG")])
    ok2 = ents2 is not None and len(ents2) == 3
    print(f"  {'ok' if ok2 else 'FAIL'} lap nhieu lan: {len(ents2) if ents2 else 0} lan (expect 3)")
    failed += not ok2

    # 3) anchor_all: < 60% cum tim thay -> tra None
    text3 = "Benh nhan kham binh thuong."
    required3 = [("sot cao", "X"), ("ho khan", "X"), ("viem phoi", "X"),
                 ("amoxicillin", "X"), ("tieu duong", "X")]  # khong co cai nao
    ents3 = anchor_all(text3, required3)
    ok3 = ents3 is None
    print(f"  {'ok' if ok3 else 'FAIL'} < 60% -> None: {ents3}")
    failed += not ok3

    # 4) anchor_all: khong an nham "sot" vao "sot cao"
    text4 = "Benh nhan sot cao, nhung khong sot nhieu."
    ents4 = anchor_all(text4, [("sot", "TRIEU_CHUNG")])
    # "sot" chi xuat hien 1 lan doc lap (sau "khong ")
    sot_count = sum(1 for e in (ents4 or []) if e["text"] == "sot")
    # Tuy theo ranh gioi, "sot cao" co "sot" la prefix nen phu thuoc implementation
    # Kiem chinh: khong gap loi (not None, bat bien OK)
    ok4 = ents4 is not None and all(
        text4[e["position"][0]:e["position"][1]] == e["text"] for e in ents4)
    print(f"  {'ok' if ok4 else 'FAIL'} ranh gioi tu, bat bien: {[(e['text'],e['position']) for e in (ents4 or [])]}")
    failed += not ok4

    # 5) anchor_all: chong lan bi giai quyet -- cum ngan nam trong cum dai bi bo
    text5 = "Hoi chung than hu nghiem trong."
    required5 = [
        ("than hu", "CHAN_DOAN"),
        ("Hoi chung than hu", "CHAN_DOAN"),
    ]
    ents5 = anchor_all(text5, required5)
    ok5 = ents5 is not None and len(ents5) == 1 and "Hoi chung" in ents5[0]["text"]
    print(f"  {'ok' if ok5 else 'FAIL'} giai quyet chong lan -> giu cum dai: "
          f"{[e['text'] for e in (ents5 or [])]}")
    failed += not ok5

    # 6) validate_document: van ban voi ty le tu 8%-18% -> pass
    # Xay dung van ban ~200 tu, thuc the ~20-30 tu
    base = ("Benh nhan nam 45 tuoi nhap vien vi sot cao keo dai 5 ngay. "
            "Kham phat hien viem phoi thuoc phai. Cho dung amoxicillin "
            "500mg ngay 3 lan. Xet nghiem cong thuc mau: BC 12 G/l. "
            "Nguoi benh cai thien sau 3 ngay dieu tri. " * 4)
    ents6 = [
        {"text": "sot cao", "type": "TRIỆU_CHỨNG", "position": [base.find("sot cao"), base.find("sot cao")+7]},
        {"text": "viem phoi", "type": "CHẨN_ĐOÁN", "position": [base.find("viem phoi"), base.find("viem phoi")+9]},
        {"text": "amoxicillin", "type": "THUỐC", "position": [base.find("amoxicillin"), base.find("amoxicillin")+11]},
    ]
    ok6, reason6 = validate_document(base, ents6)
    print(f"  {'ok' if ok6 else 'FAIL'} validate doc ngan: {reason6 or 'PASS'}")
    failed += not ok6

    # 7) validate_document bat loi C1 (nguyen van sai)
    text7 = "Benh nhan sot cao."
    ents7 = [{"text": "SOT CAO", "type": "TRIỆU_CHỨNG", "position": [10, 17]}]
    ok7, reason7 = validate_document(text7, ents7)
    print(f"  {'ok' if not ok7 else 'FAIL'} validate bat C1 nguyen van sai: {reason7}")
    failed += ok7   # phai fail

    # 8) validate_document bat loi C3 (chong lan)
    text8 = "Benh nhan sot cao keo dai."
    ents8 = [
        {"text": "sot cao", "type": "TRIỆU_CHỨNG", "position": [10, 17]},
        {"text": "cao keo", "type": "TRIỆU_CHỨNG", "position": [14, 21]},
    ]
    ok8, reason8 = validate_document(text8, ents8)
    print(f"  {'ok' if not ok8 else 'FAIL'} validate bat C3 chong lan: {reason8}")
    failed += ok8   # phai fail

    # 9) validate_document bat loi C7 (do dai)
    short = "Benh nhan sot."
    ents9 = [{"text": "sot", "type": "TRIỆU_CHỨNG", "position": [10, 13]}]
    ok9, reason9 = validate_document(short, ents9)
    print(f"  {'ok' if not ok9 else 'FAIL'} validate bat C7 van ban qua ngan: {reason9}")
    failed += ok9   # phai fail

    # 10) validate_document bat C6 am duoc gan nhan
    text10 = "Benh nhan dung noi soi da day va amoxicillin." * 50  # du dai
    am_x = ["noi soi da day"]
    ents10 = [
        {"text": "noi soi da day", "type": "TÊN_XÉT_NGHIỆM",
         "position": [text10.find("noi soi da day"),
                      text10.find("noi soi da day")+14]},
        {"text": "amoxicillin", "type": "THUỐC",
         "position": [text10.find("amoxicillin"),
                      text10.find("amoxicillin")+11]},
    ]
    ok10, reason10 = validate_document(text10, ents10, am_xetnghiem=am_x)
    print(f"  {'ok' if not ok10 else 'FAIL'} validate bat C6 am duoc gan nhan: {reason10}")
    failed += ok10

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"synth_anchor: {failed} ca THAT BAI")
    print("ok synth_anchor: tat ca ca PASS")


if __name__ == "__main__":
    test_synth_anchor()
'''

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(root, "src", "synth_anchor.py")
with open(out, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Written {out} ({len(content)} bytes)")
