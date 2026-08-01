"""
K6 — Neo (anchor) cụm do LLM sinh về lại văn bản gốc, và xác thực.

Bất biến sống còn của pipeline: LLM KHÔNG BAO GIỜ được phép "viết ra" một
span. Nó chỉ được CHỈ VÀO một đoạn trong văn bản gốc. anchor() là nơi DUY
NHẤT quyết định một cụm LLM sinh ra có được chấp nhận hay không; sau khi
chấp nhận, text luôn lấy lại từ chính văn bản gốc (src[start:end]) — không
bao giờ dùng chuỗi LLM sinh trực tiếp. Đây là nguyên nhân duy nhất khiến
`text == src[start:end]` đúng THEO CẤU TRÚC, không phải nhờ may mắn.

4 bậc, từ chặt đến lỏng — dừng ở bậc đầu tiên khớp. Không khớp bậc nào ->
BỎ (thà bỏ sót còn hơn giữ một span không thật sự có trong văn bản).
"""

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

FUZZY_MIN_RATIO = 0.85
EDGE_STRIP = ' \t.,;:!?()[]{}"\'-–—•·*”“’‘'


def _ws_flex_search(gen_text: str, unit_text: str) -> Optional[Tuple[int, int]]:
    """Khớp không phân biệt hoa/thường, khoảng trắng linh hoạt (1 khớp \\s+)."""
    parts = [re.escape(p) for p in gen_text.split()]
    if not parts:
        return None
    m = re.search(r'\s+'.join(parts), unit_text, re.IGNORECASE)
    return (m.start(), m.end()) if m else None


def _fuzzy_window(gen_text: str, unit_text: str) -> Optional[Tuple[int, int]]:
    """Trượt cửa sổ CÙNG SỐ TỪ trong unit_text, so khớp bằng difflib.
    Dùng khi LLM sửa nhẹ chính tả/dấu câu nhưng vẫn cùng cụm từ gốc."""
    words = unit_text.split()
    gw = gen_text.split()
    if not gw or not words or len(gw) > len(words):
        return None
    spans, pos = [], 0
    for w in words:
        i = unit_text.index(w, pos)     # an toàn: cursor luôn tiến, không lùi
        spans.append((i, i + len(w)))
        pos = i + len(w)
    k = len(gw)
    best_ratio, best_span = 0.0, None
    gl = gen_text.lower()
    for i in range(len(words) - k + 1):
        cand = unit_text[spans[i][0]:spans[i + k - 1][1]]
        ratio = SequenceMatcher(None, cand.lower(), gl).ratio()
        if ratio > best_ratio:
            best_ratio, best_span = ratio, (spans[i][0], spans[i + k - 1][1])
    return best_span if best_ratio >= FUZZY_MIN_RATIO else None


def anchor(gen_text: str, unit_text: str, unit_start: int) -> Optional[Tuple[int, int]]:
    """
    Tìm (start, end) TUYỆT ĐỐI trong văn bản gốc cho `gen_text` (LLM sinh),
    biết nó nằm trong `unit_text` bắt đầu tại `unit_start`.

    Trả None nếu không neo được -> gọi nơi BỎ span, không suy diễn thêm.
    """
    gen_text = (gen_text or '').strip()
    if not gen_text:
        return None

    i = unit_text.find(gen_text)                      # bậc 1: substring nguyên văn
    if i >= 0:
        return unit_start + i, unit_start + i + len(gen_text)

    hit = _ws_flex_search(gen_text, unit_text)         # bậc 2: hoa/thường + khoảng trắng
    if hit:
        return unit_start + hit[0], unit_start + hit[1]

    stripped = gen_text.strip(EDGE_STRIP)              # bậc 3: cắt biên rồi thử lại
    if stripped and stripped != gen_text:
        hit = anchor(stripped, unit_text, unit_start)
        if hit:
            return hit

    hit = _fuzzy_window(gen_text, unit_text)           # bậc 4: fuzzy cùng số từ
    if hit:
        return unit_start + hit[0], unit_start + hit[1]

    return None


def anchor_entities(raw_items: List[Tuple[str, str]], unit: Dict) -> List[Dict]:
    """
    Neo một loạt (type_code, gen_text) LLM sinh cho MỘT unit.

    Trả list entity {text, start, end} đã neo THẬT vào văn bản gốc — text
    luôn được cắt từ unit['text'] chứ không phải gen_text. Mục nào không
    neo được thì bị loại âm thầm (không raise), gọi nơi tự đếm nếu cần.
    """
    out = []
    for code, gen_text in raw_items:
        hit = anchor(gen_text, unit['text'], unit['start'])
        if not hit:
            continue
        s, e = hit
        out.append({'text': unit['text'][s - unit['start']:e - unit['start']],
                    'start': s, 'end': e, 'code': code})
    return out


PLACEHOLDER = re.compile(
    r'^(không ghi rõ|không rõ|chưa rõ|n/?a|không có|không|có)\.?$', re.I)
_NUM_ONLY = re.compile(r'^[<>≤≥]?\s*\d+(?:[.,]\d+)?\s*%?$')
_QUAL_VALUE = re.compile(r'^\(?\s*[-+–±]{1,3}\s*\)?$|^(?:âm tính|dương tính)$', re.I)
MAX_ENTITIES_PER_SHORT_UNIT = 6
SHORT_UNIT_WORDS = 15


# Trần độ dài theo LOẠI, tính bằng SỐ TỪ.
#
# VÌ SAO CẦN — đo được, không phải phòng xa: bài nộp V2 đầu tiên bảo LLM "lấy
# cụm ĐẦY ĐỦ NHẤT" nên nó nuốt trọn cả câu. Số TỪ tăng 94% (5539 -> 10738)
# trong khi số thực thể chỉ tăng 19%, và WER xấu đi 63.56 -> 72.71. WER tính
# trên TỪ: một span 27 từ gán sai vừa tạo 27 lượt insertion, vừa che mất khái
# niệm thật nằm bên trong (thêm deletion) — đắt gấp nhiều lần việc bỏ qua nó.
# Theo NL1 (bỏ sót và trích thừa phạt ngang nhau) thì với span dài bất thường,
# BỎ có lợi hơn GIỮ.
#
# CÁCH CHỌN SỐ: xuất phát từ phân vị của chính bài chấm tốt hơn (WER 63.56),
# nhưng có hiệu chỉnh ở hai loại mà phân bố của bài đó BỊ THIÊN LỆCH:
#   - TÊN_XÉT_NGHIỆM: bài đó trích bằng luật "số + đơn vị" nên chỉ bắt được
#     viết tắt ngắn ('SPO2', 'BC', '- ast'); p95=4 của nó không phản ánh độ
#     dài thật của tên thủ thuật ('chụp CT sọ não', 'siêu âm tim') -> nới 5.
#   - THUỐC: bài đó khớp từ điển RxNorm vốn trả tên đơn lẻ ('doxycycline',
#     'Vitamin K'); cụm thuốc thật dài hơn ('thuốc giảm đau opioid') -> nới 4.
#   - CHẨN_ĐOÁN lấy p99=8 thay p95=7, vì tên bệnh tiếng Việt thật sự dài
#     ('tụ máu ngoài màng cứng phải cấp tính' = 8 từ).
# Kết quả trên chính dữ liệu V2: 10738 -> 6169 từ (1.11x ngân sách bài tốt),
# vẫn giữ TÊN_XÉT_NGHIỆM gấp ~4 lần bài tốt (261 so với 67).
MAX_WORDS_BY_TYPE = {
    'THUỐC': 4,
    'TÊN_XÉT_NGHIỆM': 5,
    'KẾT_QUẢ_XÉT_NGHIỆM': 4,
    'TRIỆU_CHỨNG': 5,
    'CHẨN_ĐOÁN': 8,
}
MAX_WORDS_DEFAULT = 6


def _structural_gate(etype: str, text: str) -> bool:
    """Chặn cấu trúc BẤT KỂ LLM tự tin bao nhiêu — bài học từ V1: model có
    thể rất tự tin mà vẫn sai (xem 65acb97). True = giữ, False = loại."""
    t = text.strip()
    if len(t.split()) > MAX_WORDS_BY_TYPE.get(etype, MAX_WORDS_DEFAULT):
        return False                # span dài bất thường -> gần như chắc là cả câu
    if etype == 'TÊN_XÉT_NGHIỆM' and _NUM_ONLY.match(t):
        return False                # số thuần không thể là TÊN xét nghiệm
    if etype == 'KẾT_QUẢ_XÉT_NGHIỆM' and not re.search(r'\d', t) and not _QUAL_VALUE.match(t):
        return False                # KẾT_QUẢ phải có chữ số hoặc định tính rõ
    return True


def verify_unit_entities(raw_items: List[Tuple[str, str]], unit: Dict,
                          code2type: Dict[str, str]) -> List[Dict]:
    """
    Toàn bộ hàng rào K6 cho MỘT unit: lọc placeholder -> neo về văn bản gốc
    -> chặn cấu trúc theo loại -> chặn mật độ bất thường.

    raw_items : [(code, gen_text), ...] do K2 (LLM) sinh cho unit này.
    code2type : {'TC': 'TRIỆU_CHỨNG', ...} — ánh xạ mã prompt sang tên loại.

    Trả entity đầy đủ {text, type, start, end, source, heading, zone} —
    sẵn sàng đưa thẳng vào K7 (merge_entities.merge).
    """
    clean = [(c, t) for c, t in raw_items if not PLACEHOLDER.match((t or '').strip())]
    anchored = anchor_entities(clean, unit)
    for e in anchored:
        e['type'] = code2type.get(e.pop('code'), None)
    anchored = [e for e in anchored if e['type']]
    anchored = [e for e in anchored if _structural_gate(e['type'], e['text'])]

    if len(unit['text'].split()) < SHORT_UNIT_WORDS and len(anchored) > MAX_ENTITIES_PER_SHORT_UNIT:
        anchored.sort(key=lambda e: e['end'] - e['start'], reverse=True)
        kept, occupied = [], []
        for e in anchored:
            if any(e['start'] < b and a < e['end'] for a, b in occupied):
                continue
            kept.append(e); occupied.append((e['start'], e['end']))
        anchored = kept

    for e in anchored:
        e['source'] = 'llm'
        e['heading'] = unit.get('heading')
        e['zone'] = unit.get('zone')
    return anchored


def test_span_anchor():
    failed = 0

    cases = [
        # (gen_text, unit_text, kỳ vọng text neo được, hoặc None nếu phải BỎ)
        ("đau bụng", "Bệnh nhân đau bụng nhiều ngày", "đau bụng"),
        ("Đau Bụng", "Bệnh nhân đau bụng nhiều ngày", "đau bụng"),        # khác hoa/thường
        ("đau  bụng", "Bệnh nhân đau bụng nhiều ngày", "đau bụng"),      # thừa khoảng trắng
        ("đau bụng.", "Bệnh nhân đau bụng, nhiều ngày", "đau bụng"),     # sai dấu câu biên
        ("đau bụng dữ dội", "Bệnh nhân đau bụng dử dội nhiều ngày", "đau bụng dử dội"),  # fuzzy: LLM gõ đúng chính tả 'dữ' nhưng gốc viết sai 'dử'
        ("sốt xuất huyết Dengue", "chẩn đoán viêm phổi", None),          # không có trong unit -> BỎ
        ("", "Bệnh nhân đau bụng", None),                                 # rỗng -> BỎ
    ]
    for gen, unit_text, expect in cases:
        hit = anchor(gen, unit_text, 100)
        got = unit_text[hit[0] - 100:hit[1] - 100] if hit else None
        ok = got == expect
        print(f"  {'✓' if ok else '✗'} anchor({gen!r}, ...) -> {got!r}  (mong {expect!r})")
        failed += not ok

    # offset TUYỆT ĐỐI phải cộng đúng unit_start, và text phải lấy từ NGUỒN GỐC
    unit = {'text': 'đau bụng nhiều ngày', 'start': 250}
    hit = anchor('đau bụng', unit['text'], unit['start'])
    ok = hit == (250, 258)
    print(f"  {'✓' if ok else '✗'} offset tuyệt đối -> {hit} (mong (250, 258))")
    failed += not ok

    # anchor_entities: text LUÔN lấy từ văn bản gốc, không phải chuỗi LLM sinh
    src = "Bệnh nhân sốt cao, ho khan, đau đầu nhiều."
    unit2 = {'text': src, 'start': 0}
    ents = anchor_entities([('TC', 'sốt cao'), ('TC', 'ho khan'), ('TC', 'không tồn tại')], unit2)
    ok2 = (len(ents) == 2 and ents[0]['text'] == 'sốt cao' and ents[1]['text'] == 'ho khan'
           and all(src[e['start']:e['end']] == e['text'] for e in ents))
    print(f"  {'✓' if ok2 else '✗'} anchor_entities lọc mục không neo được -> {[e['text'] for e in ents]}")
    failed += not ok2

    # verify_unit_entities: lọc placeholder + gán type + chặn cấu trúc + neo
    code2type = {'TC': 'TRIỆU_CHỨNG', 'TX': 'TÊN_XÉT_NGHIỆM', 'KQ': 'KẾT_QUẢ_XÉT_NGHIỆM'}
    unit3 = {'text': 'WBC 14.99 G/L, thời gian khởi phát: Không ghi rõ',
             'start': 500, 'heading': 'Kết quả xét nghiệm', 'zone': 'clinical'}
    raw = [('TX', 'WBC'), ('KQ', '14.99 G/L'), ('TX', '421'),   # số thuần -> loại
           ('TC', 'Không ghi rõ')]                               # placeholder -> loại
    ents3 = verify_unit_entities(raw, unit3, code2type)
    texts3 = sorted(e['text'] for e in ents3)
    ok3 = (texts3 == ['14.99 G/L', 'WBC']
           and all(unit3['text'][e['start']-500:e['end']-500] == e['text'] for e in ents3)
           and all(e['heading'] == 'Kết quả xét nghiệm' for e in ents3))
    print(f"  {'✓' if ok3 else '✗'} verify_unit_entities lọc placeholder+số thuần -> {texts3}")
    failed += not ok3

    # chặn mật độ: unit ngắn mà sinh quá nhiều thực thể -> giữ span dài nhất
    unit4 = {'text': 'sốt ho đau đầu mệt buồn nôn chóng mặt', 'start': 0,
             'heading': None, 'zone': 'advice'}
    raw4 = [('TC', w) for w in ['sốt', 'ho', 'đau đầu', 'mệt', 'buồn nôn', 'chóng mặt', 'đau']]
    ents4 = verify_unit_entities(raw4, unit4, {'TC': 'TRIỆU_CHỨNG'})
    ok4 = len(ents4) <= MAX_ENTITIES_PER_SHORT_UNIT
    print(f"  {'✓' if ok4 else '✗'} chặn mật độ unit ngắn -> {len(raw4)} đề xuất -> {len(ents4)} giữ")
    failed += not ok4

    # chặn ĐỘ DÀI theo loại — đây là lỗi đã làm WER xấu đi 63.6 -> 72.7 ở
    # bài nộp V2 đầu tiên (LLM nuốt trọn cả câu làm một thực thể)
    long_sent = ('Chụp kiểm tra ghi nhận tụ máu ngoài màng cứng phải cấp tính '
                 'trên nền tổn thương mạn tính')
    unit5 = {'text': long_sent, 'start': 0, 'heading': 'Diễn biến bệnh', 'zone': 'clinical'}
    ents5 = verify_unit_entities([('CD', long_sent)], unit5, {'CD': 'CHẨN_ĐOÁN'})
    ok5 = ents5 == []
    print(f"  {'✓' if ok5 else '✗'} chặn cả câu {len(long_sent.split())} từ gán CHẨN_ĐOÁN -> giữ {len(ents5)}")
    failed += not ok5

    # nhưng cụm LÕI trong chính câu đó vẫn phải qua được — tên bệnh tiếng Việt
    # thật sự dài tới 8 từ, đây là lý do trần CHẨN_ĐOÁN lấy p99 chứ không p95
    core = 'tụ máu ngoài màng cứng phải cấp tính'   # đúng 8 từ = trần CHẨN_ĐOÁN
    assert len(core.split()) == 8, 'test tự mâu thuẫn: lõi phải đúng 8 từ'
    ents6 = verify_unit_entities([('CD', core)], unit5, {'CD': 'CHẨN_ĐOÁN'})
    ok6 = len(ents6) == 1 and ents6[0]['text'] == core
    print(f"  {'✓' if ok6 else '✗'} lõi {len(core.split())} từ vẫn qua -> {[e['text'] for e in ents6]}")
    failed += not ok6

    # trần RIÊNG theo loại: cùng một cụm, TÊN_XÉT_NGHIỆM (trần 5) cho qua
    # nhưng KẾT_QUẢ_XÉT_NGHIỆM (trần 4) thì chặn
    u7 = {'text': 'chụp CT sọ não toàn bộ có cản quang', 'start': 0,
          'heading': 'Các thủ thuật đã thực hiện', 'zone': 'clinical'}
    five = 'chụp CT sọ não toàn'          # 5 từ
    six = 'chụp CT sọ não toàn bộ'        # 6 từ
    assert len(five.split()) == 5 and len(six.split()) == 6, 'test tự mâu thuẫn'
    keep7 = verify_unit_entities([('TX', five)], u7, {'TX': 'TÊN_XÉT_NGHIỆM'})
    drop7 = verify_unit_entities([('TX', six)], u7, {'TX': 'TÊN_XÉT_NGHIỆM'})
    ok7 = len(keep7) == 1 and drop7 == []
    print(f"  {'✓' if ok7 else '✗'} trần TÊN_XÉT_NGHIỆM=5 từ -> 5từ:{len(keep7)} 6từ:{len(drop7)}")
    failed += not ok7

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"span_anchor: {failed} ca THẤT BẠI")
    print(f"✓ span_anchor: tất cả ca PASS")


if __name__ == "__main__":
    test_span_anchor()
