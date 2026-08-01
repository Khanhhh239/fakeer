"""
K1 — Phân đoạn văn bản thành các UNIT cho pipeline V2.

Vì sao cần: đo trên 100 file input thật, 1264/1277 bullet (99%) có một
heading cha ngay phía trên, và heading đó TỰ KHAI BÁO loại thực thể bên
dưới nó ("Các thủ thuật đã thực hiện" -> TÊN_XÉT_NGHIỆM, "Các bệnh lý mạn
tính" -> CHẨN_ĐOÁN...). V1 bỏ hoàn toàn tín hiệu này. K1 gắn heading + zone
vào từng unit để K2 (prompt LLM) và K7 (hợp nhất) dùng làm ngữ cảnh.

Đơn vị (unit) là bullet hoặc một câu/mệnh đề văn xuôi — đủ ngắn để LLM ít
ảo giác, đủ nhỏ để batch nhanh.
"""

import re
from typing import Dict, List, Optional

BULLET = re.compile(r'^([ \t]*)([-•*])\s+(.+?)\s*$')
# heading: dòng KHÔNG bullet, ngắn (4-60 ký tự), KHÔNG kết thúc bằng dấu câu
# kết câu, bắt đầu bằng chữ hoa (có thể có tiền tố số thứ tự "1.", "2.").
HEAD_RE = re.compile(r'^(?:\d+\.\s*)?([A-ZÀ-ỸĐ][^\n]{3,58})$')
# mốc bệnh án cấu trúc, vd "2.  Tiền sử bệnh hiện tại" — đã đo khớp 70/100 file.
ZONE_MARK = re.compile(r'^\s*([2-9])\.\s{1,4}([A-ZÀ-ỸĐ][^\n]{3,60})\s*$', re.M)
SENT_END = re.compile(r'[.;!?]+(?:\s+|$)')
CLAUSE_END = re.compile(r',\s+')

MAX_WORDS_UNIT = 40   # câu văn xuôi dài hơn thì tách tiếp theo dấu phẩy
MIN_UNIT_CHARS = 2


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or BULLET.match(line):
        return False
    if len(s) > 60 or s[-1] in '.!?':
        return False
    return bool(HEAD_RE.match(s))


def _clean_heading(line: str) -> str:
    s = line.strip().rstrip(':').strip()
    return re.sub(r'^\d+\.\s*', '', s)


def zone_cut(text: str) -> Optional[int]:
    """Offset bắt đầu khối bệnh án cấu trúc trong `text`, None nếu không có mốc."""
    m = ZONE_MARK.search(text)
    return m.start() if m else None


def _emit(chunk: str, rel_pos: int, abs_start: int, out: List[Dict]):
    """Cắt khoảng trắng biên, neo offset TUYỆT ĐỐI bằng phép cộng vị trí —
    không dùng .find()/.index() để tránh lệch khi chuỗi con trùng lặp."""
    lead = len(chunk) - len(chunk.lstrip())
    body = chunk.strip()
    if len(body) < MIN_UNIT_CHARS:
        return
    s = abs_start + rel_pos + lead
    out.append({'text': body, 'start': s, 'end': s + len(body)})


def _split_prose_line(line: str, abs_start: int) -> List[Dict]:
    """Tách 1 dòng văn xuôi thành câu; câu > MAX_WORDS_UNIT từ tách tiếp
    theo dấu phẩy. Offset tính từ span regex, tuyệt đối, không đoán."""
    out: List[Dict] = []
    n = len(line)
    cuts = [0] + [m.end() for m in SENT_END.finditer(line)]
    if cuts[-1] != n:
        cuts.append(n)
    cuts = sorted(set(cuts))
    for a, b in zip(cuts, cuts[1:]):
        piece = line[a:b]
        if len(piece.split()) <= MAX_WORDS_UNIT:
            _emit(piece, a, abs_start, out)
            continue
        sub = [0] + [m.end() for m in CLAUSE_END.finditer(piece)]
        if sub[-1] != len(piece):
            sub.append(len(piece))
        sub = sorted(set(sub))
        for sa, sb in zip(sub, sub[1:]):
            _emit(piece[sa:sb], a + sa, abs_start, out)
    return out


def segment_document(text: str) -> List[Dict]:
    """
    Tách `text` thành danh sách unit.

    Mỗi unit: {text, start, end, heading, zone, is_bullet}
      - heading : heading cha gần nhất phía trên (None nếu chưa gặp)
      - zone    : 'clinical' (trong khối bệnh án cấu trúc) | 'advice' (văn
                  xuôi tư vấn chung, trước mốc hoặc file không có mốc)

    Bất biến BẮT BUỘC: text[u['start']:u['end']] == u['text'] với MỌI unit.
    """
    cut = zone_cut(text)
    units: List[Dict] = []
    heading = None
    pos = 0

    for line in text.split('\n'):
        line_start = pos
        pos += len(line) + 1  # +1 bù cho '\n' đã cắt bởi split

        if _is_heading(line):
            heading = _clean_heading(line)
            continue

        m = BULLET.match(line)
        if m:
            body = m.group(3)
            if len(body) < MIN_UNIT_CHARS:
                continue
            s = line_start + m.start(3)
            e = line_start + m.end(3)
            zone = 'clinical' if (cut is not None and s >= cut) else 'advice'
            units.append({'text': body, 'start': s, 'end': e,
                          'heading': heading, 'zone': zone, 'is_bullet': True})
            continue

        if not line.strip():
            continue

        for u in _split_prose_line(line, line_start):
            u['heading'] = heading
            u['zone'] = 'clinical' if (cut is not None and u['start'] >= cut) else 'advice'
            u['is_bullet'] = False
            units.append(u)

    return units


def test_segment_units():
    """Test K1: bất biến offset, nhận heading, tách câu dài, gán zone."""
    failed = 0

    # 1) bullet nhận đúng heading cha
    text = "Triệu chứng hiện tại\n- đau bụng\n- sốt cao\n"
    units = segment_document(text)
    ok = (len(units) == 2 and all(u['heading'] == 'Triệu chứng hiện tại' for u in units)
          and units[0]['text'] == 'đau bụng' and units[1]['text'] == 'sốt cao')
    print(f"  {'✓' if ok else '✗'} bullet nhận heading cha -> {[(u['text'], u['heading']) for u in units]}")
    failed += not ok

    # 2) câu văn xuôi tách theo dấu chấm
    text2 = "Bệnh nhân đau đầu. Không sốt. Đã dùng paracetamol."
    units2 = segment_document(text2)
    texts2 = [u['text'] for u in units2]
    ok2 = texts2 == ['Bệnh nhân đau đầu.', 'Không sốt.', 'Đã dùng paracetamol.']
    print(f"  {'✓' if ok2 else '✗'} tách câu văn xuôi -> {texts2}")
    failed += not ok2

    # 3) câu dài (> MAX_WORDS_UNIT) tách tiếp theo dấu phẩy
    long_sent = ("Bệnh nhân được ghi nhận có tiền sử tăng huyết áp, đái tháo đường "
                 "type 2, rối loạn lipid máu, đã điều trị nhiều năm nay tại bệnh viện "
                 "tuyến trên, hiện đang dùng thuốc đều đặn theo toa, không bỏ thuốc.")
    units3 = segment_document(long_sent)
    ok3 = len(units3) > 1 and all(len(u['text'].split()) <= MAX_WORDS_UNIT for u in units3)
    print(f"  {'✓' if ok3 else '✗'} câu dài tách theo phẩy -> {len(units3)} mảnh")
    failed += not ok3

    # 4) zone: trước mốc '2.' là advice, từ đó là clinical
    text4 = ("Câu hỏi từ người dùng: em bị đau bụng.\n"
             "2.  Tiền sử bệnh hiện tại\n"
             "    - yếu tay phải\n")
    units4 = segment_document(text4)
    zmap = {u['text']: u['zone'] for u in units4}
    ok4 = zmap.get('yếu tay phải') == 'clinical' and any(
        v == 'advice' for k, v in zmap.items() if 'đau bụng' in k)
    print(f"  {'✓' if ok4 else '✗'} zone theo mốc '2. ...' -> {zmap}")
    failed += not ok4

    # 5) bất biến offset TRÊN CHÍNH VĂN BẢN THẬT (100 file, nếu có)
    import glob
    real_files = sorted(glob.glob('input/*.txt'))
    checked = 0
    for fp in real_files:
        with open(fp, encoding='utf-8') as f:
            t = f.read()
        for u in segment_document(t):
            if t[u['start']:u['end']] != u['text']:
                print(f"  ✗ LỆCH OFFSET tại {fp}: {u['text']!r} != {t[u['start']:u['end']]!r}")
                failed += 1
        checked += 1
    print(f"  {'✓' if checked else '(bỏ qua, không thấy input/*.txt)'} "
          f"bất biến offset trên {checked} file thật")

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"segment_units: {failed} ca THẤT BẠI")
    print(f"✓ segment_units: tất cả ca PASS ({checked} file thật đã kiểm)")


if __name__ == "__main__":
    test_segment_units()
