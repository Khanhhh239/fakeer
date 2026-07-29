# Kế hoạch triển khai — NER y khoa tiếng Việt (encoder + thác phân loại)

> **Tài liệu này dành cho một agent chưa có bất kỳ ngữ cảnh nào về dự án.**
> Đọc hết Mục 0 và Mục 7 trước khi viết dòng code đầu tiên.
> Mọi con số trong tài liệu đều **đã được đo**, không phải ước lượng. Chỗ nào chưa đo thì có ghi rõ.

---

## 0. Bối cảnh và ràng buộc bất biến

### 0.1 Bài toán

Cuộc thi trích xuất thực thể y khoa từ **bệnh án tiếng Việt**. Đầu vào là văn bản thô, đầu ra là danh sách thực thể thuộc **đúng 5 loại**:

| type | nghĩa | ví dụ |
|---|---|---|
| `TRIỆU_CHỨNG` | biểu hiện bệnh nhân khai / bác sĩ quan sát | `nặng mặt`, `tiểu ít`, `đau vùng hạ sườn phải` |
| `CHẨN_ĐOÁN` | tên bệnh hoặc hội chứng quy cho bệnh nhân | `Hội chứng thận hư`, `Viêm cầu thận mạn` |
| `THUỐC` | tên thuốc, kèm hàm lượng nếu đi liền ngay sau | `Medrol 16mg`, `Furosemid 40 mg` |
| `TÊN_XÉT_NGHIỆM` | tên xét nghiệm / chỉ số / thăm dò — **chỉ phần tên** | `Ure`, `Creatinin`, `Điện giải`, `siêu âm ổ bụng` |
| `KẾT_QUẢ_XÉT_NGHIỆM` | giá trị đo được — **chỉ phần giá trị** | `6,4 mmol/l`, `52 g/l` |

### 0.2 Ràng buộc KHÔNG được vi phạm

1. **Chỉ được self-host model, cấm gọi API ngoài lúc chấm.** Không OpenAI, không Gemini, không API nào.
2. **Model self-host tối đa 9B tham số.** Qwen3-8B (8B) hợp lệ. Qwen2.5-7B hợp lệ. 14B/32B **không** hợp lệ.
3. **Span phải nguyên văn từng ký tự** như trong văn bản gốc — kể cả chữ hoa, dấu, khoảng trắng thừa. Metric có thành phần `0.3 × (1 − WER)`.
4. **Sai type bị phạt hai lần** (mất điểm ở type đúng, cộng lỗi ở type sai).
5. **Trích thừa bị phạt gấp 3.** Thà bỏ sót còn hơn trích bừa.

### 0.3 Vì sao dùng encoder + thác, không dùng thẳng LLM

Đã thử LLM thuần và **đo được** các thất bại sau — agent **không được** quay lại các cách này:

| cách đã thử | kết quả đo | kết luận |
|---|---|---|
| Prompt Qwen sinh tự do cả 5 type | Qwen3-8B **bịa 274 span** không có trong văn bản (61% output thô); model fine-tune bịa 98 (33%) | sinh tự do = bịa |
| Hỏi **từng type một** (5 lời gọi riêng) | **0/45 lượt** model chịu trả rỗng; `đau vùng hạ sườn phải` bị gán **cả 4 nhãn**; 175–199 thực thể trên tài liệu chỉ có ~40 | mất cạnh tranh giữa các type → mọi type nhận mọi span |
| Prompt có câu **cấm** ("không trích cách dùng thuốc") | phản tác dụng **3/3 lần**; model *thêm* đúng cái bị cấm vào span | **không dùng câu cấm trong prompt** |

**Nguyên lý rút ra — áp dụng xuyên suốt:** mọi quyết định phải là **chọn 1 trong N lựa chọn đối đầu nhau**, không bao giờ là "sinh ra thứ gì đó". Và mọi span phải **cắt ra từ văn bản gốc**, không bao giờ do model gõ ra.

---

## 1. Kiến trúc tổng thể

```
văn bản thô
   │
   ├── NHÁNH A — triệu chứng & chẩn đoán ───────────────────
   │   tách từ (PyVi) + GIỮ ÁNH XẠ OFFSET  ← Mục 4.2, chỗ dễ sai nhất
   │       ↓
   │   encoder BIO  →  span SYM_DIS          (chỉ MỘT nhãn)
   │       ↓ (ánh xạ ngược về offset văn bản gốc)
   │   thác 3 bậc ──→ TRIỆU_CHỨNG | CHẨN_ĐOÁN                    (Mục 4.3)
   │
   ├── NHÁNH B — xét nghiệm ────────────────────────────────
   │   luật regex trên văn bản gốc → TÊN_XÉT_NGHIỆM + KẾT_QUẢ    (Mục 4.4)
   │   (Qwen chỉ vá 2 ca luật không bắt được)
   │
   └── NHÁNH C — thuốc ─────────────────────────────────────
       khớp từ điển RxNorm + regex hàm lượng → THUỐC            (Mục 4.5)
   │
   └──→ hợp nhất, khử chồng lấn → JSON                          (Mục 4.6)
```

Ba nhánh **độc lập hoàn toàn**. Nhánh B và C không cần encoder, chạy và kiểm được ngay.

### 1.1 Vì sao chia ba nhánh

Đã khảo sát: **không dataset NER tiếng Việt công khai nào có type xét nghiệm.** Nên không thể fine-tune encoder cho `TÊN_XÉT_NGHIỆM` / `KẾT_QUẢ_XÉT_NGHIỆM` nếu không tự gán nhãn. Ngược lại, cấu trúc xét nghiệm trong bệnh án Việt rất đều (`TÊN: GIÁ_TRỊ ĐƠN_VỊ`) nên luật regex làm tốt — đã đo: gỡ được **11 tên + 11 giá trị** từ một bệnh án 2040 ký tự, **nguyên văn 100%**.

---

## 2. Dữ liệu

### 2.1 Nguồn — tải trực tiếp, không cần đăng ký

**PhoNER_COVID19** (NAACL 2021)
```
https://raw.githubusercontent.com/VinAIResearch/PhoNER_COVID19/main/data/word/train_word.conll
https://raw.githubusercontent.com/VinAIResearch/PhoNER_COVID19/main/data/word/dev_word.conll
https://raw.githubusercontent.com/VinAIResearch/PhoNER_COVID19/main/data/word/test_word.conll
```
Định dạng CoNLL BIO, một token một dòng, câu cách nhau bằng dòng trống:
```
Bộ	B-ORGANIZATION
Y_tế	I-ORGANIZATION
.	O
```
Có **10 type**, nhưng chỉ dùng **1**: `SYMPTOM_AND_DISEASE`. Chín type còn lại (`PATIENT_ID`, `PERSON_NAME`, `AGE`, `GENDER`, `OCCUPATION`, `LOCATION`, `ORGANIZATION`, `TRANSPORTATION`, `DATE`) **chuyển hết thành `O`**.

**ViMQ** (ICONIP 2021) — repo `tadeephuy/ViMQ`, **branch `master`** (không phải `main`)
```
https://raw.githubusercontent.com/tadeephuy/ViMQ/master/data/train.json
https://raw.githubusercontent.com/tadeephuy/ViMQ/master/data/dev.json
https://raw.githubusercontent.com/tadeephuy/ViMQ/master/data/test.json
```
Định dạng JSON, span theo **chỉ số TỪ** (không phải ký tự), **bao gồm cả hai đầu**:
```json
{
  "sentence": "Hẹp động_mạch thận phải có tiến_hành hiến thận được không ?",
  "seq_label": [[0, 2, "SYMPTOM_AND_DISEASE"], [6, 7, "medical_procedure"]],
  "sent_label": "method_diagnosis"
}
```
`[0, 2, X]` nghĩa là từ thứ 0 đến thứ 2 **tính cả từ thứ 2**. Kiểm lại: `sentence.split()[0:3]` = `Hẹp động_mạch thận`. **Agent phải tự verify điều này trên vài mẫu trước khi convert hàng loạt** — nếu hiểu sai bao gồm/không bao gồm thì toàn bộ nhãn lệch 1 từ.

Ba nhãn: `SYMPTOM_AND_DISEASE`, `medical_procedure`, `drug`. **Chỉ dùng `SYMPTOM_AND_DISEASE`.** Hai nhãn kia → `O` (lý do ở Mục 2.3).

Số lượng thật, đã đếm trên dữ liệu tải về: train 7.000 câu / 11.369 span, dev 1.000 câu / 1.647 span.

### 2.2 Nhãn hợp nhất — đúng 3 lớp

```
O
B-SYM_DIS   I-SYM_DIS
```

Ánh xạ:
| nguồn | nhãn gốc | → |
|---|---|---|
| PhoNER | `SYMPTOM_AND_DISEASE` | `SYM_DIS` |
| PhoNER | 9 type còn lại | `O` |
| ViMQ | `SYMPTOM_AND_DISEASE` | `SYM_DIS` |
| ViMQ | `medical_procedure` | `O` |
| ViMQ | `drug` | `O` — **xem cảnh báo dưới** |

### 2.3 ⚠️ KHÔNG train `DRUG` từ ViMQ — đã kiểm và không dùng được

Đếm thật trên dữ liệu tải về:

| tập | tổng span | `drug` | tỉ lệ |
|---|---|---|---|
| train | 11.369 | **686** | 6,0% |
| dev | 1.647 | **101** | 6,1% |

Nhưng vấn đề lớn hơn số lượng là **sai miền**. Đây là toàn bộ kiểu từ vựng `drug` của ViMQ (lấy nguyên từ train):

```
thuốc tránh thai khẩn_cấp · viên sủi vitamin C · thuốc hạ sốt
vắc-xin 6 trong 1 · sữa Anlene · Thuốc điều_trị huyết_áp · Thuốc imunoglukan
```

Đó là **cách bệnh nhân mô tả** trong câu hỏi tư vấn, không phải tên thuốc kê đơn. Mục tiêu của ta là `Medrol 16mg`, `Furosemid 40 mg`, `Zestril 10mg` — tên biệt dược/hoạt chất kèm hàm lượng trong đơn thuốc. `sữa Anlene` là một nhãn sữa.

Encoder train trên 686 mẫu kiểu đó **gần như chắc chắn không nhận ra `Medrol 16mg`**.

**Quyết định: `THUỐC` KHÔNG lấy từ encoder.** Chuyển sang khớp từ điển — xem Mục 4.5. Lý do thuyết phục: tên thuốc là **từ vựng đóng**, và đã có sẵn KB RxNorm 83.320 RxCUI / 129.690 tên. Từ điển + regex hàm lượng ăn đứt một encoder học từ 686 ví dụ sai miền.

Vậy encoder **chỉ còn một nhiệm vụ**: bắt span `SYM_DIS`. Đơn giản hơn, và đó cũng là nhãn có nhiều dữ liệu nhất (9.265 + toàn bộ PhoNER).

### 2.4 Cả hai dataset đều ĐÃ TÁCH TỪ

Cả hai đều ở dạng word-segmented, các âm tiết nối bằng `_`: `động_mạch`, `Y_tế`, `tiến_hành`.

Bệnh án đầu vào lúc inference thì **chưa tách**. Đây là nguồn lỗi lớn nhất của cả nhánh A — xử lý ở Mục 4.2.

---

## 3. NOTEBOOK 1 — Huấn luyện (`train_ner_encoder.ipynb`)

Chạy trên Kaggle, GPU T4 ×2 hoặc P100, Internet ON.

### 3.1 KHÔNG dùng code của repo tham chiếu

Repo `manhtt-079/vipubmed-deberta` có thư mục `reproduce/` trông như code train sẵn. **Không dùng.** Đã kiểm bằng cách chạy thật, `reproduce/covid/model.py` có hai lỗi chết:

```python
torch.nn.init.xavier_uniform_(self.classifier)
# AttributeError: 'Linear' object has no attribute 'dim'
# (truyền cả module thay vì .weight → model không dựng nổi)

self.loss_fct = nn.BCELoss()   # áp lên logit thô
# RuntimeError: all elements of input should be between 0 and 1
# (NER đa lớp phải là CrossEntropyLoss → loss không chạy nổi)
```

Thêm: `config.py` để `num_labels = 2` (sai, PhoNER cần 21), trỏ vào file `train_vi_refined.tsv` **không có trong bản phát hành** và không kèm script tạo, và `requirements.txt` pin `torch==1.13.0` / `transformers==4.25.1` từ 2022 — không cài được trên Kaggle hiện tại.

Kiến trúc của họ, bỏ lỗi đi, đúng bằng `AutoModel + Dropout + Linear` — tức là **chính xác** `AutoModelForTokenClassification`. Dùng cái đó.

### 3.2 Siêu tham số — lấy từ paper, giữ nguyên

```
learning_rate        2e-5
batch_size           16
max_length           256      # câu ngắn; 512 chỉ tổ chậm
epochs               10
warmup_ratio         0.05
weight_decay         0.015
adam_epsilon         1e-9
classifier_dropout   0.2
max_grad_norm        1.0
seed                 42
early stopping       theo micro-F1 trên dev, patience 3
```

### 3.3 Model — dùng ViPubmedDeBERTa làm chính

| model | HF id | tình trạng đã kiểm |
|---|---|---|
| **ViPubmedDeBERTa** ✅ | `manhtt-079/vipubmed-deberta-base` | **dùng cái này.** Đã thử nạp: `AutoTokenizer` chạy, `word_ids()` hoạt động, 86M tham số |
| ViHealthBERT ⚠️ | `demdecuong/vihealthbert-base-word` | **tokenizer KHÔNG phải fast** — `word_ids()` ném `ValueError: word_ids() is not available when using non-fast tokenizers`. Muốn dùng phải tự viết căn nhãn subword thủ công |

Đã kiểm bằng cách chạy thật trên `transformers 5.3.0`. ViPubmedDeBERTa vừa có tokenizer chạy được, vừa cao điểm hơn trong paper (80.65 vs 78.26 trên ViMQ-NER). **Bắt đầu bằng ViPubmedDeBERTa. Chỉ đụng tới ViHealthBERT nếu còn thời gian**, và khi đó phải tự căn nhãn thủ công.

Số tham chiếu từ paper (micro-F1, **in-domain**): ViPubmedDeBERTa-base đạt **80.65** trên ViMQ-NER, ViHealthBERT **78.26**. Trên PhoNER thì cả hai ~94, **nhưng đừng lấy số đó làm mốc** — PhoNER có 9/10 type là mẫu bề mặt (tuổi, ngày, địa điểm) nên dễ. Mốc đúng cho bài này là **~80**.

### 3.4 Căn nhãn theo subword

Tokenizer chia một từ thành nhiều subword. Quy tắc:
- subword **đầu tiên** của từ giữ nhãn của từ đó
- các subword **sau** đặt nhãn `-100` (PyTorch bỏ qua khi tính loss)
- token đặc biệt (`[CLS]`, `[SEP]`, padding) đặt `-100`

Dùng `tokenizer(..., is_split_into_words=True)` rồi `word_ids()` để căn. Đây là cách chuẩn, đừng tự viết lại.

### 3.5 Đánh giá

Dùng `seqeval` với chế độ **strict, scheme IOB2**. Chỉ có một nhãn thực thể (`SYM_DIS`) nên micro-F1 là đủ.

Báo **riêng F1 trên phần dev của PhoNER** và **phần dev của ViMQ**. Hai miền rất khác nhau (tin tức COVID vs câu hỏi bệnh nhân); nếu một bên cao một bên thấp thì phải biết, vì miền đích của ta — bệnh án lâm sàng — không giống bên nào.

### 3.6 Đầu ra của notebook 1

Lưu vào `/kaggle/working/` để tải về rồi upload lại thành Kaggle Dataset cho notebook 2:

```
/kaggle/working/ner_encoder/
  ├── config.json
  ├── model.safetensors            (dùng save_pretrained, KHÔNG lưu .bin)
  ├── tokenizer.json / vocab.txt / bpe.codes ...   (tokenizer.save_pretrained)
  ├── label_map.json               {"O":0,"B-SYM_DIS":1,"I-SYM_DIS":2}
  └── metrics.json                 {"model":..., "dev_micro_f1":..., "per_label":{...}}
```

In rõ ra cuối notebook: model nào thắng, F1 bao nhiêu, để người dùng biết chọn cái nào.

---

## 4. NOTEBOOK 2 — Inference đầu-cuối (`ner_inference_e2e.ipynb`)

**Đầu vào:** một ô text để dán bệnh án thô. **Đầu ra:** JSON theo schema Mục 5.

Kaggle input cần add **ba** thứ:
1. weight từ notebook 1 (Kaggle Dataset)
2. `icd10_vi_full.csv` — KB ICD, cho Mục 4.3
3. `rxnorm_merged.csv` + `inn_usan.csv` — KB thuốc, cho Mục 4.5

### 4.1 Bố cục notebook

```
cell 1  cài đặt (transformers, pyvi, sentence-transformers, vllm) + verify
cell 2  TEXT = """<ô dán bệnh án>"""
cell 3  NHÁNH B: luật xét nghiệm            ← chạy ngay, không cần model
cell 4  NHÁNH C: khớp từ điển RxNorm → THUỐC ← chạy ngay, không cần model
cell 5  NHÁNH A bước 1: tách từ + ánh xạ offset  (assert ok TRƯỚC khi đi tiếp)
cell 6  NHÁNH A bước 2: encoder → span SYM_DIS
cell 7  NHÁNH A bước 3: thác tách triệu chứng/bệnh
cell 8  hợp nhất + khử chồng lấn + xuất JSON
cell 9  checklist nghiệm thu (Mục 7) — BẮT BUỘC
```

### 4.2 ⚠️ Ánh xạ offset — chỗ dễ sai nhất toàn dự án

**Vấn đề:** encoder được train trên text đã tách từ (`động_mạch`), nhưng span cuối cùng phải là offset trong **văn bản gốc chưa tách**. PyVi vừa nối âm tiết vừa có thể chuẩn hoá khoảng trắng, nên không thể lấy offset trong text đã tách rồi dùng thẳng.

**Giải pháp bắt buộc — khớp theo KÝ TỰ đã chuẩn hoá NFC, không khớp theo token.**

Hàm dưới đây **đã được chạy thử trên toàn bộ 100 bệnh án thật: 100/100 đúng, 0 lỗi.** Dùng nguyên văn, đừng viết lại.

```python
from pyvi import ViTokenizer
import unicodedata as ud

def dense_chars(raw: str):
    """Mỗi phần tử = MỘT ký tự hiển thị (đã gộp dấu tổ hợp) + span gốc của nó.
       Bỏ khoảng trắng."""
    out, i = [], 0
    while i < len(raw):
        if raw[i].isspace():
            i += 1
            continue
        j = i + 1
        while j < len(raw) and ud.combining(raw[j]):   # gộp dấu thanh rời
            j += 1
        out.append((ud.normalize('NFC', raw[i:j]), i, j))
        i = j
    return out

def segment_with_map(raw: str):
    """
    -> (words, spans, ok)
       words[i] : từ thứ i sau tách từ (có thể chứa '_')
       spans[i] : (start, end) — offset trong RAW của đúng từ đó
       ok       : True nếu phủ hết văn bản. False = ánh xạ HỎNG, phải dừng.
    """
    dense = dense_chars(raw)
    seg = ViTokenizer.tokenize(raw).split()
    words, spans, p = [], [], 0
    for st in seg:
        core = list(ud.normalize('NFC', st.replace('_', '')))
        if p + len(core) > len(dense):
            break
        if [c for c, _, _ in dense[p:p + len(core)]] != core:
            break                       # lệch -> dừng, KHÔNG đi tiếp
        words.append(st)
        spans.append((dense[p][1], dense[p + len(core) - 1][2]))
        p += len(core)
    return words, spans, p == len(dense)
```

**Bốn điều tuyệt đối không được làm:**
1. **Không** giả định "mỗi từ đã tách nuốt `count('_')+1` token thô". **Sai** — PyVi tách dấu câu thành token riêng: `tuổi,` là 1 token thô nhưng thành 2 token sau tách. Cách này đã được thử và cho kết quả lệch từ token thứ 3 (`'tuổi'` → `'tuổi,'`, rồi `','` → `'vào'`).
2. **Không** so sánh ký tự trực tiếp mà bỏ qua chuẩn hoá NFC. Văn bản đề dùng Unicode **tổ hợp (NFD)** — `ó` là 2 codepoint — còn PyVi trả về **NFC** — `ó` là 1 codepoint. Bỏ qua điều này thì **20/100 file hỏng** (đã đo).
3. **Không** `ViTokenizer.tokenize` rồi `raw.find(span_text)` — chuỗi lặp lại nhiều lần sẽ khớp nhầm chỗ.
4. **Không** bỏ qua `ok == False`. Nếu ánh xạ vỡ thì mọi offset sau đó sai, và sai **âm thầm**. Bắt buộc:
   ```python
words, spans, ok = segment_with_map(TEXT)
assert ok, "ánh xạ offset HỎNG — dừng, không được chạy tiếp"
```

Sau khi encoder trả span theo **chỉ số từ** `[i, j]`, offset gốc là `(spans[i][0], spans[j][1])`, và text cuối cùng **luôn lấy bằng `raw[start:end]`** — không bao giờ lấy từ output của model.

### 4.3 Thác tách `SYM_DIS` → `TRIỆU_CHỨNG` / `CHẨN_ĐOÁN`

Nguồn KB: file ICD-10 tiếng Việt, 14.792 mã / 17.094 tên. Người dùng có sẵn tại `Medical/data/kb/icd10_vi_full.csv`, cần upload thành Kaggle Dataset. Cột: mã ICD + tên tiếng Việt.

Encoder nhúng: `AITeamVN/Vietnamese_Embedding`.

**Thác 3 bậc, mỗi bậc chỉ nhận phần bậc trước không quyết nổi:**

```
span SYM_DIS
  ├─ bậc 1: top-1 ICD thuộc chương R (mã bắt đầu bằng 'R')  → TRIỆU_CHỨNG
  ├─ bậc 2: top-1 ngoài chương R VÀ cosine ≥ 0.93           → CHẨN_ĐOÁN
  └─ bậc 3: còn lại → hỏi Qwen, chọn nhị phân A/B
```

**Số đã đo** (30 ví dụ, dùng ICD chương R = "Triệu chứng, dấu hiệu"):

| | kết quả |
|---|---|
| luật chương R áp cho **mọi** span | 73,3% — **không dùng kiểu này** |
| chỉ bậc 1 (khớp chương R → triệu chứng) | **7/7 đúng** |
| chỉ bậc 2 (ngoài R, sim ≥ 0.93 → bệnh) | **11/11 đúng, 0 triệu chứng lọt vào** |
| hai bậc quyết được | **18/30 = 60% ở độ chính xác 100%** |

**Vì sao không dùng KB cho tất cả:** chương R trong KB chỉ có **495 tên trên 17.094**. Từ ngữ triệu chứng đời thường tiếng Việt (`nặng mặt`, `tức nặng 2 chi dưới`, `tiểu ít`) **không tồn tại trong ICD**. Retriever không có quyền nói "không có trong KB" nên luôn trả hàng xóm gần nhất, mà 97% KB là bệnh → nó đoán bệnh. Ví dụ thật:

```
nặng mặt              -> Q67.1 Mặt bị ép              (0.676)  SAI
tiểu ít               -> D69.6 giảm tiểu cầu           (0.695)  SAI
đau vùng hạ sườn phải -> M54.2 Đau vùng cổ gáy         (0.585)  SAI
```

Ngưỡng cosine **không** tách được hai nhóm (triệu chứng 0.585–1.000, bệnh 0.711–1.001, chồng lấn hoàn toàn). Nên **chỉ dùng KB ở vùng nó chắc chắn**, phần còn lại đưa Qwen.

**Cảnh báo:** ngưỡng `0.93` rút ra từ 30 ví dụ do người thiết kế tự chọn. Đây là **tín hiệu, không phải nghiệm thu**. Phải hiệu chỉnh lại khi có gold. Agent **không được** báo cáo con số 100% như thể đã được kiểm chứng.

**Prompt cho bậc 3** — nhị phân, ràng buộc cứng:

```python
system = (
  "Bạn là bác sĩ. Với cụm từ được trích từ bệnh án, hãy chọn đúng một nhãn:\n"
  "A. TRIỆU_CHỨNG — biểu hiện bệnh nhân khai hoặc bác sĩ quan sát được trên người bệnh\n"
  "B. CHẨN_ĐOÁN — tên một bệnh hoặc hội chứng được quy cho bệnh nhân\n"
  "Chỉ trả về một chữ cái."
)
user = f"Đoạn: «{cau_chua_cum}»\n\nCụm: «{span}»\n\nNhãn:"
```

Bắt buộc dùng constrained decoding:
```python
from vllm.sampling_params import StructuredOutputsParams
SamplingParams(temperature=0, max_tokens=4, logprobs=20,
               structured_outputs=StructuredOutputsParams(choice=["A", "B"]))
```
Đọc phân phối ở token sinh **đầu tiên** rồi tự chuẩn hoá trên đúng `{A, B}` để có độ tin cậy. Không tin `cumulative_logprob` là đã chuẩn hoá — chưa kiểm chứng được điều đó.

**Model cho bậc 3:** `Qwen/Qwen3-8B` (8B, hợp lệ). Đặt `enable_thinking=False` khi gọi `apply_chat_template`. Nếu OOM thì dùng `Qwen/Qwen2.5-7B-Instruct`.

### 4.4 Nhánh B — luật xét nghiệm

Chạy trực tiếp trên **văn bản gốc**, không qua tách từ, nên không dính vấn đề offset.

**Bước 1 — cắt đoạn.** Tách ở `\n`, `;`, `:`, dấu chấm câu, và **dấu phẩy không nằm giữa hai chữ số**:
```python
SPLIT = re.compile(r'(?<!\d),(?!\d)|[;:\n]|(?<=[a-zA-ZÀ-ỹ])\.(?=\s|$)')
```
`(?<!\d),(?!\d)` là bắt buộc: `4,49 T/l` là số thập phân tiếng Việt, cắt ở dấu phẩy đó là hỏng.

Coi `:` là ranh giới đoạn có chủ ý — `Ure: 6,4 mmol/l` tự tách thành `Ure` + `6,4 mmol/l`, **đúng hai thực thể cần tách**.

**Bước 2 — bắt cặp tên/giá trị:**
```python
_SEP = re.compile(r'^(.{1,40}?)\s*[:\-=–]\s*([\d.,]+\s*[a-zA-ZÀ-ỹ/%µ]*)$'
                  r'|^(.{1,40}?)\s+([\d.,]+\s*[a-zA-ZÀ-ỹ/%µ]*)$')
```
Khi làm sạch phần tên: **không được `rstrip('-')`** — `Cl-`, `HCO3-` là tên ion, dấu trừ là một phần của tên. Đã từng mất điểm vì lỗi này. Dùng:
```python
def clean_name(n):
    return n.strip().lstrip(':-=–').rstrip(':=–').strip()
```

**Bước 3 — Qwen vá đúng hai ca luật không bắt được:**
- tên xét nghiệm **không kèm giá trị**: `protein niệu 24h`, `siêu âm ổ bụng`, `điện giải đồ`
- giá trị **phi số**: `(–)`, `HC (–)`, `Trụ niệu (–)`

Cách vá: sinh ứng viên n-gram từ các đoạn **chưa được luật dùng đến**, rồi hỏi Qwen chọn 1 trong 3 — `TÊN_XÉT_NGHIỆM` / `KẾT_QUẢ_XÉT_NGHIỆM` / `KHÔNG_PHẢI`. Vẫn là chọn, không phải sinh.

### 4.5 Nhánh C — `THUỐC` bằng khớp từ điển

Chạy trên **văn bản gốc**, không qua tách từ.

**Nguồn từ điển:** RxNorm đã dựng sẵn, **83.320 RxCUI / 129.690 tên**, tại `Medical/data/kb/rxnorm_merged.csv` — upload thành Kaggle Dataset. Kèm `Medical/data/kb/inn_usan.csv` (36 cầu nối INN↔USAN, ví dụ `paracetamol` ↔ `acetaminophen`).

**Thuật toán:**

1. **Khớp tên** — quét mọi n-gram ≤ 5 từ trong văn bản, đối chiếu từ điển RxNorm đã chuẩn hoá (bỏ dấu, thường hoá). Ưu tiên khớp **dài nhất**.
2. **Nối hàm lượng** — nếu ngay sau tên có hàm lượng thì span **kết thúc ngay sau hàm lượng**:
   ```python
STRENGTH = re.compile(r'^\s*\d+(?:[.,]\d+)?\s*'
                      r'(?:mg|g|mcg|µg|ml|l|ui|iu|%)\b', re.I)
```
   `Medrol 16mg x 3 viên, uống 8h sáng` → span đúng là `Medrol 16mg`. Phần `x 3 viên, uống…` **nằm ngoài**.
3. **Vá bằng LLM** — tên không có trong RxNorm (biệt dược Việt Nam) thì từ điển bỏ sót. Sinh ứng viên n-gram từ các dòng **thuộc mục đơn thuốc chưa được khớp**, hỏi Qwen chọn `THUỐC` / `KHÔNG_PHẢI`. Vẫn là chọn, không phải sinh.

**Vì sao tin cách này hơn encoder:** tên thuốc là **từ vựng đóng và hữu hạn**, đúng loại bài toán mà từ điển thắng học máy. Ngược lại ViMQ chỉ có 686 ví dụ `drug` và toàn sai miền (Mục 2.3).

**Số liệu tham chiếu:** pipeline liên kết thuốc dùng chính KB này đã đo được **96% chính xác** trên tác vụ tên→RxCUI. Nhưng đó là đo **liên kết**, không phải đo **phát hiện span** — đừng nhầm hai con số.

### 4.6 Hợp nhất và khử chồng lấn

Sau khi có tất cả span từ cả hai nhánh, **mỗi ký tự chỉ được thuộc tối đa một thực thể**. Dùng quy hoạch động (weighted interval scheduling), nghiệm tối ưu chính xác:

```python
def select_non_overlapping(items):
    """items: [{'start','end','score',...}] -> tập con không chồng lấn, tổng score cực đại"""
    import bisect
    items = sorted(items, key=lambda x: x['end'])
    ends = [x['end'] for x in items]
    n = len(items)
    dp, back = [0.0] * (n + 1), [None] * (n + 1)
    for i in range(1, n + 1):
        it = items[i - 1]
        j = bisect.bisect_right(ends, it['start'], 0, i - 1)
        if it['score'] + dp[j] > dp[i - 1]:
            dp[i], back[i] = it['score'] + dp[j], ('take', j)
        else:
            dp[i], back[i] = dp[i - 1], ('skip', i - 1)
    out, i = [], n
    while i > 0:
        act, j = back[i]
        if act == 'take':
            out.append(items[i - 1])
        i = j
    return out[::-1]
```

Điểm để so sánh: span từ encoder dùng xác suất softmax trung bình của các token trong span; span từ luật xét nghiệm đặt điểm cao (ví dụ `1.0`) vì luật tất định; span từ Qwen dùng hậu nghiệm đã chuẩn hoá.

---

## 5. Schema JSON đầu ra

```json
{
  "text": "<nguyên văn bệnh án đầu vào, không sửa gì>",
  "entities": [
    {
      "text": "Hội chứng thận hư",
      "type": "CHẨN_ĐOÁN",
      "start": 89,
      "end": 106,
      "score": 0.97,
      "source": "encoder+kb"
    }
  ]
}
```

- `type` ∈ đúng 5 giá trị ở Mục 0.1, viết hoa có dấu, **không được có giá trị nào khác**
- `start`/`end` là offset ký tự trong `text`, nửa mở `[start, end)`
- `text` của thực thể **phải bằng đúng** `text[start:end]`
- `source` ∈ `encoder`, `encoder+kb`, `encoder+llm`, `rule`, `llm` — để truy vết khi debug
- danh sách sắp theo `start` tăng dần

Xuất ra `/kaggle/working/ner_output.json`.

---

## 6. Bẫy đã biết — đọc kỹ, đây là chỗ agent trước đã sai

| # | bẫy | hậu quả đã đo | cách tránh |
|---|---|---|---|
| 1 | Lấy text thực thể từ **output của model** | 274 span bịa | **Luôn** lấy bằng `raw[start:end]` |
| 2 | Hỏi LLM từng type riêng biệt | 0/45 lượt trả rỗng, 1 span nhận 4 nhãn | Luôn cho các lựa chọn **đối đầu** trong cùng một câu hỏi |
| 3 | Dùng câu **cấm** trong prompt | phản tác dụng 3/3 lần | Chỉ viết định nghĩa khẳng định + ví dụ |
| 4 | `.split()` để lấy offset | lệch offset khi có khoảng trắng thừa | `re.finditer(r'\S+', raw)` |
| 5 | `rstrip('-')` khi làm sạch tên | `Cl-` thành `Cl`, sai nguyên văn | Dùng `clean_name` ở Mục 4.4 |
| 6 | Cắt đoạn ở mọi dấu phẩy | `4,49 T/l` bị vỡ | `(?<!\d),(?!\d)` |
| 7 | Dùng `reproduce/` của repo tham chiếu | 2 lỗi chết, không chạy được | `AutoModelForTokenClassification` |
| 8 | Lấy F1 94.76 của PhoNER làm mốc | kỳ vọng sai | Mốc đúng là **~80** (ViMQ-NER) |
| 9 | Bỏ qua `assert ok` khi ánh xạ lệch | offset sai **âm thầm** | Để `assert` dừng hẳn |
| 10 | Báo cáo ngưỡng 0.93 như đã kiểm chứng | tự lừa mình | Ghi rõ: 30 ví dụ tự chọn, chưa có gold |
| 11 | **Bỏ qua chuẩn hoá NFC khi so ký tự** | **20/100 file hỏng ánh xạ** | Văn bản đề là **NFD**, PyVi trả **NFC** — dùng `dense_chars` ở Mục 4.2 |
| 12 | Căn từ đã tách theo **số token thô** | lệch từ token thứ 3 trở đi (`'tuổi'`→`'tuổi,'`) | Căn theo **ký tự**, xem Mục 4.2 |
| 13 | Train nhãn `DRUG` từ ViMQ | 686 mẫu, sai miền (`sữa Anlene`) | Dùng từ điển RxNorm, Mục 4.5 |
| 14 | Dùng ViHealthBERT với `word_ids()` | `ValueError: not available when using non-fast tokenizers` | Dùng ViPubmedDeBERTa, Mục 3.3 |

### 6.1 Ba việc phải làm ĐẦU TIÊN, trước khi viết code chính

Cả ba đều rẻ và cả ba đều đã từng lộ ra lỗi chết người:

1. Chạy `segment_with_map` (Mục 4.2) trên **toàn bộ** bệnh án đầu vào, đếm số file `ok == False`. Phải là **0**. Đã kiểm: hàm trong tài liệu cho 100/100.
2. Nạp thử `AutoTokenizer` của model định dùng và gọi `word_ids()` một lần. Nếu ném lỗi thì đổi model, đừng viết vòng qua.
3. Kiểm quy ước span ViMQ trên 5 mẫu: `[i, j]` **bao gồm cả hai đầu**, tức `words[i : j+1]`. Đã kiểm trên 1.647 span của dev — không span nào có `j >= len(words)`, xác nhận là bao gồm.

---

## 7. Checklist nghiệm thu — chạy trước khi báo cáo xong

Notebook 2 phải có một cell cuối chạy **toàn bộ** các assert sau. Cái nào vỡ thì báo lỗi, **không được** báo hoàn thành:

```python
ents = result["entities"]
T = result["text"]

# 1. nguyên văn — bất biến quan trọng nhất
assert all(e["text"] == T[e["start"]:e["end"]] for e in ents), "span KHÔNG nguyên văn"

# 2. không chồng lấn
o = sorted(ents, key=lambda x: x["start"])
assert all(o[i]["end"] <= o[i+1]["start"] for i in range(len(o)-1)), "có span CHỒNG LẤN"

# 3. type hợp lệ
VALID = {"TRIỆU_CHỨNG","CHẨN_ĐOÁN","THUỐC","TÊN_XÉT_NGHIỆM","KẾT_QUẢ_XÉT_NGHIỆM"}
assert all(e["type"] in VALID for e in ents), "có type LẠ"

# 4. không span rỗng, không span chỉ có khoảng trắng
assert all(e["text"].strip() for e in ents), "có span RỖNG"

# 5. offset hợp lệ
assert all(0 <= e["start"] < e["end"] <= len(T) for e in ents), "offset SAI"
```

Ngoài ra in ra để người dùng tự đọc:
- số thực thể **theo từng type** — bệnh án ~2000 ký tự nên cho ra **cỡ 35–45 thực thể**. Nếu ra trên 100 là có gì đó hỏng (đã từng ra 175–199 khi thiết kế sai).
- **số span mỗi bậc của thác quyết định** (KB bậc 1 / KB bậc 2 / Qwen) — nếu Qwen phải quyết trên 80% thì KB không đóng góp gì, cần xem lại.
- **số span luật xét nghiệm bắt được** vs số Qwen phải vá.

---

## 8. Thứ tự thực hiện đề nghị

1. **Mục 6.1** — ba phép kiểm mở màn. Khoảng 15 phút, chặn được cả bốn lỗi chết đã biết.
2. **Nhánh B** (Mục 4.4) và **Nhánh C** (Mục 4.5) — không cần model, không cần train, xong trong một buổi. Đây đã là 3/5 type. Cho kết quả thật để đối chiếu về sau.
3. **Notebook 1** — train encoder cho .
4. **Nhánh A** trong notebook 2 —  **trước**, có test riêng, rồi mới nối vào encoder.
5. **Thác tách triệu chứng/bệnh** — bậc 1 và 2 trước (không cần LLM), đo tỉ lệ quyết được, rồi mới thêm Qwen.
6. Hợp nhất + checklist Mục 7.

Thứ tự này có chủ ý: **ba type dễ nhất (thuốc, tên xét nghiệm, kết quả xét nghiệm) xong trước và không phụ thuộc GPU.** Nếu hết thời gian thì vẫn có một hệ chạy được cho 3/5 type, thay vì một hệ dở dang cho cả 5.

---

## 9. Việc CHƯA làm — đừng tự ý làm thêm, hãy báo lại

- **Chưa có gold thủ công.** Mọi con số trong tài liệu này là đo từng phần (độ phủ, độ chính xác KB trên mẫu tự chọn), **không phải điểm cuối**. Không được suy ra chất lượng tổng thể.
- **Assertion (phủ định) chưa xử lý.** `Không có suy thận` hiện được gán nhãn span nhưng không quyết định phủ định. Đây là **0,3 trọng số** của metric, làm riêng.
- **Liên kết ID (ICD/RxNorm) là bước sau**, không thuộc phạm vi hai notebook này. Đã có pipeline riêng.
- Nếu thấy có cách làm tốt hơn ở đâu đó trong tài liệu này, **báo lại trước khi đổi**. Nhiều lựa chọn trông kỳ quặc ở đây là kết quả của một phép đo cụ thể đã ghi trong Mục 6.
