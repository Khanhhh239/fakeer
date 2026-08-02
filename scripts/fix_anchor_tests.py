"""Fix 2 failing test cases in synth_anchor.py"""
import os

path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "synth_anchor.py")
with open(path, encoding="utf-8") as f:
    src = f.read()

# Fix 1: anchor_all -- span dai co score cao hon de select_non_overlapping giu dung
old_score = '''        for m in hits:
            ents.append({
                "text": text[m.start():m.end()],
                "type": etype,
                "position": [m.start(), m.end()],
                "score": 1.0,
            })'''

new_score = '''        for m in hits:
            # Span dai co score cao hon -> select_non_overlapping giu span dai
            ents.append({
                "text": text[m.start():m.end()],
                "type": etype,
                "position": [m.start(), m.end()],
                "score": 1.0 + (m.end() - m.start()) * 0.001,
            })'''

if old_score not in src:
    print("ERROR: old_score not found")
else:
    src = src.replace(old_score, new_score)
    print("Fixed score for longer spans")

# Fix 2: validate test case 6 -- xay dung van ban du dai va ty le thuc the hop le
old_test6 = '''    # 6) validate_document: van ban voi ty le tu 8%-18% -> pass
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
    failed += not ok6'''

new_test6 = '''    # 6) validate_document: van ban voi ty le tu 8%-18% -> pass
    # Can: do dai 1500-4000, ty le tu trong thuc the 8%-18%
    # Xay dung: ~2000 ky tu, 10-15% tu nam trong thuc the
    import random as _r
    _filler = ("Benh nhan nam 45 tuoi nhap vien vi sot cao keo dai 5 ngay. "
               "Kham phat hien viem phoi thuoc phai. Cho dung amoxicillin "
               "500mg ngay 3 lan sau an. Xet nghiem cong thuc mau tra ket qua. "
               "Nguoi benh cai thien sau 3 ngay dieu tri noi tru. ")
    # Lap de dat do dai 1500+ ky tu
    base = _filler * 8  # ~1720 ky tu
    # Dat nhieu thuc the de dat 8%-18%
    # Dem tu: ~250 tu, can 20-45 tu trong thuc the
    # Moi tu 5-8 ky tu, "sot cao"=2 tu, "viem phoi"=2 tu, "amoxicillin"=1 tu
    # Can ~15-20 thuc the lap lai
    positions = []
    search_start = 0
    for _ in range(8):  # tim 8 lan "sot cao"
        idx = base.find("sot cao", search_start)
        if idx < 0: break
        positions.append(("sot cao", "TRIỆU_CHỨNG", idx))
        search_start = idx + 1
    search_start = 0
    for _ in range(8):
        idx = base.find("viem phoi", search_start)
        if idx < 0: break
        positions.append(("viem phoi", "CHẨN_ĐOÁN", idx))
        search_start = idx + 1
    search_start = 0
    for _ in range(8):
        idx = base.find("amoxicillin", search_start)
        if idx < 0: break
        positions.append(("amoxicillin", "THUỐC", idx))
        search_start = idx + 1
    ents6 = [
        {"text": surf, "type": typ,
         "position": [idx, idx + len(surf)]}
        for surf, typ, idx in positions
    ]
    # Kiem truoc: bat bien
    for e in ents6:
        assert base[e["position"][0]:e["position"][1]] == e["text"], f"bat bien sai: {e}"
    ok6, reason6 = validate_document(base, ents6)
    _tw = len(base.split()); _ew = sum(len(e["text"].split()) for e in ents6)
    print(f"  {'ok' if ok6 else 'FAIL'} validate doc du dai "
          f"({len(base)} ky tu, {_tw} tu, {_ew} tu thuc the, ratio={_ew/_tw:.1%}): "
          f"{reason6 or 'PASS'}")
    failed += not ok6'''

if old_test6 not in src:
    print("ERROR: old test6 not found")
else:
    src = src.replace(old_test6, new_test6)
    print("Fixed test case 6")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("Done")
