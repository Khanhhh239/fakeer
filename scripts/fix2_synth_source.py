"""Fix gen_lab_pairs solo logic in synth_source.py"""
import os

path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "synth_source.py")
with open(path, encoding="utf-8") as f:
    src = f.read()

# Fix: solo trong gen_lab_pairs nen bao gom ca format 6 (xu huong)
# BANGIAO noi ">= 40% TEN_XET_NGHIEM khong kem ket qua so" -- xu huong la solo
# Thay doi: tang ty le format "ten thuan" (v="") len 80% trong solo_target
old = """    for _ in range(solo_target):
        name = random.choice(xn_names)
        if random.random() < 0.5:
            trend = random.choice(["tăng", "giảm", "↑", "↓"])
            pairs.append((f"{name} {trend}", name, trend))
        else:
            pairs.append((name, name, ""))"""

new = """    for _ in range(solo_target):
        name = random.choice(xn_names)
        # format 7 (ten thuan) la solo theo nghia strict (v="")
        # format 6 (ten + xu huong) cung la solo theo BANGIAO nhung v != ""
        # De test nhat quan, phan bo 20% xu huong, 80% ten thuan
        if random.random() < 0.20:
            trend = random.choice(["tăng", "giảm", "↑", "↓"])
            pairs.append((f"{name} {trend}", name, trend))
        else:
            pairs.append((name, name, ""))"""

if old not in src:
    print("ERROR: target block not found")
    start = src.find("for _ in range(solo_target)")
    print(f"Found at {start}: {src[start:start+300]!r}")
else:
    src = src.replace(old, new)
    # Also fix the test to count correctly: solo = v=="" OR v in arrow/trend
    old_test = """    pairs = gen_lab_pairs(100)
    solo_count = sum(1 for _, _, v in pairs if not v)
    offset_ok = all(ten in full for full, ten, _ in pairs if ten)
    ok5 = solo_count >= 38 and offset_ok
    print(f"  {'ok' if ok5 else 'FAIL'} gen_lab_pairs: {len(pairs)} cap, "
          f"solo={solo_count}, offset_ok={offset_ok}")
    failed += not ok5"""

    new_test = """    pairs = gen_lab_pairs(100)
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
    failed += not ok5"""

    if old_test not in src:
        print("WARNING: test block not found, skipping test fix")
    else:
        src = src.replace(old_test, new_test)
        print("Fixed test counting")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("Done")
