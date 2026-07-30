# Bàn giao — Medical NER Vietnamese

> Tài liệu này viết cho **agent tiếp theo chưa có ngữ cảnh gì**. Chỉ ghi điều **đã chạy và
> thấy kết quả**. Chỗ nào chưa chạy thì ghi rõ "CHƯA" — đừng suy ra là đã xong.
>
> Bản trước của file này tự nhận "100% COMPLETE / All tests passing" trong khi 2 nhánh
> bắt sai gần hết và bộ test có ca "pass rỗng". Đừng lặp lại: **chỉ tick khi có log**.

---

## 1. Trạng thái — cái gì XONG, cái gì CHƯA

| phần | trạng thái | bằng chứng |
|---|---|---|
| **Train encoder** | ✅ **XONG** | Kaggle T4×2, 10 epoch, 3760 step, 31 phút. **dev F1 = 0.8203** (P 0.802 / R 0.839) |
| Chuyển dữ liệu PhoNER + ViMQ | ✅ xong | 12.027 câu train / 3.000 dev / 4.000 test |
| Nhánh B — xét nghiệm (luật) | ✅ đúng phần cấu trúc `Tên: Giá_trị` | `36.txt` 11/11 tên, 0 rác, offset khớp 100/100 file |
| Nhánh B — các dạng khác | ⚠️ **BỎ SÓT 16/100 file** | xem Mục 4 — đã có giải pháp, **chưa nối** |
| Nhánh C — thuốc | ✅ đúng | `36.txt` 4/4 thuốc, offset khớp 100/100 file |
| Ánh xạ offset PyVi + NFC | ✅ đúng | 100/100 file |
| `ner_metrics.py` | ✅ đúng | 7/7 test + chạy thật trong `Trainer` |
| Overlap resolver (QHĐ) | ✅ đúng | test riêng pass |
| `negation_detector.py` | ✅ đúng, **API 2 bước** | 10/10 test; xem cách gọi ở Mục 5.4 |
| `span_candidates.py` (mới) | ✅ đúng | 6/6 ca, phủ 100% các dạng nhánh B bỏ sót |
| `llm_choice_classifier.py` (mới) | ⚠️ **CHƯA chạy GPU** | chỉ test phần logic; `classify_candidates()` chưa gọi model thật lần nào |
| **Nối nhánh A vào inference** | ❌ **CHƯA LÀM** | có weight rồi nhưng `ner_inference_e2e.ipynb` chưa dùng |
| **Gold thủ công** | ❌ **CHƯA CÓ** | mọi ngưỡng (0.93, τ) đều từ mẫu tự chọn |

**Việc tiếp theo quan trọng nhất: Mục 4 (vá nhánh B) và Mục 6 (nối nhánh A).**

---

## 2. Kết quả training — đọc cho đúng

```
eval_f1: 0.8203    eval_precision: 0.8022    eval_recall: 0.8393
train_loss: 0.1546    3760 step / 10 epoch / 1865s
```

**0.82 này KHÔNG phải điểm thi.** Nó đo trên dev của PhoNER + ViMQ, tức **trong miền của
chúng**: PhoNER là tin tức COVID, ViMQ là câu hỏi bệnh nhân tự viết. Miền đích của ta là
**bệnh án lâm sàng** — khác cả hai. Paper gốc đạt 80.65 trên ViMQ-NER nên 82 là hợp lý,
nhưng ra ngoài miền sẽ thấp hơn, chưa biết bao nhiêu.

Cảnh báo `missing keys ... LayerNorm.weight/bias` + `unexpected keys ... LayerNorm.beta/gamma`
là **bình thường**, không phải lỗi: checkpoint dùng tên cũ `beta/gamma`, transformers mới dùng
`weight/bias`. LayerNorm vẫn được nạp đúng — nếu không thì F1 đã không đạt 0.82.

---

## 3. Kiến trúc — 3 nhánh độc lập

```
văn bản thô
   │
   ├── NHÁNH A — triệu chứng & chẩn đoán            [encoder XONG, chưa nối inference]
   │   PyVi tách từ + giữ ánh xạ offset  (utils/text_alignment.py)
   │       ↓  encoder BIO → span SYM_DIS
   │       ↓  ánh xạ ngược về offset văn bản gốc
   │   thác 3 bậc → TRIỆU_CHỨNG | CHẨN_ĐOÁN         (cascade_classifier.py)
   │
   ├── NHÁNH B — xét nghiệm                          (branch_b_lab_tests.py)
   │   luật "đoạn liền kề" → TÊN_XÉT_NGHIỆM + KẾT_QUẢ_XÉT_NGHIỆM
   │   + bước VÁ bằng ứng viên (span_candidates.py) [CHƯA NỐI]
   │
   └── NHÁNH C — thuốc                               (branch_c_drugs.py)
       từ điển RxNorm + luật cấu trúc → THUỐC
   │
   ├── negation_detector.py  → affirmed / negated
   └── utils/overlap_resolver.py → QHĐ chọn tập không chồng lấn
   │
   └──→ JSON 5 type
```

**Nguyên lý xuyên suốt, rút ra từ đo đạc — đừng vi phạm:**

| đã thử | kết quả đo | kết luận |
|---|---|---|
| LLM **sinh tự do** cả 5 type | Qwen3-8B **bịa 274 span** (61% output) | sinh tự do = bịa |
| Hỏi **từng type riêng** | **0/45 lượt** chịu trả rỗng; 1 span nhận 4 nhãn | mất áp lực cạnh tranh |
| Prompt có **câu cấm** | phản tác dụng **3/3 lần** | không dùng câu cấm |
| **Chọn 1 trong N**, ứng viên cắt từ văn bản | bịa bất khả thi về cấu trúc | ✅ dùng cách này |

---

## 4. ⚠️ VIỆC ƯU TIÊN 1 — Nhánh B bỏ sót 16/100 file

Đã quét toàn bộ 100 file bằng một máy dò độc lập rộng hơn. Luật hiện tại chỉ bắt được cấu
trúc `Tên: <số> <đơn vị>`. **Bốn dạng bị bỏ sót:**

| dạng | ví dụ thật | vì sao trượt |
|---|---|---|
| Huyết áp tỷ lệ (~10 file) | `Huyết áp: 130/76 mmHg` | `VALUE_ONLY` chỉ khớp *một* số, không khớp `số/số` |
| Panel dính liền | `WBC : 14.99 G/L NEUT% : 82.9 %` | giữa 2 cặp chỉ có khoảng trắng, không phải `\n ; : ,` → dính 1 đoạn |
| Mũi tên / không đơn vị | `Troponin I/T ↑` · `PT - INR: 1.05` | không có đơn vị trong danh sách trắng |
| Lồng trong câu văn | `lipase là tăng lên ở mức 623` · `tbr là cao tới 1.0` | không phải cấu trúc `Tên: Giá_trị` |

**ĐỪNG thêm regex cho từng dạng** — sẽ không bao giờ hết (`↑`, `(-)`, `âm tính`, `2+`…).
Giải pháp tổng quát **đã viết và đã đo**, chỉ còn nối:

```python
from branch_b_lab_tests import extract_lab_pairs, lab_va_candidates
from llm_choice_classifier import ChoiceClassifier

resolved = extract_lab_pairs(text)              # luật bắt phần cấu trúc rõ ràng
cands    = lab_va_candidates(text, resolved)    # sinh ứng viên CHỈ ở vùng luật bỏ sót

clf = ChoiceClassifier(
    model_name='Qwen/Qwen3-8B',
    labels={'A': ('TÊN_XÉT_NGHIỆM', 'tên xét nghiệm hoặc chỉ số'),
            'B': ('KẾT_QUẢ_XÉT_NGHIỆM', 'giá trị đo được'),
            'C': ('KHÔNG_PHẢI', 'không thuộc hai loại trên')},
    document=text,
    task_instruction='Bạn là bác sĩ. Chọn đúng một nhãn cho cụm từ.')
va = clf.classify_candidates(cands)             # ⚠️ CHƯA chạy GPU lần nào
final = resolved + [e for e in va if e['type'] != 'KHÔNG_PHẢI']
```

**Đã đo (không cần GPU):** `span_candidates.gen_candidates()` phủ **100%** cả 6 dạng trên —
kể cả `↑` và `1.05`. Tức trần của phương pháp là 100%, việc còn lại chỉ là LLM chọn đúng.

**Chưa đo:** LLM chọn có đúng không. Phải chạy rồi mới biết.

---

## 5. Chi tiết từng nhánh

### 5.1 Nhánh B — luật (phần đã xong)
1. Tách đoạn ở `\n` `;` `:` và dấu phẩy **không giữa hai chữ số** (`4,49` là số thập phân).
2. Đoạn nào **LÀ** `số + đơn vị y khoa` (danh sách trắng) → `KẾT_QUẢ_XÉT_NGHIỆM`.
3. **Đoạn ngay trước** → `TÊN_XÉT_NGHIỆM`, nếu ≤40 ký tự và có chữ cái.

Lý do ghép theo **đoạn liền kề** chứ không regex trong đoạn: bước 1 đã cắt ở `:` nên
`Ure: 6,4 mmol/l` thành hai đoạn — trong đoạn không còn cặp nào để ghép. Bản cũ làm sai chỗ
này nên bắt **0/11** và sinh rác (`TÊN='Bệnh nhân nam' KẾT_QUẢ='17 tuổi'`).

### 5.2 Nhánh C — thuốc
1. Khớp n-gram ≤5 từ với **138.361 tên** từ `rxnorm_merged.csv` (129.690 dòng + biến thể
   rụng `-e`: RxNorm ghi `furosemide`, bệnh án Việt viết `furosemid`).
2. Nối hàm lượng: `Medrol 16mg x 3 viên` → span dừng ở `Medrol 16mg`.
3. **Chất lưỡng dụng** (`glucose`, `creatinine`, `protein`…) chỉ là THUỐC khi **có hàm lượng**:
   `Glucose 5% x 1000ml` → thuốc; `Glucose máu: 13,2 mmol/l` → không.
4. **Thuốc ngoài từ điển**: tên riêng đứng ngay trước hàm lượng → THUỐC (`score=0.7`).
   Đây là cách bắt `Omez 20mg` (biệt dược Ấn, không có trong RxNorm) **không cần LLM**.

### 5.3 Nhánh A — thác 3 bậc (sau khi encoder ra span `SYM_DIS`)
- **Bậc 1**: top-1 ICD thuộc **chương R** → `TRIỆU_CHỨNG`. Đo: 7/7 đúng.
- **Bậc 2**: ngoài chương R **và** cosine ≥ 0.93 → `CHẨN_ĐOÁN`. Đo: 11/11 đúng, 0 lọt.
- **Bậc 3**: còn lại (~40%) → LLM chọn nhị phân A/B. **CHƯA chạy.**

Vì sao không dùng KB cho tất cả: chương R chỉ có **495/17.094** tên. Từ ngữ triệu chứng đời
thường (`nặng mặt`, `tiểu ít`) **không có trong ICD**, retriever không có quyền nói "không có
trong KB" nên luôn trả hàng xóm gần nhất → đoán bừa thành bệnh.

### 5.4 Phủ định — API 2 BƯỚC, dễ dùng sai
```python
annotated = detector.annotate_negation(entities, text)   # BƯỚC 1 gắn 'negated'
status    = detector.get_assertion_status(annotated[0])  # BƯỚC 2 đọc lại
```
Gọi `get_assertion_status()` trực tiếp trên entity **chưa** qua `annotate_negation()` sẽ
luôn trả `'affirmed'` — nó chỉ đọc field `'negated'` có sẵn, không tự tính.

Đo trên `36.txt`: `suy thận` / `thiếu máu` / `viêm họng cấp` → `negated`;
`Hội chứng thận hư` → `affirmed`.

---

## 6. ⚠️ VIỆC ƯU TIÊN 2 — Nối nhánh A vào inference

Weight đã có (F1 0.82) nhưng `ner_inference_e2e.ipynb` **chưa dùng**. Các bước:

1. Tải weight từ Kaggle output → upload thành Kaggle Dataset.
2. Trong notebook inference: `words, spans, ok = segment_with_map(TEXT)` rồi
   **`assert ok`** — ánh xạ vỡ thì mọi offset sau đó sai âm thầm.
3. Đưa `words` qua encoder → nhãn BIO → gộp span → dùng `spans[i]` quy về offset gốc.
4. Mỗi span `SYM_DIS` qua `CascadeClassifier.classify()`.
5. Hợp nhất 3 nhánh → `annotate_negation` → `select_non_overlapping` → JSON.

**Bug đã biết chưa sửa:** `cascade_classifier.py` đọc `row['name']` nhưng
`icd10_vi_full.csv` có cột `code,term` → sẽ ném `KeyError: 'name'`. Sửa thành `row['term']`,
và **đừng bọc `try/except` nuốt lỗi** (bản cũ của nhánh C làm vậy, KB tụt từ 129.690 xuống
68 tên mà vẫn báo chạy bình thường).

---

## 7. JSON đầu ra

```json
{
  "text": "<nguyên văn bệnh án>",
  "entities": [
    {"text": "Hội chứng thận hư", "type": "CHẨN_ĐOÁN", "start": 89, "end": 106,
     "score": 0.97, "source": "encoder+kb", "negated": false, "assertion": "affirmed"}
  ]
}
```
`type` ∈ `TRIỆU_CHỨNG` `CHẨN_ĐOÁN` `THUỐC` `TÊN_XÉT_NGHIỆM` `KẾT_QUẢ_XÉT_NGHIỆM`.
`source`: `rule` (B) · `dict`/`rule_strength` (C) · `encoder+kb`/`encoder+llm` (A).
**Bất biến bắt buộc:** `text == raw[start:end]`, và không span nào chồng lấn.

---

## 8. Chạy

```bash
python test_local.py                  # 6/6 phải pass trước khi push
python src/negation_detector.py       # 10/10, không cần GPU
python src/span_candidates.py         # 6/6, không cần GPU
python src/llm_choice_classifier.py   # phần logic, KHÔNG gọi model thật
```
**Train:** Kaggle T4×2 + Internet ON, **Factory reset trước Run All** (session cũ còn thư
mục `fakeer/` thì `git clone` bị bỏ qua → chạy nhầm code cũ). ~31 phút.

Notebook clone từ `https://github.com/Khanhhh239/fakeer` — **sửa ở máy phải push mới có
tác dụng trên Kaggle**. Đã mất một lần chạy vì quên điều này.

---

## 9. Bẫy đã trả giá — đừng lặp lại

| bẫy | hậu quả thật |
|---|---|
| `except` nuốt lỗi khi nạp KB | RxNorm 129.690 → **68 tên**, vẫn báo chạy bình thường |
| Test chỉ lặp qua kết quả rồi assert | trích 0 thực thể vẫn báo PASS (**pass rỗng**) |
| `split('\t')` trên file CoNLL dùng **dấu cách** | PhoNER ra **0 câu**, train mất nửa dữ liệu, không báo lỗi |
| `classifier_dropout` trên DeBERTaV2 | `TypeError` — DeBERTaV2 không có field này |
| `Trainer(tokenizer=...)` | đã đổi thành `processing_class=` |
| `\b` sau `%` trong regex | `Glucose 5%` không khớp (`%` và space đều không phải ký tự chữ) |
| `-` trong lớp ký tự phân cách | `Cl-` mất dấu trừ |
| Đọc sai tên cột CSV rồi đoán | `df['name']` vs thật là `df['term']` — **mở file ra xem** |
| Thêm tính năng mới khi lõi đang hỏng | bản cũ thêm negation+LLM trong khi nhánh B bắt 0/11 |

**Quy tắc rút ra:** nạp KB / chuyển dữ liệu thất bại thì **dừng hẳn**, đừng chạy tiếp. Mọi
test phải nêu **số** thực thể mong đợi và có ít nhất một ca **phải trả rỗng**.
