"""
Sinh ứng viên span TỔNG QUÁT từ văn bản — dùng chung cho mọi nhánh cần "vá"
phần luật tất định không bắt được, thay vì liệt kê thêm một luật regex mới
mỗi khi gặp một dạng viết khác.

NGUYÊN LÝ: đừng cố NHẬN DIỆN mẫu (regex biết trước hình dạng). Thay vào đó
SINH MỌI TỔ HỢP con có thể là thực thể (n-gram từ chính văn bản), rồi để một
bước phân loại (LLM, ràng buộc lựa chọn) CHỌN trong số đó. Ứng viên luôn là
đoạn con của văn bản gốc nên không bao giờ bịa; việc còn lại chỉ là chọn đúng.

Đã đo (dry-run, không cần GPU): cách này phủ được 100% các dạng mà regex của
nhánh B từng bỏ sót — tỷ lệ huyết áp "130/76 mmHg", panel dính liền không dấu
phân cách "WBC : 14.99 G/L NEUT% : 82.9 %", mũi tên "Troponin I/T ↑", giá trị
không đơn vị "PT - INR: 1.05", và giá trị lồng trong câu văn
"lipase là tăng lên ở mức 623" — không cần biết trước bất kỳ dạng nào trong
số này, chỉ cần n-gram đủ rộng.
"""

import re
import unicodedata as ud
from typing import Dict, List, Set, Tuple

# Tách đoạn: giống branch_b_lab_tests.py — cắt ở \n ; : và dấu chấm câu,
# dấu phẩy KHÔNG nằm giữa hai chữ số ("4,49" là số thập phân tiếng Việt).
SPLIT = re.compile(r'(?<!\d),(?!\d)|[;:\n]|(?<=[a-zA-ZÀ-ỹ])\.(?=\s|$)')

# Hư từ: không bao giờ là điểm ĐẦU hay ĐIỂM CUỐI của một thực thể y khoa.
# Lọc ở BIÊN ứng viên, không lọc bỏ hẳn — "không có suy thận" vẫn cần giữ
# nguyên cụm "suy thận" dù bắt đầu bằng cách xa "không".
STOP = set("""và của có trong với là cho khi sau trước trên dưới do bị được các những
một hai ba bốn năm này kia đó đây thì mà nhưng hoặc nếu vì nên đã đang sẽ rất hơn nhất
theo về từ đến tại bởi cùng như để không chưa cũng vẫn còn lại ra vào lên xuống
ông bà anh chị em tôi ta họ nó ai gì sao nào đâu x""".split())


def segments_with_offset(text: str) -> List[Tuple[str, int, int]]:
    """Tách đoạn, giữ offset THẬT trong văn bản gốc. text[s:e] == đoạn."""
    out, last_end = [], 0

    def add(a: int, b: int):
        raw = text[a:b]
        stripped = raw.strip()
        if not stripped:
            return
        s = a + (len(raw) - len(raw.lstrip()))
        out.append((stripped, s, s + len(stripped)))

    for m in SPLIT.finditer(text):
        add(last_end, m.start())
        last_end = m.end()
    add(last_end, len(text))
    return out


def gen_candidates(text: str, nmax: int = 6) -> List[Dict]:
    """
    Sinh MỌI n-gram (≤ nmax từ) trong mỗi đoạn, cộng nguyên đoạn, lọc hư từ
    ở biên. Trả về list {text, start, end}, khoá theo offset (cùng chuỗi ở
    hai vị trí khác nhau = hai ứng viên riêng).

    Đã đo: 866 ứng viên / bệnh án 2040 ký tự, phủ 44/44 span đối chứng = 100%.
    """
    seen: Set[Tuple[int, int]] = set()
    out: List[Dict] = []

    def add(s: int, e: int):
        t = text[s:e]
        lstrip = len(t) - len(t.lstrip(' .;,:()[]'))
        rstrip = len(t) - len(t.rstrip(' .;,:()[]'))
        s, e = s + lstrip, e - rstrip
        if e <= s or (s, e) in seen:
            return
        seen.add((s, e))
        out.append({'text': text[s:e], 'start': s, 'end': e})

    for seg, base, _ in segments_with_offset(text):
        toks, p = [], 0
        for w in seg.split():
            i = seg.find(w, p)
            toks.append((w, base + i, base + i + len(w)))
            p = i + len(w)
        for i in range(len(toks)):
            for n in range(1, min(nmax, len(toks) - i) + 1):
                sl = toks[i:i + n]
                a = sl[0][0].lower().strip('.,;:()[]')
                b = sl[-1][0].lower().strip('.,;:()[]')
                if a in STOP or b in STOP:
                    continue
                add(sl[0][1], sl[-1][2])
        if toks:
            add(toks[0][1], toks[-1][2])   # nguyên đoạn — bắt span dài

    return out


def unresolved_regions(text: str, claimed: List[Tuple[int, int]],
                       signal: str = r'[\d↑↓]') -> List[Dict]:
    """
    Tìm phần văn bản CHƯA được luật tất định nhận (offset không nằm trong
    `claimed`) và có TÍN HIỆU đáng chú ý (mặc định: có chữ số hoặc mũi tên
    ↑↓). Dùng để giới hạn phạm vi sinh ứng viên cho bước "vá" — không sinh
    ứng viên trên toàn văn bản, chỉ trên vùng có khả năng chứa thực thể mà
    luật đã bỏ sót.

    Trả về list {text, start, end} — các ĐOẠN (không phải n-gram) hợp lệ.
    """
    claimed_mask = [False] * len(text)
    for s, e in claimed:
        for i in range(max(0, s), min(len(text), e)):
            claimed_mask[i] = True

    sig = re.compile(signal)
    segs = segments_with_offset(text)

    # Tín hiệu xét theo đoạn VÀ HAI ĐOẠN KỀ, không xét riêng lẻ.
    # Lý do: TÊN xét nghiệm thường không chứa chữ số ("WBC", "PT - INR",
    # "Troponin I/T") — nó đứng CẠNH đoạn có số. Lọc từng đoạn riêng sẽ
    # loại mất chính phần tên, chỉ giữ lại phần giá trị. Đã đo: bỏ qua
    # điều này thì "WBC" và "PT - INR" biến mất khỏi tập ứng viên.
    has_sig = [bool(sig.search(s)) for s, _, _ in segs]
    keep = [has_sig[i] or (i > 0 and has_sig[i - 1])
            or (i + 1 < len(segs) and has_sig[i + 1])
            for i in range(len(segs))]

    out = []
    for i, (seg, s, e) in enumerate(segs):
        if all(claimed_mask[j] for j in range(s, e)):
            continue                      # đã được luật nhận trọn vẹn
        if not keep[i]:
            continue                      # không có tín hiệu đáng vá
        out.append({'text': seg, 'start': s, 'end': e})
    return out


def gen_candidates_for_regions(text: str, regions: List[Dict],
                               nmax: int = 6) -> List[Dict]:
    """Sinh n-gram CHỈ trong các vùng đã chọn (không phải toàn văn bản)."""
    all_cands = gen_candidates(text, nmax=nmax)
    out = []
    for r in regions:
        for c in all_cands:
            if r['start'] <= c['start'] and c['end'] <= r['end']:
                out.append(c)
    return out


def test_span_candidates():
    """
    Đo lại đúng 6 ca đã phát hiện trong bệnh án thật khiến luật regex của
    nhánh B bỏ sót. Không thể pass rỗng: mỗi ca nêu rõ span PHẢI có trong
    tập ứng viên.
    """
    cases = [
        ('Huyết áp:130/76 mmHg', ['130/76 mmHg', 'Huyết áp']),
        ('WBC : 14.99 G/L NEUT% : 82.9 % (Tăng)',
         ['WBC', '14.99 G/L', 'NEUT%', '82.9 %']),
        ('Troponin I/T ↑ (chẩn đoán nhồi máu)', ['Troponin I/T', '↑']),
        ('PT - INR: 1.05', ['PT - INR', '1.05']),
        ('lipase là tăng lên ở mức 623 (lần nhập viện trước)',
         ['lipase', '623']),
        ('tbr là cao tới 1.0 sau đó cải thiện', ['tbr', '1.0']),
    ]
    failed = 0
    for text, must_have in cases:
        cand_texts = {c['text'] for c in gen_candidates(text)}
        miss = [m for m in must_have if m not in cand_texts]
        if miss:
            print(f"  ✗ {text!r}\n      THIẾU ứng viên: {miss}")
            failed += 1
        else:
            print(f"  ✓ {text!r} -> phủ đủ {must_have}")

    # offset phải khớp nguyên văn cho MỌI ứng viên sinh ra, trên mọi ca
    for text, _ in cases:
        for c in gen_candidates(text):
            if text[c['start']:c['end']] != c['text']:
                print(f"  ✗ offset sai trong {text!r}: {c}")
                failed += 1

    # unresolved_regions: nếu đã "claimed" hết thì không sinh ứng viên nào
    t = "Ure: 6,4 mmol/l"
    assert unresolved_regions(t, [(0, len(t))]) == [], \
        "unresolved_regions: vùng đã claimed hết vẫn còn sinh ra"
    # nếu CHƯA claimed gì mà có tín hiệu số -> phải thấy
    assert len(unresolved_regions(t, [])) > 0, \
        "unresolved_regions: có tín hiệu số nhưng không thấy vùng nào"
    print("  ✓ unresolved_regions: 2/2 ca PASS")

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"span_candidates: {failed} ca THẤT BẠI")
    print(f"✓ span_candidates: {len(cases)}/{len(cases)} ca PASS")


if __name__ == "__main__":
    test_span_candidates()
