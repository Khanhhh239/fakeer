"""
K2 — LLM sinh thực thể theo từng unit (NGUỒN CHÍNH của pipeline V2).

Khác căn bản với V1: V1 dùng LLM để CHỌN giữa các lựa chọn cố định
(choice-classification) trên ứng viên do luật sinh trước — nên thứ luật
không hề biết tới (siêu âm tim, nội soi dạ dày...) không bao giờ tới tay
LLM. V2 để LLM ĐỌC VÀ TỰ LIỆT KÊ thực thể trên từng unit — không có khái
niệm "vùng mờ" nữa, mọi unit đều được hỏi.

An toàn không đến từ việc giới hạn LLM chọn gì (như V1), mà từ việc KHÔNG
BAO GIỜ tin trực tiếp text nó sinh ra — mọi span đều phải đi qua
`span_anchor.verify_unit_entities` (K6) để neo về văn bản gốc trước khi
được công nhận là một thực thể thật.

Module này CHỈ phụ thuộc `vllm` bên trong `extract_all()` — mọi thứ khác
(prompt, parse) test được trên máy không có GPU/vllm.
"""

import re
from typing import Callable, Dict, List, Optional, Tuple

CODE2TYPE = {
    'TC': 'TRIỆU_CHỨNG',
    'CD': 'CHẨN_ĐOÁN',
    'TH': 'THUỐC',
    'TX': 'TÊN_XÉT_NGHIỆM',
    'KQ': 'KẾT_QUẢ_XÉT_NGHIỆM',
}

SYSTEM_PROMPT = """Bạn là bác sĩ trích xuất thông tin từ bệnh án tiếng Việt.
Liệt kê thực thể y khoa trong ĐOẠN được cho, dùng đúng 5 mã sau:

TC = TRIỆU_CHỨNG   biểu hiện bệnh nhân khai / bác sĩ quan sát
                   (sốt, khó thở, yếu nửa người, lưỡi đỏ như dâu tây)
CD = CHẨN_ĐOÁN     tên bệnh, hội chứng
                   (viêm dạ dày, hội chứng thận hư, tai biến mạch máu não)
TH = THUỐC         tên thuốc, nhóm thuốc
                   (omeprazole, kháng sinh, thuốc giảm đau opioid)
TX = TÊN_XÉT_NGHIỆM  tên xét nghiệm / thăm dò / thủ thuật chẩn đoán
                   (công thức máu, CRP, siêu âm tim, nội soi dạ dày, chụp CT)
KQ = KẾT_QUẢ_XÉT_NGHIỆM  giá trị hoặc kết luận của xét nghiệm
                   (6,4 mmol/l, âm tính, men gan tăng, 92 g/L)

QUY TẮC:
1. COPY NGUYÊN VĂN từ đoạn — không sửa chữ, không đổi dấu, không diễn giải.
2. Lấy cụm NGẮN NHẤT mà vẫn đủ nghĩa y khoa. TUYỆT ĐỐI KHÔNG lấy cả câu,
   cả mệnh đề, cả dòng. Chỉ lấy phần TÊN của khái niệm, bỏ hết phần mô tả
   hoàn cảnh, thời điểm, nguyên nhân, diễn biến bao quanh nó.
   Hầu hết thực thể dài 1-4 từ. Nếu cụm bạn định lấy dài quá 8 từ thì gần
   như chắc chắn bạn đang lấy cả câu — hãy rút lại còn phần lõi.
3. Bỏ qua: thời gian, tuổi, tên người, lời khuyên, câu hỏi, "Không ghi rõ".
4. "Mục:" cho biết loại thường gặp trong đoạn — dùng làm GỢI Ý, không phải
   luật cứng; nếu nội dung thật sự thuộc loại khác thì cứ gán loại đúng.

Mỗi thực thể một dòng, đúng dạng:  MÃ|nguyên văn
Không có thực thể nào thì trả về đúng một dòng: KHÔNG"""

# Few-shot: mỗi cặp PHẢI cùng độ hạt (một unit = một bullet/câu) với dữ liệu
# thật để không dạy model gộp nhiều dòng — và LUÔN có ít nhất một ví dụ
# KHÔNG, nếu không model sẽ cố sinh ra thứ gì đó cho mọi đoạn (bài học từ
# lỗi kinh điển của few-shot toàn ví dụ dương).
#
# ĐO ĐƯỢC (bài nộp V2 đầu tiên): bản prompt trước bảo "lấy cụm ĐẦY ĐỦ NHẤT"
# khiến model nuốt trọn cả bullet — số TỪ tăng 94% (5539 -> 10738) trong khi
# số thực thể chỉ tăng 19%, WER xấu đi 63.6 -> 72.7. WER tính trên TỪ nên một
# span 27 từ sai làm hỏng điểm gấp nhiều lần một span 3 từ sai. Vì vậy 3
# ví dụ cuối dạy THẲNG việc rút lõi ra khỏi câu dài — đó mới là ca khó, không
# phải ca bullet vốn đã ngắn sẵn.
FEWSHOT: List[Tuple[str, str]] = [
    ("Mục: Kết quả xét nghiệm\nĐoạn: Công thức máu, CRP, máu lắng",
     "TX|Công thức máu\nTX|CRP\nTX|máu lắng"),
    ("Mục: Triệu chứng hiện tại\nĐoạn: đau bụng vùng hạ sườn phải",
     "TC|đau bụng vùng hạ sườn phải"),
    ("Mục: None\nĐoạn: Cảm ơn bác sĩ đã tư vấn cho em.",
     "KHÔNG"),
    # rút lõi khỏi câu dài: bỏ "Chụp kiểm tra ghi nhận", giữ đúng tên bệnh
    ("Mục: Diễn biến bệnh\nĐoạn: Chụp kiểm tra ghi nhận tụ máu ngoài màng cứng "
     "phải cấp tính trên nền tổn thương mạn tính",
     "CD|tụ máu ngoài màng cứng phải cấp tính"),
    # bỏ hoàn cảnh "khi gắng sức trong tuần qua", giữ đúng triệu chứng
    ("Mục: Triệu chứng hiện tại\nĐoạn: Cảm thấy mệt mỏi nhiều khi gắng sức trong tuần qua",
     "TC|mệt mỏi"),
    ("Mục: Kết quả xét nghiệm\nĐoạn: Xét nghiệm chức năng gan cho thấy men gan tăng",
     "TX|Xét nghiệm chức năng gan\nKQ|men gan tăng"),
]

CODE_LINE = re.compile(r'^\s*(?:\d+[.):]\s*)?([A-Za-zÀ-ỹ]{2})\s*[|:]\s*(.+?)\s*$')
NONE_LINE = re.compile(r'^\s*KH[ÔO]NG\s*\.?\s*$', re.I)


def build_prompt(unit: Dict) -> str:
    head = unit.get('heading') or 'None'
    return f"Mục: {head}\nĐoạn: {unit['text']}"


def _messages(unit: Dict) -> List[Dict]:
    msgs = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for u, a in FEWSHOT:
        msgs.append({'role': 'user', 'content': u})
        msgs.append({'role': 'assistant', 'content': a})
    msgs.append({'role': 'user', 'content': build_prompt(unit)})
    return msgs


def build_chat_prompts(units: List[Dict], tokenizer) -> List[str]:
    """`tokenizer` chỉ cần có .apply_chat_template — không cần vllm để test."""
    return [tokenizer.apply_chat_template(
        _messages(u), tokenize=False, add_generation_prompt=True,
        enable_thinking=False) for u in units]


def parse_response(raw: str) -> List[Tuple[str, str]]:
    """
    Phân giải output LLM thành [(code, text), ...].

    Khoan dung với sai lệch định dạng nhỏ (số thứ tự đầu dòng, mã viết
    thường, dùng ':' thay '|') nhưng KHÔNG suy diễn nội dung — dòng không
    khớp mẫu bị bỏ qua thay vì đoán.
    """
    out = []
    for line in (raw or '').split('\n'):
        line = line.strip()
        if not line or NONE_LINE.match(line):
            continue
        m = CODE_LINE.match(line)
        if not m:
            continue
        code, text = m.group(1).upper(), m.group(2).strip()
        if code in CODE2TYPE and text:
            out.append((code, text))
    return out


def extract_all(units: List[Dict], llm, tokenizer, sampling_params=None) -> List[List[Tuple[str, str]]]:
    """Gọi vLLM MỘT LẦN cho toàn bộ `units`, trả kết quả đã parse theo thứ tự."""
    from vllm import SamplingParams
    sp = sampling_params or SamplingParams(temperature=0, max_tokens=160)
    prompts = build_chat_prompts(units, tokenizer)
    outs = llm.generate(prompts, sp)
    return [parse_response(o.outputs[0].text) for o in outs]


def test_llm_extract():
    failed = 0

    # 1) parse_response: định dạng chuẩn
    r1 = parse_response("TC|đau bụng\nCD|viêm dạ dày")
    ok1 = r1 == [('TC', 'đau bụng'), ('CD', 'viêm dạ dày')]
    print(f"  {'✓' if ok1 else '✗'} parse chuẩn -> {r1}")
    failed += not ok1

    # 2) parse_response: KHÔNG -> rỗng
    r2 = parse_response("KHÔNG")
    ok2 = r2 == []
    print(f"  {'✓' if ok2 else '✗'} parse KHÔNG -> {r2}")
    failed += not ok2

    # 3) parse_response: khoan dung số thứ tự, mã thường, dấu ':' , khoảng trắng thừa
    r3 = parse_response("1. tc : sốt cao\n  2) KQ|92 g/l  \n\nrác không khớp mẫu\n")
    ok3 = r3 == [('TC', 'sốt cao'), ('KQ', '92 g/l')]
    print(f"  {'✓' if ok3 else '✗'} parse khoan dung định dạng -> {r3}")
    failed += not ok3

    # 4) parse_response: mã lạ (không trong CODE2TYPE) bị bỏ qua, không crash
    r4 = parse_response("XX|gì đó lạ\nTH|paracetamol")
    ok4 = r4 == [('TH', 'paracetamol')]
    print(f"  {'✓' if ok4 else '✗'} parse bỏ mã lạ -> {r4}")
    failed += not ok4

    # 5) build_chat_prompts hoạt động với tokenizer giả (không cần vllm)
    class _FakeTok:
        def apply_chat_template(self, msgs, tokenize, add_generation_prompt, enable_thinking):
            return f"[{len(msgs)} lượt] {msgs[-1]['content']}"
    unit = {'text': 'đau bụng', 'heading': 'Triệu chứng hiện tại'}
    prompts = build_chat_prompts([unit], _FakeTok())
    ok5 = (len(prompts) == 1 and 'Mục: Triệu chứng hiện tại' in prompts[0]
           and 'Đoạn: đau bụng' in prompts[0])
    print(f"  {'✓' if ok5 else '✗'} build_chat_prompts ráp đúng ngữ cảnh -> {prompts[0][:70]!r}")
    failed += not ok5

    # 6) few-shot bắt buộc có ví dụ KHÔNG (chống ảo giác sinh bừa)
    ok6 = any(a.strip() == 'KHÔNG' for _, a in FEWSHOT)
    print(f"  {'✓' if ok6 else '✗'} few-shot có ví dụ KHÔNG")
    failed += not ok6

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"llm_extract: {failed} ca THẤT BẠI")
    print(f"✓ llm_extract: tất cả ca PASS (phần cần GPU/vllm CHƯA được gọi thật)")


if __name__ == "__main__":
    test_llm_extract()
