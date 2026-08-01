"""
K8 — Hậu xử lý cuối: chuẩn biên, mở rộng span cụt bằng KB, xuất format BTC.

Format BTC (xác nhận qua bài nộp thật, 19.07 điểm — không lỗi schema):
mỗi file là MỘT MẢNG PHẲNG các thực thể, không bọc {"text":..,"entities":..}.
Mỗi phần tử: text / type / candidates / assertions / position=[start,end].
candidates + assertions để RỖNG — vòng nộp thử chỉ chấm text_score (NER).
"""

import csv
import json
import os
import unicodedata as ud
from typing import Dict, List, Optional, Set

EDGE_STRIP = ' \t.,;:!?()[]{}"\'-–—•·*”“’‘'


def clean_boundary(text: str, start: int, end: int) -> Optional[tuple]:
    """Cắt ký tự rác ở hai biên (bullet/dấu câu sót lại). Trả None nếu
    sau khi cắt không còn gì (toàn bộ span là rác biên)."""
    s = text[start:end]
    lead = len(s) - len(s.lstrip(EDGE_STRIP))
    trail = len(s) - len(s.rstrip(EDGE_STRIP))
    ns, ne = start + lead, end - trail
    if ns >= ne:
        return None
    return ns, ne


def _norm(s: str) -> str:
    s = ud.normalize('NFC', s).lower().strip()
    return ' '.join(s.split())


def load_name_set(csv_path: str, col: str = 'term') -> Set[str]:
    with open(csv_path, encoding='utf-8') as f:
        return {_norm(r[col]) for r in csv.DictReader(f) if r.get(col)}


def expand_diagnosis_spans(entities: List[Dict], text: str, name_set: Set[str],
                            types=('CHẨN_ĐOÁN',)) -> int:
    """
    Mở rộng span CỤT bằng KB tên bệnh (ICD), 2 chiều — encoder/LLM đôi khi
    cắt cụt ('sỏi' thay vì 'sỏi đoạn cuối ống mật chủ', 'thận hư' thay vì
    'Hội chứng thận hư'). Span cụt mất điểm HAI lần: sai WER ở text_score,
    tra ID sai ở candidate-linking. KHÔNG cần train lại: thử nối thêm 1-4
    từ liền kề, nhận nếu bản DÀI khớp CHÍNH XÁC một tên trong `name_set` mà
    bản ngắn không khớp. Sửa entities TẠI CHỖ, trả số span đã mở rộng.
    """
    occupied = [(e['start'], e['end']) for e in entities]

    def _better(short, start, end):
        if _norm(short) in name_set:
            return None
        # cửa sổ 90 ký tự / tối đa 8 từ thêm — đủ cho tên dài thật gặp trong
        # dữ liệu ("sỏi" -> "sỏi đoạn cuối ống mật chủ" cần nối 5 từ; bản đầu
        # chỉ thử tới 4 từ nên bỏ sót đúng ca thật này, đã sửa ở đây).
        tail = text[end:end + 90]
        words = tail.split()
        for n in range(1, min(9, len(words) + 1)):
            cand_end = end + tail.find(words[n - 1]) + len(words[n - 1])
            cand = text[start:cand_end]
            if len(cand.split()) > 8:
                break
            if _norm(cand) in name_set:
                return start, cand_end
        head = text[max(0, start - 90):start]
        wh = head.split()
        for n in range(1, min(9, len(wh) + 1)):
            s2 = max(0, start - 90) + head.rfind(' '.join(wh[-n:]))
            cand = text[s2:end]
            if len(cand.split()) > 8:
                break
            if _norm(cand) in name_set:
                return s2, end
        return None

    n_expanded = 0
    for e in entities:
        if e['type'] not in types:
            continue
        hit = _better(e['text'], e['start'], e['end'])
        if not hit:
            continue
        ns, ne = hit
        if ns >= e['start'] and ne <= e['end']:
            continue
        if any((a, b) != (e['start'], e['end']) and ns < b and a < ne for a, b in occupied):
            continue  # không được đè lên thực thể khác
        e['start'], e['end'], e['text'] = ns, ne, text[ns:ne]
        n_expanded += 1
    return n_expanded


def to_btc_format(entities: List[Dict]) -> List[Dict]:
    """Mảng phẳng đúng schema BTC — candidates/assertions rỗng có chủ đích."""
    ordered = sorted(entities, key=lambda e: e['start'])
    return [{'text': e['text'], 'type': e['type'], 'candidates': [],
             'assertions': [], 'position': [e['start'], e['end']]} for e in ordered]


def validate(text: str, entities: List[Dict]):
    """Hai bất biến bắt buộc trước khi ghi file: nguyên văn + không chồng lấn."""
    ordered = sorted(entities, key=lambda e: e['start'])
    for e in ordered:
        assert text[e['start']:e['end']] == e['text'], \
            f"lệch nguyên văn: {e['text']!r} != {text[e['start']:e['end']]!r}"
    for a, b in zip(ordered, ordered[1:]):
        assert a['end'] <= b['start'], f"chồng lấn: {a} và {b}"


def finalize_document(text: str, entities: List[Dict],
                       name_set: Optional[Set[str]] = None) -> List[Dict]:
    """Toàn bộ K8 cho MỘT văn bản: chuẩn biên -> mở rộng KB -> validate."""
    cleaned = []
    for e in entities:
        hit = clean_boundary(text, e['start'], e['end'])
        if not hit:
            continue
        ns, ne = hit
        ne2 = dict(e, start=ns, end=ne, text=text[ns:ne])
        cleaned.append(ne2)
    if name_set:
        expand_diagnosis_spans(cleaned, text, name_set)
    validate(text, cleaned)
    return cleaned


def write_submission(final_dir: str, submit_dir: str) -> Dict:
    """Đọc {'text','entities'} từ final_dir/*.json, ghi mảng phẳng BTC vào
    submit_dir/*.json. Trả thống kê tổng quát để in log."""
    os.makedirs(submit_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(final_dir) if f.endswith('.json'))
    from collections import Counter
    cnt, n = Counter(), 0
    for fn in files:
        d = json.load(open(os.path.join(final_dir, fn), encoding='utf-8'))
        validate(d['text'], d['entities'])
        out = to_btc_format(d['entities'])
        json.dump(out, open(os.path.join(submit_dir, fn), 'w', encoding='utf-8'),
                   ensure_ascii=False, indent=2)
        cnt.update(e['type'] for e in out)
        n += len(out)
    return {'n_files': len(files), 'n_entities': n, 'by_type': dict(cnt)}


def test_export_btc():
    failed = 0

    # 1) clean_boundary cắt bullet/dấu câu sót ở biên
    text = "- ALT: 45 U/l."
    hit = clean_boundary(text, 0, len(text))
    ok1 = hit and text[hit[0]:hit[1]] == 'ALT: 45 U/l'
    print(f"  {'✓' if ok1 else '✗'} clean_boundary cắt biên -> {text[hit[0]:hit[1]] if hit else None!r}")
    failed += not ok1

    # 2) clean_boundary: toàn bộ là rác biên -> None
    ok2 = clean_boundary("- • ", 0, 4) is None
    print(f"  {'✓' if ok2 else '✗'} clean_boundary toàn rác -> None")
    failed += not ok2

    # 3) expand_diagnosis_spans nối span cụt khớp KB
    text3 = "Chụp cộng hưởng từ ghi nhận sỏi đoạn cuối ống mật chủ rõ."
    ents3 = [{'text': 'sỏi', 'type': 'CHẨN_ĐOÁN',
              'start': text3.index('sỏi'), 'end': text3.index('sỏi') + 3}]
    names = {_norm('sỏi đoạn cuối ống mật chủ')}
    n = expand_diagnosis_spans(ents3, text3, names)
    ok3 = n == 1 and ents3[0]['text'] == 'sỏi đoạn cuối ống mật chủ'
    print(f"  {'✓' if ok3 else '✗'} mở rộng span cụt bằng KB -> {ents3[0]['text']!r}")
    failed += not ok3

    # 4) expand_diagnosis_spans KHÔNG đè lên thực thể liền kề
    text4 = "sỏi mật gây đau, sốt cao kéo dài"
    s_start = 0
    ents4 = [{'text': 'sỏi', 'type': 'CHẨN_ĐOÁN', 'start': 0, 'end': 3},
             {'text': 'sốt cao', 'type': 'TRIỆU_CHỨNG', 'start': 17, 'end': 24}]
    names4 = {_norm('sỏi mật gây đau sốt')}   # cố tình đè qua thực thể kế bên
    n4 = expand_diagnosis_spans(ents4, text4, names4)
    ok4 = ents4[1]['text'] == 'sốt cao'   # thực thể kế bên phải nguyên vẹn
    print(f"  {'✓' if ok4 else '✗'} không đè lên thực thể liền kề -> {ents4[1]['text']!r}")
    failed += not ok4

    # 5) to_btc_format đúng schema, candidates/assertions rỗng, position=[s,e]
    out5 = to_btc_format([{'text': 'sốt', 'type': 'TRIỆU_CHỨNG', 'start': 5, 'end': 8,
                           'score': 0.9, 'source': 'llm'}])
    ok5 = out5 == [{'text': 'sốt', 'type': 'TRIỆU_CHỨNG', 'candidates': [],
                    'assertions': [], 'position': [5, 8]}]
    print(f"  {'✓' if ok5 else '✗'} to_btc_format đúng schema -> {out5}")
    failed += not ok5

    # 6) validate bắt được chồng lấn và lệch nguyên văn
    try:
        validate("abc", [{'text': 'ab', 'start': 0, 'end': 2},
                          {'text': 'bc', 'start': 1, 'end': 3}])
        ok6 = False
    except AssertionError:
        ok6 = True
    print(f"  {'✓' if ok6 else '✗'} validate bắt chồng lấn")
    failed += not ok6

    # 7) finalize_document: toàn bộ K8 trên 1 văn bản, đầu ra sạch bullet + validate qua
    text7 = "- gan nhiễm mỡ độ 2"
    ents7 = [{'text': '- gan nhiễm mỡ độ 2', 'type': 'CHẨN_ĐOÁN', 'start': 0, 'end': len(text7)}]
    out7 = finalize_document(text7, ents7)
    ok7 = len(out7) == 1 and out7[0]['text'] == 'gan nhiễm mỡ độ 2'
    print(f"  {'✓' if ok7 else '✗'} finalize_document cắt bullet cuối cùng -> {out7[0]['text']!r}")
    failed += not ok7

    # 8) write_submission end-to-end trên thư mục tạm
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        fdir = os.path.join(tmp, 'final'); os.makedirs(fdir)
        sdir = os.path.join(tmp, 'submit')
        doc_text = "Bệnh nhân sốt cao, ho khan."
        json.dump({'text': doc_text, 'entities': [
            {'text': 'sốt cao', 'type': 'TRIỆU_CHỨNG', 'start': 10, 'end': 17},
            {'text': 'ho khan', 'type': 'TRIỆU_CHỨNG', 'start': 19, 'end': 26},
        ]}, open(os.path.join(fdir, '1.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        stats = write_submission(fdir, sdir)
        written = json.load(open(os.path.join(sdir, '1.json'), encoding='utf-8'))
        ok8 = (stats['n_files'] == 1 and stats['n_entities'] == 2
               and written[0]['candidates'] == [] and written[0]['position'] == [10, 17])
        print(f"  {'✓' if ok8 else '✗'} write_submission end-to-end -> {stats}")
        failed += not ok8
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"export_btc: {failed} ca THẤT BẠI")
    print(f"✓ export_btc: tất cả ca PASS")


if __name__ == "__main__":
    test_export_btc()
