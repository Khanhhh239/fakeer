"""
Sinh CA KHÓ cho dữ liệu huấn luyện: nhiễu văn bản + mồi âm.

Bốn loại ca khó, theo yêu cầu:
  1. DÍNH TỪ      — mô phỏng lỗi gõ có thật trong đề thi (`bệnh dạithường`)
  2. CHÈN ***     — mô phỏng phần bị che/mất trong đề thi (`Kháng sinh nhóm ***`)
  3. THUỐC GIẢ    — chuỗi trông như thuốc nhưng KHÔNG phải (`thuốc trừ sâu`)
  4. XÉT NGHIỆM GIẢ — thủ thuật/điều trị/ảnh học, KHÔNG phải xét nghiệm

BẤT BIẾN SỐNG CÒN: nhiễu chỉ được rơi NGOÀI span thực thể, và mọi thay đổi
độ dài phải dịch lại offset của các span phía sau. Sai chỗ này thì toàn bộ
nhãn hỏng mà không có gì báo.

Mồi âm (3, 4) được chèn như văn bản bình thường và CỐ Ý KHÔNG gán nhãn —
đó chính là tín hiệu dạy model "cụm này không phải thực thể".
"""

import random
import re
from typing import Dict, List, Optional, Tuple

# `Kháng sinh nhóm ***********, ********` — có thật trong input/1.txt của đề thi
MASK_CHARS = ['***', '****', '*****', '***********', '########', '____']

# Lỗi gõ có thật đã quan sát trong đề thi: `bệnh dạithường`, `điên dạiở`,
# `địnhkhai`, `chụp chụp ct sọ não`. KHÔNG mô phỏng hoán vị ký tự trong từ
# (`Khho anội`) — dạng đó không tồn tại trong đề thi, học vào chỉ tổ hại.
NOISE_KINDS = ('glue', 'mask', 'dup_word', 'no_space_punct')


def _covered(pos: int, spans: List[Tuple[int, int]]) -> bool:
    """pos có nằm trong (hoặc sát biên) một span thực thể nào không."""
    return any(a - 1 <= pos <= b + 1 for a, b in spans)


def _shift(entities: List[Dict], at: int, delta: int) -> None:
    """Dịch offset MỌI span nằm sau vị trí `at`. Bỏ bước này = hỏng toàn bộ nhãn."""
    for e in entities:
        if e['position'][0] >= at:
            e['position'][0] += delta
            e['position'][1] += delta


def _safe_gaps(text: str, entities: List[Dict], min_len: int = 12) -> List[Tuple[int, int]]:
    """Các khoảng TRỐNG giữa các span thực thể — chỉ được chèn nhiễu vào đây."""
    spans = sorted((e['position'][0], e['position'][1]) for e in entities)
    gaps, cur = [], 0
    for a, b in spans:
        if a - cur >= min_len:
            gaps.append((cur, a))
        cur = max(cur, b)
    if len(text) - cur >= min_len:
        gaps.append((cur, len(text)))
    return gaps


def inject_text_noise(text: str, entities: List[Dict], rate: float = 0.03,
                      rng: Optional[random.Random] = None) -> Tuple[str, List[Dict]]:
    """
    Chèn nhiễu gõ vào `text`, dịch offset `entities` tương ứng.

    `rate` = tỷ lệ trên số TỪ nằm ngoài span (0.03 = 3%).
    Trả (text mới, entities đã dịch offset). entities bị sửa TẠI CHỖ.
    """
    rng = rng or random.Random()
    ents = [dict(e, position=list(e['position'])) for e in entities]

    for _ in range(max(1, int(len(text.split()) * rate))):
        spans = [(e['position'][0], e['position'][1]) for e in ents]
        gaps = _safe_gaps(text, ents)
        if not gaps:
            break
        ga, gb = rng.choice(gaps)
        kind = rng.choice(NOISE_KINDS)
        seg = text[ga:gb]

        if kind == 'glue':
            # `bệnh dại` + `thường` -> `bệnh dạithường` (mất 1 dấu cách)
            hits = [m.start() for m in re.finditer(r'(?<=\w) (?=\w)', seg)]
            hits = [h for h in hits if not _covered(ga + h, spans)]
            if not hits:
                continue
            i = ga + rng.choice(hits)
            text = text[:i] + text[i + 1:]
            _shift(ents, i, -1)

        elif kind == 'mask':
            # `Kháng sinh nhóm ***********` — thay 1 từ bằng dấu che
            hits = [m for m in re.finditer(r'\b\w{4,}\b', seg)]
            hits = [m for m in hits if not _covered(ga + m.start(), spans)
                    and not _covered(ga + m.end(), spans)]
            if not hits:
                continue
            m = rng.choice(hits)
            mask = rng.choice(MASK_CHARS)
            i, j = ga + m.start(), ga + m.end()
            text = text[:i] + mask + text[j:]
            _shift(ents, j, len(mask) - (j - i))

        elif kind == 'dup_word':
            # `chụp chụp ct sọ não` — có thật trong input/3.txt
            hits = [m for m in re.finditer(r'\b\w{3,}\b', seg)]
            hits = [m for m in hits if not _covered(ga + m.start(), spans)]
            if not hits:
                continue
            m = rng.choice(hits)
            w = m.group()
            i = ga + m.start()
            text = text[:i] + w + ' ' + text[i:]
            _shift(ents, i, len(w) + 1)

        else:  # no_space_punct — `viêm dạ dày.Bệnh nhân`
            hits = [m.start() for m in re.finditer(r'(?<=[.,;:]) (?=\w)', seg)]
            hits = [h for h in hits if not _covered(ga + h, spans)]
            if not hits:
                continue
            i = ga + rng.choice(hits)
            text = text[:i] + text[i + 1:]
            _shift(ents, i, -1)

    return text, ents


def inject_negative_bait(text: str, entities: List[Dict], baits: List[str],
                         n: int = 2, rng: Optional[random.Random] = None
                         ) -> Tuple[str, List[Dict]]:
    """
    Chèn `n` mồi âm (thuốc giả / xét nghiệm giả) vào chỗ trống, CỐ Ý KHÔNG gán nhãn.

    Đây là tín hiệu dạy model: cụm này trông giống thực thể nhưng KHÔNG phải.
    Chèn ở ranh giới câu để văn không vỡ.
    """
    rng = rng or random.Random()
    ents = [dict(e, position=list(e['position'])) for e in entities]

    # khuôn câu để mồi âm nằm tự nhiên, không lơ lửng giữa dòng
    FRAMES = [
        'Người bệnh cũng hỏi về {}. ',
        'Trước đó có dùng {}. ',
        'Gia đình có nhắc tới {}. ',
        'Không liên quan tới {}. ',
        'Cần phân biệt với {}. ',
    ]

    for _ in range(n):
        if not baits:
            break
        gaps = _safe_gaps(text, ents, min_len=2)
        # ưu tiên chèn ngay sau dấu chấm câu trong vùng trống
        cands = []
        for ga, gb in gaps:
            for m in re.finditer(r'(?<=[.!?]) ', text[ga:gb]):
                cands.append(ga + m.end())
        if not cands:
            continue
        i = rng.choice(cands)
        s = rng.choice(FRAMES).format(rng.choice(baits))
        text = text[:i] + s + text[i:]
        _shift(ents, i, len(s))

    return text, ents


def validate(text: str, entities: List[Dict]) -> None:
    """Bất biến bắt buộc sau mọi thao tác nhiễu. Sai -> dừng ngay, không ghi file."""
    for e in entities:
        a, b = e['position']
        assert text[a:b] == e['text'], \
            f"nhiễu làm hỏng nhãn: {e['text']!r} != {text[a:b]!r} @ {a}"
    o = sorted(entities, key=lambda x: x['position'][0])
    for x, y in zip(o, o[1:]):
        assert x['position'][1] <= y['position'][0], f"chồng lấn: {x} và {y}"


# --------------------------------------------------------------------------
# TEST
# --------------------------------------------------------------------------

def test_synth_noise():
    failed = 0
    rng = random.Random(0)

    base = ('Bệnh nhân nam 45 tuổi vào viện vì đau bụng vùng thượng vị nhiều ngày. '
            'Khám thấy bụng mềm, không phản ứng thành bụng rõ ràng. '
            'Chẩn đoán viêm dạ dày và cho dùng omeprazole mỗi sáng. '
            'Sau một tuần điều trị tình trạng cải thiện tốt hơn trước.')
    ents = []
    for t, ty in [('đau bụng vùng thượng vị', 'TRIỆU_CHỨNG'),
                  ('viêm dạ dày', 'CHẨN_ĐOÁN'),
                  ('omeprazole', 'THUỐC')]:
        i = base.index(t)
        ents.append({'text': t, 'type': ty, 'position': [i, i + len(t)]})

    # 1) nhiễu gõ KHÔNG được phá nhãn, qua nhiều seed
    bad = 0
    for seed in range(40):
        t2, e2 = inject_text_noise(base, ents, rate=0.10, rng=random.Random(seed))
        try:
            validate(t2, e2)
        except AssertionError:
            bad += 1
    ok = bad == 0
    print(f"  {'✓' if ok else '✗'} nhiễu gõ giữ nguyên nhãn qua 40 seed (hỏng: {bad})")
    failed += not ok

    # 2) nhiễu PHẢI thật sự đổi văn bản
    t3, e3 = inject_text_noise(base, ents, rate=0.15, rng=random.Random(7))
    ok = t3 != base
    print(f"  {'✓' if ok else '✗'} nhiễu có tác dụng (độ dài {len(base)} -> {len(t3)})")
    failed += not ok

    # 3) mồi âm chèn được, KHÔNG được gán nhãn, nhãn cũ vẫn đúng
    baits = ['thuốc trừ sâu', 'phẫu thuật nội soi']
    t4, e4 = inject_negative_bait(base, ents, baits, n=2, rng=random.Random(3))
    try:
        validate(t4, e4)
        has_bait = any(b in t4 for b in baits)
        no_label = all(e['type'] in ('TRIỆU_CHỨNG', 'CHẨN_ĐOÁN', 'THUỐC') for e in e4)
        ok = has_bait and len(e4) == 3 and no_label
    except AssertionError as ex:
        ok = False
        print('     ', ex)
    print(f"  {'✓' if ok else '✗'} mồi âm chèn vào, không gán nhãn (nhãn vẫn {len(e4)})")
    failed += not ok

    # 4) ghép cả hai: mồi âm rồi nhiễu gõ — vẫn phải giữ bất biến
    bad2 = 0
    for seed in range(30):
        r = random.Random(seed)
        ta, ea = inject_negative_bait(base, ents, baits, n=2, rng=r)
        tb, eb = inject_text_noise(ta, ea, rate=0.10, rng=r)
        try:
            validate(tb, eb)
        except AssertionError:
            bad2 += 1
    ok = bad2 == 0
    print(f"  {'✓' if ok else '✗'} mồi âm + nhiễu gõ chồng nhau qua 30 seed (hỏng: {bad2})")
    failed += not ok

    # 5) span sát biên văn bản không bị nhiễu ăn mất
    edge = 'đau đầu nhiều ngày nay không rõ nguyên nhân gì cả'
    e5 = [{'text': 'đau đầu', 'type': 'TRIỆU_CHỨNG', 'position': [0, 7]}]
    bad3 = 0
    for seed in range(30):
        t6, e6 = inject_text_noise(edge, e5, rate=0.2, rng=random.Random(seed))
        try:
            validate(t6, e6)
        except AssertionError:
            bad3 += 1
    ok = bad3 == 0
    print(f"  {'✓' if ok else '✗'} span ở đầu văn bản an toàn qua 30 seed (hỏng: {bad3})")
    failed += not ok

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"synth_noise: {failed} ca THẤT BẠI")
    print("✓ synth_noise: tất cả ca PASS")


if __name__ == '__main__':
    test_synth_noise()
