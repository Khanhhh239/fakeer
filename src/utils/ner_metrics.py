"""
F1 mức THỰC THỂ cho NER, chuẩn IOB2 strict — tự viết, không dùng seqeval.

Vì sao không dùng seqeval: gói này còn dùng `setup.py` kiểu cũ và hỏng ở bước
sinh metadata trên Python 3.12 của Kaggle:
    error: metadata-generation-failed
    × python setup.py egg_info did not run successfully
Cell cài đặt vẫn "chạy xong" nhưng import ở cell sau thì ném ModuleNotFoundError.
Một hàm 30 dòng đáng tin hơn một dependency vỡ.

Strict nghĩa là: một thực thể chỉ được tính đúng khi TRÙNG CẢ loại LẪN biên
(vị trí bắt đầu và kết thúc), giống cách đề chấm.
"""

from collections import defaultdict
from typing import Dict, List, Set, Tuple


def extract_entities(labels: List[str]) -> Set[Tuple[str, int, int]]:
    """
    Chuỗi nhãn BIO -> tập {(loại, đầu, cuối)}, cuối là chỉ số KHÔNG bao gồm.

    Xử lý cả chuỗi sai chuẩn: 'I-X' đứng đầu hoặc nối sau loại khác thì được
    coi là mở thực thể mới, thay vì bỏ im lặng.
    """
    ents, start, etype = set(), None, None

    def close(end: int):
        if etype is not None:
            ents.add((etype, start, end))

    for i, lab in enumerate(labels + ['O']):
        if lab.startswith('B-'):
            close(i)
            start, etype = i, lab[2:]
        elif lab.startswith('I-'):
            if etype != lab[2:]:          # I- lạc loài -> mở thực thể mới
                close(i)
                start, etype = i, lab[2:]
        else:                              # 'O' hoặc nhãn lạ
            close(i)
            start, etype = None, None
    return ents


def entity_f1(y_true: List[List[str]], y_pred: List[List[str]]) -> Dict:
    """
    -> {'micro': {...}, 'per_label': {loại: {...}}}
    Mỗi mục có precision / recall / f1 / support / tp / fp / fn.
    """
    assert len(y_true) == len(y_pred), "số câu vàng và câu dự đoán không khớp"

    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)

    for gold_seq, pred_seq in zip(y_true, y_pred):
        gold = extract_entities(gold_seq)
        pred = extract_entities(pred_seq)
        for e in pred & gold:
            tp[e[0]] += 1
        for e in pred - gold:
            fp[e[0]] += 1
        for e in gold - pred:
            fn[e[0]] += 1

    def prf(t: int, p: int, n: int) -> Dict:
        prec = t / (t + p) if t + p else 0.0
        rec = t / (t + n) if t + n else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return {'precision': prec, 'recall': rec, 'f1': f1,
                'support': t + n, 'tp': t, 'fp': p, 'fn': n}

    labels = set(tp) | set(fp) | set(fn)
    per_label = {l: prf(tp[l], fp[l], fn[l]) for l in sorted(labels)}
    micro = prf(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    return {'micro': micro, 'per_label': per_label}


def format_report(res: Dict) -> str:
    """In bảng giống classification_report của seqeval."""
    lines = [f"{'':>14} {'prec':>8} {'recall':>8} {'f1':>8} {'support':>8}"]
    for lab, m in res['per_label'].items():
        lines.append(f"{lab:>14} {m['precision']:8.4f} {m['recall']:8.4f} "
                     f"{m['f1']:8.4f} {m['support']:8d}")
    m = res['micro']
    lines.append(f"{'micro avg':>14} {m['precision']:8.4f} {m['recall']:8.4f} "
                 f"{m['f1']:8.4f} {m['support']:8d}")
    return "\n".join(lines)


def test_ner_metrics():
    """Ca kiểm có đáp án tính tay — không thể pass rỗng."""
    # 1. khớp hoàn toàn
    y = [['B-A', 'I-A', 'O', 'B-A']]
    assert entity_f1(y, y)['micro']['f1'] == 1.0, "khớp hoàn toàn phải F1=1"

    # 2. sai biên -> KHÔNG được tính đúng (strict)
    gold = [['B-A', 'I-A', 'O']]
    pred = [['B-A', 'O',   'O']]
    r = entity_f1(gold, pred)
    assert r['micro']['tp'] == 0, f"sai biên vẫn tính đúng: {r['micro']}"

    # 3. đúng biên nhưng sai loại -> vừa fp vừa fn
    gold = [['B-A', 'I-A']]
    pred = [['B-B', 'I-B']]
    r = entity_f1(gold, pred)
    assert r['micro']['tp'] == 0 and r['micro']['fp'] == 1 and r['micro']['fn'] == 1

    # 4. đếm đúng khi có nhiều thực thể
    gold = [['B-A', 'O', 'B-A', 'I-A', 'O', 'B-B']]
    pred = [['B-A', 'O', 'B-A', 'O',   'O', 'B-B']]
    r = entity_f1(gold, pred)
    assert r['micro']['tp'] == 2 and r['micro']['fn'] == 1 and r['micro']['fp'] == 1
    assert r['per_label']['A']['tp'] == 1 and r['per_label']['B']['tp'] == 1

    # 5. 'I-' đứng đầu vẫn được coi là một thực thể
    assert extract_entities(['I-A', 'I-A']) == {('A', 0, 2)}

    # 6. hai thực thể liền nhau cùng loại phải TÁCH, không dính làm một
    assert extract_entities(['B-A', 'B-A']) == {('A', 0, 1), ('A', 1, 2)}

    # 7. không có gì -> F1 = 0, không chia cho 0
    r = entity_f1([['O', 'O']], [['O', 'O']])
    assert r['micro']['f1'] == 0.0 and r['micro']['support'] == 0

    print("✓ ner_metrics: 7/7 ca PASS")


if __name__ == "__main__":
    test_ner_metrics()
    demo = entity_f1(
        [['B-SYM_DIS', 'I-SYM_DIS', 'O', 'B-SYM_DIS']],
        [['B-SYM_DIS', 'I-SYM_DIS', 'O', 'O']],
    )
    print()
    print(format_report(demo))
