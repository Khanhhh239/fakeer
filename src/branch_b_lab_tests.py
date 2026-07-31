"""
NHÁNH B - Trích xuất TÊN_XÉT_NGHIỆM và KẾT_QUẢ_XÉT_NGHIỆM
Chạy trên văn bản gốc, không cần model.

THIẾT KẾ: ghép theo ĐOẠN LIỀN KỀ, không ghép bằng regex bên trong một đoạn.

Vì sao: bước tách đoạn đã cắt ở dấu ':' nên "Ure: 6,4 mmol/l" thành HAI đoạn
riêng biệt là "Ure" và "6,4 mmol/l". Mọi regex cố ghép cặp tên/giá trị *bên trong*
một đoạn đều vô nghĩa sau bước đó — bản trước làm vậy và bắt được 0/11 xét nghiệm
thật trên bệnh án mẫu, đồng thời sinh ra rác kiểu:
    TÊN='Bệnh nhân nam' KẾT_QUẢ='17 tuổi'
    TÊN='1.  Medrol'    KẾT_QUẢ='16mg x 3 viên'

Cách đúng: đoạn nào LÀ "số + đơn vị y khoa" thì đó là KẾT_QUẢ, và đoạn ngay
trước nó là TÊN. Đo được: 11/11 xét nghiệm thật, 0 rác, offset khớp nguyên văn.
"""

import re
from typing import List, Dict, Tuple

from span_candidates import unresolved_regions, gen_candidates_for_regions

# Bước 1: Tách đoạn — cắt ở \n, ;, :, dấu chấm câu, và dấu phẩy KHÔNG nằm giữa
# hai chữ số ("4,49 T/l" là số thập phân tiếng Việt, cắt ở đó là hỏng).
SPLIT = re.compile(r'(?<!\d),(?!\d)|[;:\n]|(?<=[a-zA-ZÀ-ỹ])\.(?=\s|$)')

# Bước 2: Đơn vị y khoa — DANH SÁCH TRẮNG, bắt buộc.
# Không có nó thì "17 tuổi", "1 tháng", "8h sáng", "3 viên" đều lọt vào.
UNIT = (r'(?:mmol/l|mmol/L|micromol/l|µmol/l|umol/l|mol/l|'
        r'g/l|g/L|mg/dl|mg/dL|mg/l|g/dl|mg%|'
        r'T/l|G/l|U/l|UI/l|IU/l|U/L|'
        r'ng/ml|pg/ml|µg/l|mcg/l|µg/ml|mcg/ml|'
        r'mmHg|cmH2O|ml/phút|ml/min|l/ngày|'
        r'tế bào/mm3|/mm3|/µl|'
        r'%|kg|cm|mm|ml|dl)')

# Một đoạn LÀ giá trị xét nghiệm khi nó chỉ gồm (dấu so sánh) số (đơn vị).
VALUE_ONLY = re.compile(r'^[<>≤≥]?\s*\d+(?:[.,]\d+)?\s*' + UNIT + r'\.?$', re.I)

# Giá trị định tính: "(-)", "(+)", "(++)", "âm tính", "dương tính"
VALUE_QUAL = re.compile(r'^\(\s*[-+–±]{1,3}\s*\)$|^(?:âm tính|dương tính)$', re.I)

MAX_NAME_LEN = 40   # tên xét nghiệm dài hơn thế gần như chắc chắn là câu văn


def clean_name(n: str) -> str:
    """
    Làm sạch tên xét nghiệm.
    KHÔNG rstrip('-'): "Cl-", "HCO3-" là tên ion, dấu trừ thuộc về tên.
    LSTRIP thêm '-•·*': gạch đầu dòng trong "- ALT", "• CRP" là ký hiệu liệt
    kê ở ĐẦU đoạn, không phải một phần tên — khác với '-' ở CUỐI tên ion.
    """
    return n.strip().lstrip(':=–-•·*').rstrip(':=–').strip()


def clean_value(v: str) -> str:
    return v.strip().rstrip('.')


def split_segments(text: str) -> List[Tuple[str, int, int]]:
    """
    Tách văn bản thành các đoạn kèm offset THẬT trong văn bản gốc.

    Returns: List of (segment_text, start_offset, end_offset)
    Bất biến: text[start:end] == segment_text
    """
    segments = []
    last_end = 0

    def add(chunk_start: int, chunk_end: int):
        raw = text[chunk_start:chunk_end]
        stripped = raw.strip()
        if not stripped:
            return
        s = chunk_start + (len(raw) - len(raw.lstrip()))
        segments.append((stripped, s, s + len(stripped)))

    for m in SPLIT.finditer(text):
        add(last_end, m.start())
        last_end = m.end()
    add(last_end, len(text))
    return segments


def extract_lab_pairs(text: str) -> List[Dict]:
    """
    Trích xuất TÊN_XÉT_NGHIỆM / KẾT_QUẢ_XÉT_NGHIỆM bằng luật.

    Returns: list dict {text, type, start, end, score, source}
    Bất biến: text[e['start']:e['end']] == e['text'] với mọi e.
    """
    entities: List[Dict] = []
    segments = split_segments(text)
    used_name_idx = set()

    def emit(seg_idx: int, etype: str):
        seg, s, e = segments[seg_idx]
        if etype == 'TÊN_XÉT_NGHIỆM':
            cleaned = clean_name(seg)
        else:
            cleaned = clean_value(seg)
        if not cleaned:
            return
        # neo lại offset sau khi làm sạch, để text[start:end] luôn khớp
        off = seg.find(cleaned)
        if off < 0:
            return
        entities.append({
            'text': cleaned,
            'type': etype,
            'start': s + off,
            'end': s + off + len(cleaned),
            'score': 1.0,          # luật tất định
            'source': 'rule',
        })

    for i, (seg, _, _) in enumerate(segments):
        if not (VALUE_ONLY.match(seg) or VALUE_QUAL.match(seg)):
            continue
        emit(i, 'KẾT_QUẢ_XÉT_NGHIỆM')

        # đoạn ngay trước là TÊN, nếu nó hợp lệ
        j = i - 1
        if j < 0 or j in used_name_idx:
            continue
        prev = segments[j][0]
        if len(prev) > MAX_NAME_LEN:
            continue
        if VALUE_ONLY.match(prev) or VALUE_QUAL.match(prev):
            continue                      # hai giá trị liền nhau -> không có tên
        if not re.search(r'[A-Za-zÀ-ỹ]', prev):
            continue                      # tên phải có ít nhất một chữ cái
        used_name_idx.add(j)
        emit(j, 'TÊN_XÉT_NGHIỆM')

    entities.sort(key=lambda x: x['start'])
    return entities


def lab_va_candidates(text: str, resolved: List[Dict] = None) -> List[Dict]:
    """
    Sinh ứng viên cho bước VÁ — thay cho việc thêm luật regex mới mỗi khi
    gặp một dạng viết khác (huyết áp "130/76 mmHg", panel dính liền
    "WBC : 14.99 G/L NEUT%...", mũi tên "Troponin I/T ↑", giá trị không đơn
    vị "PT - INR: 1.05", giá trị lồng trong câu văn "lipase ... 623").

    KHÔNG tự phân loại — chỉ trả về ứng viên. Phân loại cần
    llm_choice_classifier.ChoiceClassifier với model đã nạp (cần GPU).

    Args:
        text: bệnh án gốc
        resolved: kết quả extract_lab_pairs(text) đã chạy trước — vùng đã
            được luật Tier-0 nhận sẽ KHÔNG sinh ứng viên chồng lên.
    """
    resolved = resolved or extract_lab_pairs(text)
    claimed = [(e['start'], e['end']) for e in resolved]
    regions = unresolved_regions(text, claimed)

    # KHÔNG dùng n-gram thô: đo được 572 ứng viên/bệnh án, hầu hết là rác
    # ngữ pháp ('Bệnh', 'Bệnh nhân nam 17', 'nhân nam'). Gửi 48k thứ đó cho LLM
    # vừa chậm vừa nguy hiểm — chỉ 1% dương tính giả là 480 thực thể thừa,
    # mà đề phạt trích thừa GẤP 3. Thà bỏ sót còn hơn.
    #
    # Thay bằng luật cấu trúc: một KẾT_QUẢ_XÉT_NGHIỆM luôn CHỨA CHỮ SỐ (hoặc
    # ↑↓, (-), (+)); một TÊN_XÉT_NGHIỆM luôn ĐỨNG NGAY TRƯỚC phần giá trị đó.
    # Nên mỗi đoạn chỉ sinh tối đa 3 ứng viên: nguyên đoạn, phần-trước-số,
    # phần-từ-số. Đo được: 572 -> ~6 ứng viên/bệnh án.
    SIG = re.compile(r'[\d↑↓]|\([-+–±]{1,3}\)')
    # lõi giá trị: số (có thể là tỉ lệ 130/76) + đơn vị, HOẶC mũi tên, HOẶC (-)
    CORE = re.compile(r'[<>≤≥]?\s*\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?'
                      r'(?:\s*[a-zA-ZÀ-ỹ][a-zA-ZÀ-ỹ/%µ°]*)?|[↑↓]|\([-+–±]{1,3}\)')
    BARE = re.compile(r'[<>≤≥]?\s*\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?')
    MAXW = 8
    out, seen = [], set()

    def add(s, e):
        t = text[s:e]
        # lstrip thêm '-•·*': "- ALT", "• Troponin I/T" nguyên câu bị dính
        # gạch đầu dòng vào ứng viên, LLM nhận cả gạch làm 1 phần "tên" ->
        # sai text_score dù type/nghĩa đúng.
        st = len(t) - len(t.lstrip(' .;,:-•·*')); en = len(t) - len(t.rstrip(' .;,:'))
        s, e = s + st, e - en
        if e <= s or (s, e) in seen:
            return
        t = text[s:e]
        if not t or len(t.split()) > MAXW:
            return
        seen.add((s, e)); out.append({'text': t, 'start': s, 'end': e})

    for i, r in enumerate(regions):
        seg, base = r['text'], r['start']
        has_sig = bool(SIG.search(seg))

        # (a) đoạn KHÔNG có số nhưng đoạn SAU có -> đây là ứng viên TÊN
        #     ("WBC" trước "14.99 G/L", "PT - INR" trước "1.05")
        if not has_sig:
            nxt = regions[i + 1] if i + 1 < len(regions) else None
            if nxt and SIG.search(nxt['text']):
                add(base, base + len(seg))
            continue

        add(base, base + len(seg))                    # nguyên đoạn
        m = SIG.search(seg)
        if m.start() > 0:
            add(base, base + m.start())               # phần TÊN (trước số)
        # vài từ đầu: bắt tên ngắn lẫn trong câu ("lipase là tăng lên ở mức 623")
        w = seg.split()
        for n in (1, 2, 3):
            if n < len(w):
                pre = ' '.join(w[:n])
                if not SIG.search(pre):
                    add(base, base + len(pre))
                # đuôi đoạn: tên đứng CUỐI, trước giá trị của đoạn sau
                # ("...G/L NEUT%" rồi đoạn sau là "82.9 %")
                suf = ' '.join(w[-n:])
                if not SIG.search(suf):
                    j = seg.rfind(suf)
                    if j >= 0:
                        add(base + j, base + j + len(suf))
        # lõi giá trị, tách khỏi đuôi văn xuôi ("623" chứ không "623 (lần...)")
        # BARE trước CORE: '1.0' phải có, vì CORE có thể nuốt nhầm chữ kế
        # ("1.0 sau" — 'sau' trông như đơn vị với regex thuần).
        for pat in (BARE, CORE):
            for cm in pat.finditer(seg):
                add(base + cm.start(), base + cm.end())
    return out


# --------------------------------------------------------------------------
# TEST — mỗi ca nêu rõ SỐ thực thể mong đợi, nên không thể "pass rỗng".
# Bản trước chỉ lặp qua kết quả rồi assert offset; khi không trích được gì
# thì vòng lặp không chạy và test báo PASS dù bắt được 0/11.
# --------------------------------------------------------------------------

def test_branch_b():
    cases = [
        # (văn bản, số thực thể mong đợi, danh sách (type, text) phải có)
        ("Ure: 6,4 mmol/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'Ure'), ('KẾT_QUẢ_XÉT_NGHIỆM', '6,4 mmol/l')]),
        ("Creatinin: 79 micromol/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'Creatinin'), ('KẾT_QUẢ_XÉT_NGHIỆM', '79 micromol/l')]),
        ("HC: 4,49 T/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'HC'), ('KẾT_QUẢ_XÉT_NGHIỆM', '4,49 T/l')]),
        # dấu trừ của tên ion PHẢI còn nguyên
        ("Cl-: 106 mmol/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'Cl-'), ('KẾT_QUẢ_XÉT_NGHIỆM', '106 mmol/l')]),
        ("HCO3-: 24 mmol/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'HCO3-'), ('KẾT_QUẢ_XÉT_NGHIỆM', '24 mmol/l')]),
        ("Ca++: 2 mmol/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'Ca++'), ('KẾT_QUẢ_XÉT_NGHIỆM', '2 mmol/l')]),
        # không dấu cách sau dấu hai chấm
        ("Triglycerid:6,7 mmol/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'Triglycerid'), ('KẾT_QUẢ_XÉT_NGHIỆM', '6,7 mmol/l')]),
        # gạch đầu dòng / bullet PHẢI bị cắt khỏi tên — nếu không, text sai
        # so với gold dù type đúng (mất điểm WER dù bắt trúng thực thể)
        ("- ALT: 45 U/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'ALT'), ('KẾT_QUẢ_XÉT_NGHIỆM', '45 U/l')]),
        ("• CRP: 12 mg/l", 2,
         [('TÊN_XÉT_NGHIỆM', 'CRP'), ('KẾT_QUẢ_XÉT_NGHIỆM', '12 mg/l')]),
        # NHỮNG CA PHẢI TRẢ VỀ RỖNG — đây là chỗ bản trước sinh rác
        ("Bệnh nhân nam 17 tuổi", 0, []),
        ("tức nặng 2 chi dưới", 0, []),
        ("1.        Medrol 16mg x 3 viên, uống 8h sáng sau ăn no", 0, []),
        ("bệnh khởi phát cách đây 1 tháng", 0, []),
        ("uống ít nước < 1l/ngày", 0, []),
    ]

    failed = 0
    for text, n_expect, must_have in cases:
        ents = extract_lab_pairs(text)
        got = [(e['type'], e['text']) for e in ents]
        ok = True

        if len(ents) != n_expect:
            print(f"  ✗ {text!r}\n      mong {n_expect} thực thể, nhận {len(ents)}: {got}")
            ok = False
        for pair in must_have:
            if pair not in got:
                print(f"  ✗ {text!r}\n      thiếu {pair}, nhận {got}")
                ok = False
        for e in ents:
            if text[e['start']:e['end']] != e['text']:
                print(f"  ✗ {text!r}\n      offset sai: "
                      f"{text[e['start']:e['end']]!r} != {e['text']!r}")
                ok = False
        if ok:
            print(f"  ✓ {text!r} -> {got}")
        else:
            failed += 1

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"Branch B: {failed}/{len(cases)} ca THẤT BẠI")
    print(f"✓ Branch B: {len(cases)}/{len(cases)} ca PASS")


def test_lab_va_candidates():
    """
    6 dạng đã đo được là luật Tier-0 bỏ sót thật trên bệnh án thật (16/100
    file). Kiểm: (a) vùng đã được Tier-0 nhận đúng thì KHÔNG sinh ứng viên
    chồng lên, (b) vùng Tier-0 bỏ sót thì ứng viên PHẢI chứa span đúng.
    """
    cases = [
        ('Huyết áp:130/76 mmHg', ['130/76 mmHg']),
        ('WBC : 14.99 G/L NEUT% : 82.9 % (Tăng)', ['WBC', '14.99 G/L', 'NEUT%']),
        ('Troponin I/T ↑ (chẩn đoán nhồi máu)', ['Troponin I/T', '↑']),
        ('PT - INR: 1.05', ['PT - INR', '1.05']),
        ('lipase là tăng lên ở mức 623 (lần nhập viện trước)', ['lipase', '623']),
        ('tbr là cao tới 1.0 sau đó cải thiện', ['tbr', '1.0']),
        # gạch đầu dòng ở ĐẦU vùng mờ (Tier-0 không bắt vì thiếu đơn vị) —
        # ứng viên gửi cho LLM phải sạch, không dính '- '/'• '
        ('- Troponin I/T: 623', ['Troponin I/T', '623']),
    ]
    failed = 0
    for text, must_have in cases:
        cands = {c['text'] for c in lab_va_candidates(text)}
        miss = [m for m in must_have if m not in cands]
        if miss:
            print(f"  ✗ {text!r}\n      THIẾU: {miss}")
            failed += 1
        else:
            print(f"  ✓ {text!r} -> vá phủ đủ {must_have}")

    # ca ĐÃ sạch (Tier-0 bắt trọn) -> vá không sinh ứng viên chồng lên
    clean = "Ure: 6,4 mmol/l"
    resolved = extract_lab_pairs(clean)
    assert len(resolved) == 2, "case sạch: Tier-0 phải bắt được 2 thực thể"
    va = lab_va_candidates(clean, resolved)
    overlap = [c for c in va if any(
        c['start'] < e['end'] and e['start'] < c['end'] for e in resolved)]
    if overlap:
        print(f"  ✗ vùng đã sạch vẫn sinh {len(overlap)} ứng viên chồng lên Tier-0")
        failed += 1
    else:
        print(f"  ✓ case sạch (Tier-0 bắt trọn): vá không sinh ứng viên thừa")

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"lab_va_candidates: {failed} ca THẤT BẠI")
    print(f"✓ lab_va_candidates: {len(cases)+1}/{len(cases)+1} ca PASS")


if __name__ == "__main__":
    test_branch_b()
    print()
    test_lab_va_candidates()
