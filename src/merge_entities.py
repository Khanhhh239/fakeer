"""
K7 — Hợp nhất thực thể từ nhiều nguồn, dùng heading làm tín hiệu loại.

Bốn nguồn (mỗi nguồn góp 0..n thực thể, có thể chồng lấn nhau):
  rule    (K3, branch_b_lab_tests.extract_lab_pairs)  tất định, số+đơn vị.
  dict    (K4, branch_c_drugs.DrugMatcher)             khớp từ điển RxNorm.
  encoder (K5, encoder + cascade KB ICD)               F1 0.82, domain lệch.
  llm     (K2 + K6, span_anchor.verify_unit_entities)  nguồn chính, phủ rộng.

Nguyên lý (NL1, PIPELINE_V2.md §0, chứng minh bằng công thức WER của đề):
bỏ sót và trích thừa phạt NGANG NHAU; chỉ SAI LOẠI phạt gấp đôi (vừa thiếu
gold vừa thừa pred). Nên toàn bộ thận trọng dồn vào bước GIẢI XUNG ĐỘT LOẠI
khi hai nguồn cùng nhận một span nhưng khác type — không dồn vào việc có
trích hay không.

Cách giải xung đột (§6.3):
  1. rule/dict THẮNG TUYỆT ĐỐI — chặn bằng cấu trúc (loại đề xuất chồng lấn
     của nguồn khác), không để DP tự chọn theo điểm.
  2. encoder/llm cạnh tranh nhau qua DP (select_non_overlapping) trên điểm
     đã cộng/trừ theo heading prior — DP tự nhiên chọn type khớp heading vì
     nó có điểm cao hơn trên cùng khoảng chồng lấn.
"""

from collections import defaultdict
from typing import Callable, Dict, List, Optional

from utils.overlap_resolver import select_non_overlapping

SOURCE_WEIGHT = {
    'rule': 1.00, 'dict': 0.95, 'rule_strength': 0.85,
    'encoder+kb': 0.60, 'llm': 0.70,
}
ABSOLUTE_SOURCES = ('rule', 'dict', 'rule_strength')
HEADING_MATCH_BONUS = 0.15
HEADING_CONFLICT_PENALTY = 0.30
CONSENSUS_BONUS = 0.20

# heading -> loại nó khai báo cho các đơn vị bên dưới. Đây là NGỮ CẢNH TÀI
# LIỆU đo được trên dữ liệu thật (99% bullet có heading cha, xem NL2), không
# phải hard-code từ vựng thực thể — heading không tự trích xuất gì cả, nó
# chỉ nghiêng điểm khi có xung đột.
HEAD_PRIOR: List[tuple] = [
    (('bệnh lý mạn', 'bệnh lý mãn', 'bệnh mãn', 'bệnh mạn', 'chẩn đoán',
      'phát hiện chẩn đoán', 'kết quả chẩn đoán'), 'CHẨN_ĐOÁN'),
    (('triệu chứng', 'dấu hiệu lâm sàng', 'biểu hiện'), 'TRIỆU_CHỨNG'),
    (('thủ thuật', 'phẫu thuật'), 'TÊN_XÉT_NGHIỆM'),
    (('thuốc', 'điều trị'), 'THUỐC'),
]


def heading_prior_type(heading: Optional[str]) -> Optional[str]:
    if not heading:
        return None
    h = heading.lower()
    for keys, typ in HEAD_PRIOR:
        if any(k in h for k in keys):
            return typ
    return None


def _base_score(e: Dict) -> float:
    if 'score' in e and e['source'] not in SOURCE_WEIGHT:
        return float(e['score'])
    return SOURCE_WEIGHT.get(e.get('source'), 0.5)


def _apply_heading(pool: List[Dict]):
    for e in pool:
        prior = heading_prior_type(e.get('heading'))
        if prior:
            e['score'] += HEADING_MATCH_BONUS if e['type'] == prior else -HEADING_CONFLICT_PENALTY


def _apply_consensus(pool: List[Dict]):
    """+CONSENSUS_BONUS khi >=2 NGUỒN KHÁC NHAU đồng ý cùng type trên CÙNG span."""
    by_span = defaultdict(list)
    for e in pool:
        by_span[(e['start'], e['end'])].append(e)
    for group in by_span.values():
        if len(group) < 2:
            continue
        sources = {g['source'] for g in group}
        types = {g['type'] for g in group}
        if len(sources) >= 2 and len(types) == 1:
            for g in group:
                g['score'] += CONSENSUS_BONUS


def merge(rule_ents: List[Dict], dict_ents: List[Dict],
          encoder_ents: List[Dict], llm_ents: List[Dict]) -> List[Dict]:
    """
    Hợp nhất 4 nguồn cho MỘT văn bản, trả tập KHÔNG chồng lấn, sort theo start.

    Mỗi entity đầu vào cần tối thiểu: text, type, start, end. 'source' nên
    có sẵn (rule/dict/rule_strength/encoder+kb/llm); thiếu thì suy ra 0.5.
    llm_ents nên có thêm 'heading' (từ span_anchor.verify_unit_entities).
    """
    pool: List[Dict] = []
    for lst, default_src in ((rule_ents, 'rule'), (dict_ents, 'dict'),
                              (encoder_ents, 'encoder+kb'), (llm_ents, 'llm')):
        for e in lst:
            ne = dict(e)
            ne.setdefault('source', default_src)
            ne['score'] = _base_score(ne)
            pool.append(ne)

    _apply_heading(pool)
    _apply_consensus(pool)

    anchors = [(e['start'], e['end']) for e in pool if e['source'] in ABSOLUTE_SOURCES]

    def _hits_anchor(e):
        return any(e['start'] < b and a < e['end'] for a, b in anchors)

    absolute = [e for e in pool if e['source'] in ABSOLUTE_SOURCES]
    competing = [e for e in pool if e['source'] not in ABSOLUTE_SOURCES and not _hits_anchor(e)]

    merged = select_non_overlapping(absolute + competing)
    merged.sort(key=lambda x: x['start'])
    for e in merged:
        e['score'] = round(e['score'], 4)
    return merged


def test_merge_entities():
    failed = 0

    # 1) heading prior nghiêng đúng chiều khi encoder vs llm xung đột type
    #    trên CÙNG span, không có rule/dict can thiệp
    enc = [{'text': 'viêm dạ dày', 'type': 'TRIỆU_CHỨNG', 'start': 0, 'end': 11,
            'source': 'encoder+kb'}]
    llm = [{'text': 'viêm dạ dày', 'type': 'CHẨN_ĐOÁN', 'start': 0, 'end': 11,
            'source': 'llm', 'heading': 'Các bệnh lý mạn tính'}]
    out = merge([], [], enc, llm)
    ok = len(out) == 1 and out[0]['type'] == 'CHẨN_ĐOÁN'
    print(f"  {'✓' if ok else '✗'} heading prior thắng khi xung đột -> {[(o['type'], o['score']) for o in out]}")
    failed += not ok

    # 2) rule THẮNG TUYỆT ĐỐI dù llm đề xuất type khác trên span chồng lấn
    rule = [{'text': 'Ure', 'type': 'TÊN_XÉT_NGHIỆM', 'start': 0, 'end': 3, 'source': 'rule'}]
    llm2 = [{'text': 'Ure', 'type': 'THUỐC', 'start': 0, 'end': 3, 'source': 'llm', 'heading': None}]
    out2 = merge(rule, [], [], llm2)
    ok2 = len(out2) == 1 and out2[0]['type'] == 'TÊN_XÉT_NGHIỆM' and out2[0]['source'] == 'rule'
    print(f"  {'✓' if ok2 else '✗'} rule thắng tuyệt đối -> {out2[0]['type'] if out2 else None}")
    failed += not ok2

    # 3) không chồng lấn -> giữ CẢ HAI, không mất thực thể nào
    llm3 = [{'text': 'ho khan', 'type': 'TRIỆU_CHỨNG', 'start': 0, 'end': 7,
             'source': 'llm', 'heading': None},
            {'text': 'omeprazole', 'type': 'THUỐC', 'start': 20, 'end': 30,
             'source': 'llm', 'heading': None}]
    out3 = merge([], [], [], llm3)
    ok3 = len(out3) == 2
    print(f"  {'✓' if ok3 else '✗'} không chồng lấn giữ cả hai -> {len(out3)} thực thể")
    failed += not ok3

    # 4) consensus: DP chỉ giữ được MỘT trong hai span trùng nhau hệt nhau, nên
    #    phép thử đúng là so sánh ĐIỂM của người thắng giữa hai kịch bản: đồng ý
    #    type (được +0.20) vs không đồng ý (không được) — không phải kỳ vọng
    #    tổng hai điểm cộng lại, vì chúng không bao giờ cùng tồn tại sau DP.
    enc4 = [{'text': 'sỏi mật', 'type': 'CHẨN_ĐOÁN', 'start': 0, 'end': 7, 'source': 'encoder+kb'}]
    llm4_agree = [{'text': 'sỏi mật', 'type': 'CHẨN_ĐOÁN', 'start': 0, 'end': 7,
                   'source': 'llm', 'heading': None}]
    out4a = merge([], [], enc4, llm4_agree)
    # llm 0.70 + consensus 0.20 = 0.90 (thắng vì cao hơn encoder 0.60+0.20=0.80)
    ok4a = len(out4a) == 1 and abs(out4a[0]['score'] - 0.90) < 1e-6

    llm4_disagree = [{'text': 'sỏi mật', 'type': 'TRIỆU_CHỨNG', 'start': 0, 'end': 7,
                      'source': 'llm', 'heading': None}]
    out4b = merge([], [], enc4, llm4_disagree)
    # khác type -> KHÔNG có consensus -> llm giữ nguyên 0.70 (không +0.20)
    ok4b = len(out4b) == 1 and abs(out4b[0]['score'] - 0.70) < 1e-6

    ok4 = ok4a and ok4b
    print(f"  {'✓' if ok4 else '✗'} consensus (+0.20 khi đồng ý) -> đồng ý:{out4a[0]['score'] if out4a else None} "
          f"khác:{out4b[0]['score'] if out4b else None}")
    failed += not ok4

    # 5) heading_prior_type: không heading -> None, không áp bonus/penalty nào
    ok5 = heading_prior_type(None) is None and heading_prior_type('Tiền sử dị ứng') is None
    print(f"  {'✓' if ok5 else '✗'} heading không khớp danh mục nào -> None (không áp lực)")
    failed += not ok5

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"merge_entities: {failed} ca THẤT BẠI")
    print(f"✓ merge_entities: tất cả ca PASS")


if __name__ == "__main__":
    test_merge_entities()
