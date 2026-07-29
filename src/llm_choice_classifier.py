"""
Phân loại span N-lựa-chọn bằng LLM, ràng buộc cứng — dùng CHUNG cho mọi nơi
cần "vá" phần luật tất định không bắt được (nhánh B vá xét nghiệm, nhánh A
bậc 3 của thác triệu chứng/chẩn đoán), thay vì mỗi nơi tự viết một lớp gọi
LLM riêng gần giống nhau (cascade_classifier.tier3_llm là placeholder chưa
bao giờ chạy; llm_classifier.py chỉ cứng cho đúng 2 lựa chọn A/B).

NGUYÊN LÝ ĐÃ ĐO TRONG DỰ ÁN NÀY (không suy đoán):
  - Cho model SINH tự do  -> bịa 61% output (Qwen3-8B, đo trên bệnh án mẫu).
  - Hỏi từng type RIÊNG    -> mất áp lực cạnh tranh, 0/45 lượt chịu trả rỗng.
  - Cho CHỌN trong N lựa chọn cố định, ứng viên lấy từ chính văn bản
    -> bịa trở thành bất khả thi về cấu trúc; N lựa chọn cạnh tranh trực
       tiếp trên cùng thang logit -> không còn hiện tượng "mọi type nhận
       mọi span".

Bố cục prompt CỐ Ý xếp theo thứ tự [hệ thống][toàn văn bệnh án][câu hỏi về
ứng viên] để vLLM prefix-cache được hai khối đầu (giống nhau trong 1 file),
chỉ phần đuôi ~40 token đổi theo từng ứng viên. Đánh dấu vị trí ứng viên
NGAY TRONG bệnh án (kiểu "...«ứng viên»...") sẽ làm mỗi ứng viên có một bản
sao bệnh án khác nhau -> cache vỡ -> prefill lại toàn bộ mỗi lần. KHÔNG làm
vậy trừ khi số lượng ứng viên rất nhỏ (< ~100) và chấp nhận trả giá đó.

⚠️ CHƯA XÁC NHẬN CHẠY ĐƯỢC TRÊN GPU THẬT. Đã kiểm: cú pháp, xây prompt, và
toàn bộ phần hậu xử lý logprob->hậu nghiệm bằng dữ liệu logprob giả lập có
hình dạng đúng như vLLM trả về (xem test_llm_choice_classifier). CHƯA từng
gọi thật một model qua vLLM trong phiên làm việc này vì môi trường chạy code
không có GPU. Đừng báo cáo "đã chạy được" cho tới khi có log thật từ Kaggle.
"""

import math
from typing import Dict, List, Optional, Tuple


class ChoiceClassifier:
    """
    Phân loại một tập ứng viên span vào N nhãn cố định (+ tuỳ chọn nhãn
    "không phải" nào cả), dùng constrained decoding của vLLM.
    """

    def __init__(self, model_name: str, labels: Dict[str, Tuple[str, str]],
                document: str, task_instruction: str):
        """
        Args:
            model_name: HF id, ví dụ 'Qwen/Qwen3-8B' (≤9B, self-host).
            labels: {mã_một_chữ: (tên_nhãn, mô tả)}. Mã một chữ để đọc
                logprob ở ĐÚNG một token sinh đầu tiên — không phụ thuộc
                cumulative_logprob của backend có được chuẩn hoá hay không.
            document: toàn văn bệnh án — nằm trong prompt để cache dùng chung
                cho mọi ứng viên của CÙNG một file.
            task_instruction: mô tả nhiệm vụ, KHÔNG liệt kê nhãn (nhãn được
                render tự động từ `labels`).
        """
        self.model_name = model_name
        self.labels = labels
        self.keys = list(labels)
        self.document = document
        self.task_instruction = task_instruction
        self.llm = None
        self.tokenizer = None

    def _system_prompt(self) -> str:
        lines = [self.task_instruction, ""]
        for k, (name, desc) in self.labels.items():
            lines.append(f"{k}. {name} — {desc}")
        lines.append("\nChỉ trả về một chữ cái. Không giải thích.")
        return "\n".join(lines)

    def load_model(self):
        if self.llm is not None:
            return
        from vllm import LLM
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.llm = LLM(
            model=self.model_name, dtype="float16",
            max_model_len=8192, gpu_memory_utilization=0.85,
            enforce_eager=True, disable_custom_all_reduce=True,
            enable_prefix_caching=True,
        )

    def _render(self, candidate_text: str, local_context: str = "") -> str:
        tail = (f"Đoạn: «{local_context}»\n\nCụm: «{candidate_text}»\n\nNhãn:"
               if local_context else f"Cụm: «{candidate_text}»\n\nNhãn:")
        msgs = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": "BỆNH ÁN:\n" + self.document},
            {"role": "assistant", "content": "Tôi đã đọc bệnh án."},
            {"role": "user", "content": tail},
        ]
        try:
            return self.tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True,
                enable_thinking=False)
        except TypeError:
            return self.tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True)

    @staticmethod
    def posterior(vllm_output, choices: List[str]) -> Tuple[str, float]:
        """
        Đọc phân phối tại token sinh ĐẦU TIÊN, tự chuẩn hoá trên đúng tập
        `choices` — không tin cumulative_logprob của backend đã chuẩn hoá
        sẵn hay chưa (chưa kiểm chứng được điều đó nếu không chạy thật).

        `vllm_output` kỳ vọng có `.logprobs[0]`: dict {token_id: LogProb},
        mỗi LogProb có `.decoded_token` và `.logprob` — đúng hình dạng
        `CompletionOutput.logprobs` của vLLM. Nếu None hoặc rỗng (một số
        cấu hình không trả logprobs) -> lùi về đọc ký tự đầu của text.
        """
        lp = (getattr(vllm_output, 'logprobs', None) or [None])[0]
        if lp:
            scores = {}
            for _tid, o in lp.items():
                tok = (getattr(o, 'decoded_token', None) or '').strip()
                if tok in choices:
                    scores[tok] = max(scores.get(tok, -1e9), o.logprob)
            if scores:
                m = max(scores.values())
                exp = {k: math.exp(v - m) for k, v in scores.items()}
                z = sum(exp.values())
                best = max(exp, key=exp.get)
                return best, exp[best] / z
        guess = (getattr(vllm_output, 'text', '') or '').strip()[:1]
        return (guess if guess in choices else choices[-1]), float('nan')

    def classify_candidates(self, candidates: List[Dict],
                            batch_size: int = 512) -> List[Dict]:
        """
        Args:
            candidates: [{text, start, end}, ...] — từ span_candidates.py
        Returns:
            candidates với thêm 'type' (tên nhãn đầy đủ) và 'score' (hậu
            nghiệm đã chuẩn hoá, NaN nếu không đọc được phân phối).
        """
        if self.llm is None:
            self.load_model()
        from vllm import SamplingParams
        from vllm.sampling_params import StructuredOutputsParams

        sp = SamplingParams(
            temperature=0, max_tokens=4, logprobs=20,
            structured_outputs=StructuredOutputsParams(choice=self.keys))

        out = []
        for i in range(0, len(candidates), batch_size):
            chunk = candidates[i:i + batch_size]
            prompts = [self._render(c['text']) for c in chunk]
            results = self.llm.generate(prompts, sp)
            for c, r in zip(chunk, results):
                key, score = self.posterior(r.outputs[0], self.keys)
                name, _ = self.labels[key]
                out.append({**c, 'type': name, 'score': score})
        return out


def test_llm_choice_classifier():
    """
    Kiểm phần KHÔNG cần GPU: xây prompt đúng cấu trúc, và posterior() đọc
    đúng logprob giả lập có hình dạng như vLLM thật trả về.
    """
    labels = {
        'A': ('TÊN_XÉT_NGHIỆM', 'tên xét nghiệm hoặc chỉ số'),
        'B': ('KẾT_QUẢ_XÉT_NGHIỆM', 'giá trị đo được'),
        'C': ('KHÔNG_PHẢI', 'không thuộc hai loại trên'),
    }
    clf = ChoiceClassifier(
        model_name='Qwen/Qwen3-8B', labels=labels,
        document='Ure: 6,4 mmol/l',
        task_instruction='Bạn là bác sĩ. Chọn đúng một nhãn cho cụm từ.')

    sysmsg = clf._system_prompt()
    assert 'TÊN_XÉT_NGHIỆM' in sysmsg and 'KẾT_QUẢ_XÉT_NGHIỆM' in sysmsg
    assert sysmsg.count('\n') >= 3, "system prompt thiếu dòng cho từng nhãn"
    print("  ✓ system prompt dựng đúng từ dict labels")

    # gia lap logprob giong hinh dang that cua vLLM CompletionOutput
    class FakeLP:
        def __init__(self, tok, lp):
            self.decoded_token = tok
            self.logprob = lp

    class FakeOutput:
        def __init__(self, logprobs, text):
            self.logprobs = logprobs
            self.text = text

    # ca 1: mo hinh rat chac chan chon A
    out1 = FakeOutput([{1: FakeLP('A', -0.01), 2: FakeLP('B', -8.0),
                        3: FakeLP('C', -9.0)}], 'A')
    key, score = ChoiceClassifier.posterior(out1, ['A', 'B', 'C'])
    assert key == 'A' and score > 0.9, f"ca 1 sai: {key} {score}"

    # ca 2: mo hinh phan van giua A va B (logprob gan nhau)
    out2 = FakeOutput([{1: FakeLP('A', -0.7), 2: FakeLP('B', -0.7),
                        3: FakeLP('C', -5.0)}], 'A')
    key2, score2 = ChoiceClassifier.posterior(out2, ['A', 'B', 'C'])
    assert key2 == 'A' and 0.4 < score2 < 0.6, f"ca 2 sai: {key2} {score2}"

    # ca 3: khong co logprobs (backend khong tra) -> lui ve doc ky tu dau
    out3 = FakeOutput(None, 'B')
    key3, score3 = ChoiceClassifier.posterior(out3, ['A', 'B', 'C'])
    assert key3 == 'B' and score3 != score3, f"ca 3 sai: {key3} {score3}"  # NaN != NaN

    print("  ✓ posterior(): 3/3 ca PASS (dùng logprob giả lập, KHÔNG phải model thật)")
    print(f"\n{'='*60}")
    print("✓ llm_choice_classifier: phần không-cần-GPU PASS. "
         "classify_candidates() CHƯA được gọi với model thật.")


if __name__ == "__main__":
    test_llm_choice_classifier()
