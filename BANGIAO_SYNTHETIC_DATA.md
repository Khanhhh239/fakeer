
## TRẠNG THÁI DỰ ÁN (đọc trước tiên)

**Kiến trúc đã xong — pipeline TRÍCH XUẤT (khác việc đang bàn giao):**
Token hoa NER 5 loại trên dữ liệu đề thi thật đã chạy được end-to-end trên Kaggle,
điểm WER thật **24.67** (tăng từ 19.07 của bản đầu). Kiến trúc chi tiết ở
`PIPELINE_V2.md`. Code: `src/segment_units.py`, `span_anchor.py`, `merge_entities.py`,
`llm_extract.py`, `export_btc.py` + `notebooks/ner_v2_phase1.ipynb`,
`ner_v2_phase2.ipynb` (chạy trên Kaggle GPU, đã test). **KHÔNG đụng vào mảng này.**

**Việc đang bàn giao ở file này — SINH DATA HUẤN LUYỆN TỔNG HỢP:**
Mục đích: có data để fine-tune encoder riêng (hiện encoder chỉ train trên
PhoNER_COVID19, chỉ biết 2/5 loại). **CHƯA CÓ DÒNG CODE NÀO cho phần này** —
chỉ mới có KẾT QUẢ NGHIÊN CỨU + KHO NGUỒN (liệt kê đủ ở §2) + PROMPT đã
đo thử trên Ollama và sửa đến bản ổn (§3.2, §3.4). Toàn bộ §3–§10 dưới đây là
đặc tả cần hiện thực hoá, KHÔNG phải mô tả cái đã chạy được.

**Việc CẦN LÀM NGAY, theo thứ tự — xem chi tiết từng bước ở §10:**
1. Viết module T0 (§3.1) — không cần GPU
2. Viết `anchor_all` + cổng kiểm định (§4–§5) — không cần GPU
3. Viết module T2A dựng khối cấu trúc (§3.3) — không cần GPU
4. **Gán tay 5–10 file `input/*.txt` làm tập kiểm định** — BẮT BUỘC, chưa làm
5. Viết notebook Kaggle gọi Qwen3-8B qua vLLM cho T1+T2B (§3.2, §3.4)
6. Chạy thử 20–30 file, soi tay, chỉnh ngưỡng cổng theo số đo thật
7. Chạy full ~500 file → train lại encoder → đo trên tập kiểm định bước 4

---

# Bàn giao: Sinh dữ liệu huấn luyện NER tổng hợp

Tài liệu duy nhất cho việc này. Thay thế `YEUCAU_DATA.md`, `PLAN_SYNTHETIC_DATA_V2.md`,
`PROMPTS_TEST.md` (đã xoá — nội dung dồn hết vào đây, bỏ phần phân tích/tường thuật).

## 0. Ràng buộc & mục tiêu

- Model sinh data: ≤9B tham số, không API ngoài (Qwen3-8B qua Ollama/vLLM).
- Sinh cho 5 loại: `TRIỆU_CHỨNG`, `CHẨN_ĐOÁN`, `THUỐC`, `TÊN_XÉT_NGHIỆM`, `KẾT_QUẢ_XÉT_NGHIỆM`.
- Mục tiêu: ~6.000 thực thể dương + ~2.000 ca đối chứng âm, ~500 file, mỗi file 1.500–4.000 ký tự.
- Chỉ làm NER (span + type). Candidate-linking (tra mã ICD/RxNorm) làm sau — xem §1.3.

## 1. Ba nguyên lý bắt buộc

### 1.1 LLM không bao giờ gán nhãn

LLM chỉ viết văn hoặc đề xuất kiến thức y khoa. Nhãn luôn có trước khi gọi LLM
(sinh khối cấu trúc bằng code), hoặc neo bằng tìm chuỗi chính xác sau khi LLM viết
xong (phần văn xuôi). LLM không bao giờ tự quyết span hay type.

### 1.2 Text phải là văn thật, không phải chuỗi KB dán liền

Cổng kiểm: **tỷ lệ số từ nằm trong thực thể phải trong khoảng 8%–18%**. Vượt 25%
nghĩa là văn bản đã thoái hoá thành chuỗi tra cứu dán liền nhau — loại thẳng, không sửa.

### 1.3 NER và Linking là hai tầng khác nhau, không trộn

- **NER (đang làm):** span/type không cần khớp KB. `kháng sinh`, `siêu âm`, `nội soi`
  vẫn là thực thể ĐÚNG dù không có trong RxNorm/`kb/xetnghiem_ten.txt` — đề thi dùng liên tục
  (nội soi 30 lần, siêu âm 26 lần / 100 file thật).
- **Linking (làm sau):** bắt buộc khớp chính xác KB. Trường nội bộ `linkable`
  (không xuất ra nhãn cuối) đánh dấu span nào tra được mã, span nào phải abstain:

| Loại | `linkable=true` khi | `linkable=false` khi |
|---|---|---|
| `THUỐC` | khớp RxNorm (hoạt chất/biệt dược) | `kháng sinh`, `thuốc hạ sốt`, `thuốc nam` |
| `CHẨN_ĐOÁN` | khớp ICD-VN | mô tả chung không phải tên bệnh chuẩn |
| `TÊN_XÉT_NGHIỆM` | khớp `kb/xetnghiem_ten.txt` | mô tả mơ hồ không định danh được |

## 2. Tài nguyên đã có sẵn — DÙNG THẲNG, không sinh lại

Tất cả nằm trong `kb/` (đã commit):

| File | Nội dung | Dùng ở đâu |
|---|---|---|
| `kb/icd10_vi_full.csv` | 14.627 mã ICD-VN | Nguồn `CHẨN_ĐOÁN`, cột `code,term` |
| `kb/rxnorm_merged.csv` | 129.690 dòng / 83.320 RxCUI | Nguồn `THUỐC`, cột `code,term` |
| `kb/inn_usan.csv` | 36 cặp INN↔USAN | Bổ sung biến thể tên thuốc |
| `kb/xetnghiem_ten.txt` | 598 tên xét nghiệm thật (trích từ bảng giá) | Nguồn DƯƠNG duy nhất cho `TÊN_XÉT_NGHIỆM` |
| `kb/heading_lamsang.txt` | 67 tên mục bệnh án thật (quét từ đề thi, ≥2 lần) | Heading cho khối cấu trúc |
| `kb/heading_hoidap.txt` | 8 tên mục hỏi–đáp thật | Heading cho phần văn xuôi |
| `kb/am_thuoc_gia.txt` | 275 mục — trông giống thuốc nhưng không phải | Mồi âm THUỐC |
| `kb/am_xetnghiem_gia.txt` | 299 mục — thủ thuật/điều trị, không phải xét nghiệm | Mồi âm TÊN_XÉT_NGHIỆM |

`src/branch_b_lab_tests.py` có sẵn whitelist `UNIT` (đơn vị đo xét nghiệm hợp lệ) —
tái dùng, không viết lại danh sách đơn vị.

## 3. Kiến trúc — 5 tầng

```
T0  Kho nguồn (đã có sẵn ở §2, chỉ cần lọc/phân tầng thêm cho CHẨN_ĐOÁN/TRIỆU_CHỨNG)
T1  Kịch bản ca bệnh (LLM đề xuất bộ khái niệm nhất quán quanh 1 chẩn đoán)
T2A Khối bệnh án cấu trúc (code điền, KHÔNG dùng LLM, nhãn đúng 100% theo cấu tạo)
T2B Văn xuôi hỏi–đáp (LLM viết, neo nhãn bằng tìm chuỗi chính xác)
T3  Cổng kiểm định (9 điều kiện, §7)
```

### 3.1 T0 — bổ sung cho CHẨN_ĐOÁN và TRIỆU_CHỨNG

`CHẨN_ĐOÁN`: lọc `kb/icd10_vi_full.csv` lấy term ≤6 từ. Phân tầng đều theo 22 chương
ICD (mỗi chương ≥30 term), phần dư dồn vào chương phổ biến (hô hấp, tiêu hoá, cơ
xương khớp, da liễu, tim mạch). Mục tiêu ≥1.200 form.

`TRIỆU_CHỨNG`: nguồn = ICD chương R (mã bắt đầu bằng `R`) + khai thác cụm từ các
bullet trong `input/*.txt` (dùng `src/segment_units.py:segment_document`, lấy
`u['text']` của các unit có `is_bullet=True`). Mục tiêu ≥1.000 form.

`THUỐC`: 3 nguồn, gộp lại:
1. Tách hoạt chất từ `rxnorm_merged.csv` — quy tắc tách: cắt phần dạng bào chế
   (`Oral Tablet`, `Injectable`...) và phần hàm lượng (`\d+\s*(MG|G|ML)...`), giữ
   phần tên hoạt chất. Bỏ chuỗi có dấu `/` hoặc `[...]` (đóng gói phối hợp thương mại).
2. Biến thể chính tả Việt: bỏ `-e` cuối (`furosemide→furosemid`), cộng bảng
   `inn_usan.csv` (`paracetamol↔acetaminophen`).
3. Danh sách tay ~80 mục nhóm thuốc chung tiếng Việt (`kháng sinh`, `thuốc hạ sốt`,
   `thuốc giảm đau`, `corticoid`...), tất cả gắn `linkable=false`.

`KẾT_QUẢ_XÉT_NGHIỆM`: sinh bằng luật cấu trúc (không phải từ vựng, không cần kho):
```
số + đơn vị (chấm)   : 14.99 G/L, 6.4 mmol/l, 92 g/L
số + đơn vị (phẩy)   : 4,49 T/l                    ← thập phân kiểu Việt
tỷ lệ                : 130/76 mmHg
định tính            : âm tính, dương tính, (+), (-), (++), (±)
mũi tên/xu hướng     : ↑, ↓, tăng, giảm, tăng nhẹ
mô tả                : men gan tăng, không thấy bất thường, bình thường
ngưỡng               : < 0.01, > 200, ≤ 5, ≥ 10
```
Đơn vị lấy từ whitelist `UNIT` trong `src/branch_b_lab_tests.py`.

Cách ghép tên (từ `xetnghiem_ten.txt`) ↔ kết quả — **8 format, phải trải đều**,
đặc biệt 2 format cuối (đây là lỗ hổng đã đo được ở pipeline trước — luật cũ đòi
"số + đơn vị" nên bỏ sót 85% tên xét nghiệm không đi kèm giá trị số):
```
1. Ure: 6,4 mmol/l          5. - Ure: 6,4 mmol/l
2. Ure : 6,4 mmol/l         6. • Ure: 6,4 mmol/l
3. Ure = 6,4 mmol/l         7. Ure ↑                    (không có số)
4. Ure 6,4 mmol/l           8. Ure                       (đứng một mình, không kết quả)
   WBC : 14.99 G/L NEUT% : 82.9 %   (nhiều cặp dính liền một dòng)
```
Bắt buộc ≥40% số `TÊN_XÉT_NGHIỆM` sinh ra đứng MỘT MÌNH (format 7–8), không kèm kết quả.

### 3.2 T1 — Prompt sinh kịch bản ca bệnh

```
CHỈ TRẢ LỜI BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc, tiếng Anh.

Bạn là bác sĩ Việt Nam. Với chẩn đoán được cho, liệt kê các khái niệm y khoa
thường đi kèm trong bệnh án.

ĐỊNH DẠNG: mỗi dòng một mục, đúng dạng MÃ|nội dung
  TC = triệu chứng người bệnh cảm nhận hoặc bác sĩ quan sát được
  TH = tên thuốc điều trị
  TX = tên xét nghiệm / thăm dò / thủ thuật chẩn đoán

SỐ LƯỢNG: 5 dòng TC, 3 dòng TH, 3 dòng TX. Tổng đúng 11 dòng.

QUY TẮC:
1. Chỉ ghi TÊN, không ghi động từ đi kèm.
   ĐÚNG: TH|amoxicillin        SAI: TH|Tiêm amoxicillin
2. TH phải là tên thuốc CÓ THẬT. Không bịa.
   ĐÚNG: TH|paracetamol, TH|kháng sinh, TH|corticoid
   SAI:  TH|antirôsin, TH|thuốc đặc trị, TH|Antibiotic uống
3. TX phải là TÊN một xét nghiệm cụ thể, KHÔNG phải mô tả cách làm.
   ĐÚNG: TX|công thức máu, TX|siêu âm ổ bụng, TX|nội soi dạ dày
   SAI:  TX|Phương pháp chẩn đoán lâm sàng, TX|Quan sát triệu chứng
4. TC phải là điều người bệnh CẢM THẤY hoặc bác sĩ THẤY trên người bệnh.
   ĐÚNG: TC|sốt cao, TC|đau vùng thượng vị
   SAI:  TC|Nhai hoặc mút đồ vật, TC|Sử dụng miệng lưỡi cắn
5. Mọi mục phải liên quan TRỰC TIẾP tới chẩn đoán đã cho.
6. Mỗi mục 1-5 từ, viết như bác sĩ ghi bệnh án.
7. KHÔNG chú thích tên nước ngoài trong ngoặc. SAI: TC|sợ nước (hydrophobia)
8. Viết xong 11 dòng thì DỪNG. Không giải thích, không hỏi lại.

VÍ DỤ — chẩn đoán "Viêm dạ dày":
TC|đau vùng thượng vị
TC|ợ chua
TC|buồn nôn
TC|đầy bụng sau ăn
TC|chán ăn
TH|omeprazole
TH|thuốc trung hoà acid
TH|amoxicillin
TX|nội soi dạ dày
TX|test hơi thở tìm H. pylori
TX|công thức máu

BÂY GIỜ LÀM VỚI CHẨN ĐOÁN: "{diagnosis}"

Nhắc lại: chỉ tiếng Việt. Không chữ Hán. Không tiếng Anh. Không chú thích trong ngoặc.
```

`{diagnosis}` lấy từ kho `CHẨN_ĐOÁN` đã phân tầng (§3.1). Chuỗi TC/TH/TX trả về
**không cần khớp KB** (xem §1.3) — chỉ loại nếu rỗng hoặc lặp lại y hệt mã khác.

### 3.3 T2A — Khối bệnh án cấu trúc, code điền, không dùng LLM

Heading lấy từ `kb/heading_lamsang.txt` (67 tên) và `kb/heading_hoidap.txt` (8 tên).
Code tự phối cấu trúc — **không dùng LLM cho bước này** (đã thử LLM "sinh khung đa
dạng", hỏng vì mỗi lần gọi độc lập nên không nhớ khung trước, và LLM mode-collapse
khi bị yêu cầu "hãy đa dạng"):

```python
NUMBERING = [None, '1.', '1)', 'I.', 'A.', 'Mục 1:', '1 -', '(1)']
BULLET    = ['-', '•', '*', '+', '‣', '·', None, '1.', 'a)', '–']
INDENT    = ['', '  ', '    ', '      ', '\t']
COLON     = [':', '', ' :', ' -', '...']
BLANKS    = [0, 1, 2]
CASE      = [str, str.upper, str.title]
LAYOUT    = ['bullet', 'inline', 'numbered']   # inline: "Triệu chứng: sốt, ho"
```
Random tổ hợp các tham số trên + random thứ tự mục + random heading trong danh sách
67 tên → dựng khung, rồi điền thực thể từ T0/T1 vào từng `{SLOT}`. Offset tính trực
tiếp theo vị trí chèn trong code → nhãn đúng 100% theo cấu tạo, không cần neo.

### 3.4 T2B — Văn xuôi hỏi–đáp, LLM viết + neo nhãn

Bố cục PHẢI đúng — đề thi thật **0/100 file là đối thoại qua lại**, toàn bộ là
1 câu hỏi + 1 bài trả lời có mục:

```
CHỈ VIẾT BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc. Được phép dùng
thuật ngữ y khoa chuẩn viết bằng chữ La-tinh (xem quy tắc bên dưới), không
được dịch hay chú thích bằng tiếng Anh thường.

Bạn là biên tập viên chuyên mục tư vấn sức khoẻ của một trang web y tế Việt Nam.
Viết MỘT BÀI tư vấn hoàn chỉnh.

Bài gồm đúng các phần sau, viết liền mạch:

Câu hỏi từ người dùng:
(4 đến 6 câu, người bệnh tự kể: hoàn cảnh, khó chịu ra sao, lo lắng gì, rồi hỏi)

Câu trả lời của bác sĩ:
Chào bạn,
1. {tiêu_đề_mục_1}
(4 đến 6 câu)
2. {tiêu_đề_mục_2}
(4 đến 6 câu)
3. {tiêu_đề_mục_3}
(4 đến 6 câu)
4. {tiêu_đề_mục_4}
(4 đến 6 câu)
Trân trọng!

CÁCH VIẾT TIÊU ĐỀ MỤC — rất quan trọng:
ĐÚNG:  1. Bệnh dại là bệnh gì
SAI:   1. [Bệnh này là gì] — giải thích bản chất bệnh:
Tiêu đề là một câu ngắn bình thường. Không dùng dấu ngoặc vuông.
Không dùng dấu gạch ngang rồi mô tả lại. Không chép chữ trong hướng dẫn này.

CÁC CỤM SAU PHẢI XUẤT HIỆN NGUYÊN VĂN trong bài, không sửa một chữ:
{danh_sách_cụm_bắt_buộc}
- {bait_thuoc}
- {bait_xetnghiem}

**BẮT BUỘC:** 2 dòng cuối (`{bait_thuoc}`, `{bait_xetnghiem}`) đưa vào bài
NHƯ MỌI CỤM KHÁC ở trên — tự nhiên, không giải thích, không đánh dấu là lạ.
Nhưng chúng KHÔNG phải thuốc và KHÔNG phải xét nghiệm thật, chỉ nhắc qua,
không dùng làm phần điều trị/chỉ định chính của bài.

QUY TẮC:
- Tổng bài 500 đến 700 từ. Mục nào cũng đủ 4 đến 6 câu.
- Mỗi câu mang một thông tin y khoa mới. Cấm lặp ý đã nói.
- Cấm câu trấn an rỗng như "đừng lo lắng", "hãy đến khám ngay" nếu không
  kèm thông tin y khoa cụ thể.
- Cấm viết dạng đối thoại qua lại. Người bệnh chỉ hỏi một lần ở đầu bài.
- Không dùng gạch đầu dòng trong phần trả lời, viết thành đoạn văn.

MÔ PHỎNG LỖI GÕ CỦA BỆNH ÁN THẬT:
1. Dính liền {n_glue} chỗ: bỏ dấu cách giữa hai từ, ví dụ "bệnh dạithường".
2. Chèn dấu sao {n_mask} chỗ, ví dụ "Kháng sinh nhóm ***", giống chỗ mờ
   trong bệnh án chụp lại.
Chỉ áp dụng ở phần văn xuôi bình thường, KHÔNG được đụng vào bất kỳ cụm nào
trong danh sách cụm bắt buộc ở trên — kể cả 2 dòng bait.

QUY TẮC NGÔN NGỮ — PHÂN BIỆT RÕ:
ĐƯỢC PHÉP dùng thuật ngữ y khoa chuẩn bằng chữ La-tinh/viết tắt quốc tế,
vì bác sĩ Việt Nam viết như vậy trong bệnh án thật:
  Tên thuốc theo tên chung quốc tế: omeprazole, amoxicillin, furosemid.
  Viết tắt xét nghiệm: CRP, AST, ALT, HbA1c, WBC, SPO2, G6PD, CT, MRI, PT-INR.
  ĐÂY KHÔNG PHẢI tiếng Anh, đây là cách viết chuẩn của ngành y.
CẤM dịch hoặc chú thích tên bệnh/triệu chứng tiếng Việt sang tiếng Anh thường:
  ĐÚNG: "Bệnh dại", "sợ nước", "chó cắn"
  SAI:  "Bệnh dại (rabies)", "sợ nước (hydrophobia)", "dog bite"
Nói cách khác: tên THUỐC và tên/viết tắt XÉT NGHIỆM được giữ nguyên dạng
quốc tế; còn TÊN BỆNH, CHẨN ĐOÁN, triệu chứng thì LUÔN viết tiếng Việt,
không chú thích tên nước ngoài đi kèm.

Nhắc lại: viết tiếng Việt, thuốc/xét nghiệm được giữ tên quốc tế chuẩn,
không dịch tên bệnh/triệu chứng sang tiếng Anh, không chữ Hán, không ngoặc vuông.
```

**Ghép tham số động — làm ở CODE, trước khi gọi LLM, không phải sau:**

```python
import random

def build_prompt(entities, am_thuoc, am_xetnghiem, template):
    n_glue = random.randint(1, 5)
    n_mask = random.randint(1, 3)
    bait_thuoc = random.choice(am_thuoc)        # mỗi lần gọi random lại, không cố định
    bait_xn    = random.choice(am_xetnghiem)
    cum_list = '\n'.join(f'- {c}' for c in entities)
    prompt = template.format(cum_list=cum_list, n_glue=n_glue, n_mask=n_mask,
                              bait_thuoc=bait_thuoc, bait_xetnghiem=bait_xn,
                              ...)  # 4 tiêu đề mục lấy theo kịch bản T1
    return prompt, bait_thuoc, bait_xn
```

`entities`: 12–15 cụm lấy từ kịch bản T1 (đã sinh sẵn cho đúng 1 chẩn đoán, nên
nhất quán về mặt y khoa — không trộn triệu chứng sớm/muộn của cùng bệnh vào 1 ca,
xem §9.3).

## 4. Neo nhãn sau khi LLM trả lời

```python
import re

def anchor_all(text, required):
    """PHƯƠNG ÁN B đã CHỐT: cho phép một cụm xuất hiện NHIỀU LẦN, gán nhãn
    HẾT các lần — không đòi "đúng 1 lần". Model hay nhắc lại triệu chứng ở
    phần trả lời (văn phong tự nhiên), và chính đề thi thật cũng lặp cùng
    một triệu chứng ở nhiều mục khác nhau.

    Khớp theo RANH GIỚI TỪ, không dùng str.find/`in` thuần — nếu không
    "sốt" sẽ ăn nhầm vào "sốt nhẹ", "hạ sốt".
    """
    ents, seen = [], 0
    for surface, etype in required:
        pat = r'(?<![\wÀ-ỹ])' + re.escape(surface) + r'(?![\wÀ-ỹ])'
        hits = list(re.finditer(pat, text, re.IGNORECASE))
        if hits:
            seen += 1
        for m in hits:
            ents.append({'text': text[m.start():m.end()], 'type': etype,
                         'position': [m.start(), m.end()]})
    if seen / len(required) < 0.6:      # < 60% cụm tìm thấy -> mẫu loãng
        return None                      # -> gọi nơi SINH LẠI, tối đa 3 lần
    return resolve_overlap(ents)         # cụm ngắn nằm trong cụm dài -> giữ cụm dài
```

`bait_thuoc`/`bait_xetnghiem` **không đưa vào `required`** — chúng có mặt trong
văn bản (LLM đã được yêu cầu chèn) nhưng **không được gán nhãn**, không cần tìm
lại offset. Đây chính là tín hiệu âm: model học "cụm này giống thực thể nhưng
không được gán".

`resolve_overlap`: dùng thẳng `select_non_overlapping` trong
`src/utils/overlap_resolver.py` (đã có, đã test).

## 5. Cổng kiểm định — trượt bất kỳ điều kiện nào thì loại mẫu, sinh lại

| # | Điều kiện | Ngưỡng |
|---|---|---|
| 1 | `text[start:end] == entity['text']` với mọi thực thể | 100% |
| 2 | Tỷ lệ số từ nằm trong thực thể | 8%–18% |
| 3 | Không có 2 span chồng lấn | 0 ca |
| 4 | Số cụm bắt buộc tìm thấy (mỗi cụm gán MỌI lần xuất hiện) | ≥60% |
| 5 | Quét từ điển ngược: không còn cụm DƯƠNG nào (§2) xuất hiện mà chưa gán nhãn | 0 sót |
| 6 | Không có chuỗi thuộc `am_thuoc_gia.txt`/`am_xetnghiem_gia.txt` bị gán nhãn | 0 ca |
| 7 | Độ dài file | 1.500–4.000 ký tự |
| 8 | Bait (`bait_thuoc`, `bait_xetnghiem`) có mặt trong text (kiểm bằng `in`, không bắt buộc gán) | — |
| 9 | Tỷ lệ mỗi loại lệch so với mục tiêu ở §6 | <15% |

Ghi log tỷ lệ loại theo từng cổng. **Loại >40% tổng thể → dừng, xem lại prompt**,
không hạ ngưỡng cổng để ép qua.

## 6. Phân bố mục tiêu

| Loại | Tỷ lệ | Số lượng (trên ~6.000) | Ghi chú |
|---|---|---|---|
| `TRIỆU_CHỨNG` | 33% | ~1.980 | |
| `CHẨN_ĐOÁN` | 25% | ~1.500 | phân tầng đủ 22 chương ICD |
| `THUỐC` | 16% | ~960 | 65% linkable / 35% không |
| `TÊN_XÉT_NGHIỆM` | 15% | ~900 | ≥40% không kèm kết quả |
| `KẾT_QUẢ_XÉT_NGHIỆM` | 11% | ~660 | trải đều 7 dạng viết |

Cấu trúc tài liệu: 65% văn xuôi + khối cấu trúc trộn, 25% chỉ văn xuôi, 10% chỉ
khối cấu trúc. Tổng ~500 file.

## 7. Quy tắc gán nhãn — chốt để nhất quán khi có xung đột

| Tình huống | Quy tắc |
|---|---|
| Liệt kê ngăn phẩy | Tách riêng từng cái. `Công thức máu, CRP, máu lắng` → 3 thực thể |
| Bổ ngữ vị trí | Lấy cả cụm. `đau bụng vùng hạ sườn phải` = 1 thực thể, không tách |
| Bổ ngữ hoàn cảnh | Bỏ, chỉ lấy lõi. `mệt mỏi khi gắng sức tuần qua` → chỉ `mệt mỏi` |
| Ngoặc giải thích | 2 thực thể riêng. `Rối loạn chuyển hóa tinh bột (amyloidosis)` → 2 |
| Hư từ ở biên | Cắt bỏ. `răng khôn hàm dưới **cho** mọc lệch` → bỏ "cho" |
| Phủ định có nêu khái niệm | VẪN gán khái niệm đó. `không sốt` → gán `sốt` (phủ định là việc của `assertions`, không phải NER) |
| Phủ định không nêu khái niệm cụ thể | KHÔNG gán gì. `không có tiền sử về bệnh` → bỏ qua |
| Chất vừa thuốc vừa xét nghiệm | Theo NGỮ CẢNH: có hàm lượng + đường dùng → THUỐC; có đơn vị đo/kết luận → TÊN_XÉT_NGHIỆM + KẾT_QUẢ. Áp dụng: glucose, albumin, creatinin, protein, calcium, kali, sắt, vitamin K, insulin |
| Nội dung giáo dục chung (bác sĩ giảng bệnh học, không phải ca cụ thể) | VẪN gán — dữ liệu đề thi thật có tính cả phần này (đo gián tiếp qua phân rã WER, không có bằng chứng ngược lại) |

## 8. Việc CẦN VIẾT (chưa có code, hoặc code cũ sai thiết kế)

1. `src/synth_noise.py` hiện tại **SAI THIẾT KẾ, phải viết lại từ đầu** theo §3.4/§4:
   bỏ hoàn toàn cơ chế "code tự tìm chỗ trống rồi chèn câu khuôn sau khi LLM sinh
   xong" (`inject_text_noise`, `inject_negative_bait` hiện tại). Thay bằng:
   sinh `n_glue`/`n_mask`/`bait_thuoc`/`bait_xetnghiem` **trước** khi gọi LLM,
   đưa vào prompt như tham số format string (§3.4).
2. Module tách hoạt chất từ RxNorm (§3.1, THUỐC nguồn 1) — chưa có.
3. Module phân tầng ICD theo 22 chương (§3.1, CHẨN_ĐOÁN) — chưa có.
4. Module dựng khối cấu trúc T2A (§3.3, phối `NUMBERING`/`BULLET`/`INDENT`...) — chưa có.
5. Module sinh `KẾT_QUẢ_XÉT_NGHIỆM` theo luật + ghép 8 format (§3.1) — chưa có.
6. `anchor_all` (§4) — CHƯA VIẾT. Khác với `verify_unit_entities` trong
   `src/span_anchor.py` (đó là cho pipeline suy luận V2, không phải cho sinh data).
7. Notebook Kaggle chạy Qwen3-8B qua vLLM để gọi T1 + T2B hàng loạt, ghi
   `output_json/*.json` đúng schema (xem `dataset2 - Copy/output_json/` làm mẫu
   format: mảng phẳng `[{text, type, position:[start,end]}]`).
8. Cổng kiểm định §5 gộp thành một hàm `validate_document(text, entities) -> bool`.

## 9. Việc ĐÃ CÓ, ĐÃ TEST — dùng thẳng, không viết lại

| File | Hàm dùng được | Test |
|---|---|---|
| `src/segment_units.py` | `segment_document()` — tách bullet/câu, gắn heading + zone | `test_segment_units` |
| `src/utils/overlap_resolver.py` | `select_non_overlapping()` | `test_overlap_resolver` |
| `src/branch_b_lab_tests.py` | whitelist `UNIT` (đơn vị đo xét nghiệm) | `test_branch_b` |
| `src/export_btc.py` | `validate()` (nguyên văn + không chồng lấn), `to_btc_format()` | `test_export_btc` |

Chạy `python test_local.py` từ thư mục gốc trước khi coi bất kỳ thay đổi nào là xong.

## 10. Thứ tự thi công

1. §3.1 các module T0 (không cần GPU)
2. `anchor_all` + cổng kiểm định §4–§5 (không cần GPU, viết test trước)
3. Module T2A khối cấu trúc (không cần GPU)
4. **Gán tay 5–10 file từ `input/*.txt` làm tập kiểm định** — việc này KHÔNG được bỏ qua,
   không có nó thì không biết data sinh ra có lệch phân bố với đề thi thật hay không
5. Viết lại `synth_noise.py` theo §8.1 + notebook Kaggle gọi T1/T2B
6. Chạy thử 20–30 file, soi tay, chỉnh ngưỡng cổng theo số đo thật (không đoán)
7. Chạy full ~500 file, train encoder, đo trên tập kiểm định bước 4
