# Trạng thái dự án & Cách hoạt động — Medical NER Vietnamese

> Bản này thay cho bản "100% COMPLETE" trước — bản đó có 2 nhánh bắt sai gần hết
> (0/11 xét nghiệm, RxNorm tụt còn 68 từ) và bộ test có ca "pass rỗng" (báo PASS dù
> trích được 0 thực thể) mà vẫn tự nhận hoàn thành. Bản này chỉ ghi điều **đã chạy
> và thấy kết quả**, không ghi điều "chắc là ổn".

## 1. Trạng thái từng phần — đã kiểm bằng cách chạy thật

| phần | trạng thái | bằng chứng |
|---|---|---|
| Nhánh B — xét nghiệm | ✅ đúng | `36.txt`: 11/11 tên xét nghiệm thật, 0 rác, offset khớp nguyên văn trên cả 100 file |
| Nhánh C — thuốc | ✅ đúng | `36.txt`: 4/4 thuốc (`Medrol 16mg`, `Omez 20mg`, `Furosemid 40 mg`, `Zestril 10mg`), offset khớp trên cả 100 file |
| Ánh xạ offset (PyVi + NFC) | ✅ đúng | 100/100 file, không lệch |
| `ner_metrics.py` (thay seqeval) | ✅ đúng | 7/7 test tay + chạy thật trong `Trainer.compute_metrics` |
| Chuyển dữ liệu train (PhoNER + ViMQ) | ✅ đúng | PhoNER 5.027/2.000/3.000 câu, ViMQ 7.000/1.000/1.000 câu |
| Nạp model + 1 bước train + eval | ✅ đúng | chạy thật trên CPU với `manhtt-079/vipubmed-deberta-base`, ra loss + F1 hợp lệ |
| Overlap resolver (QHĐ) | ✅ đúng | chọn `sốt cao` bỏ `sốt`, đúng thiết kế |
| `negation_detector.py` | ✅ đúng, **nhưng API 2 bước** | 10/10 test riêng; đo lại trên `36.txt`: `suy thận`/`thiếu máu`/`viêm họng cấp` → `negated`, `Hội chứng thận hư` → `affirmed`. Xem lưu ý cách gọi ở Mục 4.4 |
| `llm_classifier.py` (Tier 3) | ⚠️ **chưa chạy được lần nào** | chỉ mới kiểm cú pháp + import OK. Cần GPU, chưa test — đừng tin nhãn "Manual test OK" ở bản cũ, không rõ nó test cái gì |
| Train encoder trên Kaggle (GPU thật, full epoch) | ⚠️ **chưa chạy** | mọi thứ đã kiểm ở quy mô nhỏ trên CPU; chưa có lần chạy đủ 10 epoch / dữ liệu đầy đủ trên GPU |

## 2. Ba lỗi vừa sửa trong `train_ner_encoder.ipynb` — vì sao chúng xảy ra

Log training thật đầu tiên vỡ ở cell 6 với:
```
TypeError: DebertaV2ForTokenClassification.__init__() got an unexpected keyword argument 'classifier_dropout'
```

**Nguyên nhân:** siêu tham số `classifier_dropout: 0.2` trong `KEHOACH_NER.md` chép thẳng từ repo tham chiếu — nhưng đó là tham số kiểu **BERT/RoBERTa**. Đã kiểm thật: `DebertaV2Config` không có field này, chỉ có `hidden_dropout_prob` dùng **chung cho toàn bộ encoder** (8 chỗ trong mã nguồn HF), không tách riêng cho đầu phân loại. DeBERTaV2 không có khái niệm "classifier dropout" độc lập. Sửa: bỏ hẳn tham số này, dùng dropout mặc định của checkpoint đã pretrain (0.1).

Sửa xong, chạy tiếp lộ lỗi thứ hai:
```
TypeError: Trainer.__init__() got an unexpected keyword argument 'tokenizer'
```
`transformers` bản cài trên Kaggle (5.3.0) đã đổi tên `tokenizer=` thành `processing_class=` trong `Trainer`. Sửa: đổi tên tham số.

Cả hai lỗi đã **chạy thật lại từ đúng nội dung notebook** (không phải đoán rồi sửa mù): nạp model 183.757.059 tham số, `Trainer` khởi tạo được, `train()` + `evaluate()` chạy ra kết quả hợp lệ.

**Lỗi thứ ba, chỉ cảnh báo, chưa chặn:** `warmup_ratio` bị đánh dấu deprecated ở bản `transformers` mới hơn. Hiện tại (5.3.0) vẫn chạy được, chỉ in cảnh báo. Không sửa vì chưa hỏng — nhưng nếu Kaggle tự nâng cấp `transformers` sau này mà lỗi này tái xuất hiện thì đây là nguyên nhân.

## 3. Pipeline — cách hoạt động, đúng theo `KEHOACH_NER.md`

### 3.1 Tổng quan 3 nhánh độc lập

```
văn bản thô
   │
   ├── NHÁNH A — triệu chứng & chẩn đoán
   │   PyVi tách từ + giữ ánh xạ offset  (src/utils/text_alignment.py)
   │       ↓
   │   encoder BIO (ViPubmedDeBERTa fine-tune) → span SYM_DIS  [CHƯA TRAIN XONG]
   │       ↓
   │   thác 3 bậc → TRIỆU_CHỨNG | CHẨN_ĐOÁN     (src/cascade_classifier.py)
   │
   ├── NHÁNH B — xét nghiệm (src/branch_b_lab_tests.py)
   │   luật ghép "đoạn liền kề" → TÊN_XÉT_NGHIỆM + KẾT_QUẢ_XÉT_NGHIỆM
   │
   └── NHÁNH C — thuốc (src/branch_c_drugs.py)
       khớp từ điển RxNorm + luật cấu trúc (thuốc ngoài từ điển) → THUỐC
   │
   ├── negation_detector.py — gắn assertion (affirmed/negated) cho từng thực thể
   └── overlap_resolver.py  — quy hoạch động, chọn tập không chồng lấn, điểm cực đại
   │
   └──→ JSON 5 type
```

### 3.2 NHÁNH B — xét nghiệm, chi tiết cách nó ra kết quả

Nguyên lý: **không ghép tên/giá trị bằng regex bên trong một đoạn** (bước tách đoạn đã cắt ở `:`, nên trong đoạn không còn cặp nào để ghép — đây chính là bug đã sửa). Thay vào đó:

1. Tách văn bản thành đoạn ở `\n` `;` `:` và dấu phẩy **không nằm giữa hai chữ số** (`4,49` là số thập phân).
2. Đoạn nào **là** "số + đơn vị y khoa" (`VALUE_ONLY` — danh sách trắng gồm `mmol/l`, `g/l`, `T/l`...) → gán `KẾT_QUẢ_XÉT_NGHIỆM`.
3. Đoạn **ngay trước nó** → gán `TÊN_XÉT_NGHIỆM`, nếu dài ≤ 40 ký tự và có ít nhất một chữ cái.

Ví dụ thật (`36.txt`): `"Ure: 6,4 mmol/l"` → tách đoạn `"Ure"` + `"6,4 mmol/l"` → đoạn 2 khớp `VALUE_ONLY` → gán `KẾT_QUẢ`, đoạn 1 đứng trước → gán `TÊN`.

### 3.3 NHÁNH C — thuốc, chi tiết cách nó ra kết quả

1. **Khớp từ điển**: quét n-gram ≤ 5 từ trong văn bản, đối chiếu 138.361 tên đã nạp từ `rxnorm_merged.csv` (129.690 dòng gốc + biến thể tự sinh: RxNorm ghi kiểu Anh `furosemide`, bệnh án Việt viết `furosemid` — rụng `-e` cuối, nạp cả hai dạng).
2. **Nối hàm lượng**: nếu ngay sau tên có `<số><đơn vị khối lượng>` (`STRENGTH`, ví dụ `mg`, `g`, `%`) thì span kéo dài đến hết hàm lượng. `Medrol 16mg x 3 viên` → span dừng ở `Medrol 16mg`, không nuốt `x 3 viên`.
3. **Chất lưỡng dụng** (`DUAL_USE`: `glucose`, `creatinine`, `protein`...) — vừa là thuốc vừa là chỉ số xét nghiệm — chỉ nhận là THUỐC khi có hàm lượng đi kèm. `Glucose 5% x 1000ml` → thuốc; `Glucose máu: 13,2 mmol/l` → không, để nhánh B xử lý.
4. **Thuốc ngoài từ điển** (`_find_unknown_drugs`): một từ trông như tên riêng đứng ngay trước hàm lượng, không phải từ chức năng (`uống`, `viên`...), không phải chỉ số xét nghiệm → vẫn nhận là THUỐC, với độ tin cậy thấp hơn (`score=0.7` so với `1.0` của khớp từ điển). Đây là cách bắt được `Omez 20mg` — biệt dược Ấn Độ không có trong RxNorm (Mỹ) — bằng **cấu trúc câu**, không cần gọi LLM.

### 3.4 NHÁNH A — encoder, hiện trạng và cách nó SẼ hoạt động

**Vấn đề đã giải quyết (offset):** encoder cần input đã tách từ (`Hẹp động_mạch thận`) vì dữ liệu train (PhoNER, ViMQ) đều ở dạng này. Nhưng bệnh án đầu vào lúc suy luận là **chưa tách**. `text_alignment.py` xây bảng ánh xạ: mỗi từ-đã-tách ↔ khoảng ký tự thật trong văn bản gốc, đi qua **ký tự đã chuẩn hoá NFC** (không qua đếm token thô — cách đó từng lệch vì PyVi tách dấu câu thành token riêng, và văn bản gốc là NFD trong khi PyVi trả NFC).

**Việc còn thiếu:** encoder (`ViPubmedDeBERTa` fine-tune trên PhoNER+ViMQ, nhãn hợp nhất `SYM_DIS`) **chưa được train đủ epoch trên GPU thật**. `notebooks/train_ner_encoder.ipynb` giờ chạy được (đã sửa 3 lỗi ở Mục 2), nhưng chưa có lần chạy nào tạo ra weight cuối cùng.

**Sau khi train xong**, luồng suy luận của nhánh A là:
1. Tách từ bệnh án bằng PyVi, giữ bảng ánh xạ offset.
2. Đưa chuỗi từ đã tách qua encoder → nhãn BIO cho từng token (`O` / `B-SYM_DIS` / `I-SYM_DIS`).
3. Gộp token liền kề cùng nhãn thành span, dùng bảng ánh xạ Mục trên để quy về offset trong văn bản gốc.
4. Mỗi span `SYM_DIS` đi qua **thác 3 bậc** (`cascade_classifier.py`) để quyết `TRIỆU_CHỨNG` hay `CHẨN_ĐOÁN`:
   - **Bậc 1**: retrieve vào KB ICD-10, nếu mã top-1 thuộc **chương R** (Triệu chứng, dấu hiệu) → `TRIỆU_CHỨNG`. Đo được: 7/7 đúng trên mẫu thử.
   - **Bậc 2**: nếu top-1 ngoài chương R và cosine ≥ 0.93 → `CHẨN_ĐOÁN`. Đo được: 11/11 đúng, 0 lọt.
   - **Bậc 3**: còn lại (≈40%, chưa quyết được bằng KB) → hỏi Qwen chọn nhị phân A/B với constrained decoding. **`llm_classifier.py` implement bậc này nhưng chưa được chạy thử lần nào** — cần GPU.

### 3.5 Gắn phủ định và hợp nhất

`negation_detector.py`: quét cửa sổ 50 ký tự trước mỗi thực thể tìm từ phủ định (`không có`, `phủ nhận`, `âm tính`...), có xử lý ngắt câu (`.`, `;`) và đảo ngược (`nhưng`, `tuy nhiên`) để không phủ định nhầm. **Cách gọi đúng — hai bước:**
```python
annotated = negation_detector.annotate_negation(entities, text)   # BƯỚC 1: gắn 'negated'
status = negation_detector.get_assertion_status(annotated[0])     # BƯỚC 2: đọc lại
```
Gọi `get_assertion_status()` trực tiếp trên entity chưa qua `annotate_negation()` sẽ luôn trả `'affirmed'` — không phải lỗi, chỉ là API 2 bước, dễ dùng sai nếu không biết.

`overlap_resolver.py`: sau khi có toàn bộ thực thể từ cả 3 nhánh, quy hoạch động chọn tập con không chồng lấn có tổng điểm cực đại — đúng bài toán *weighted interval scheduling*, nghiệm tối ưu O(n log n). Đảm bảo mỗi ký tự thuộc tối đa một thực thể.

## 4. Schema JSON đầu ra

```json
{
  "text": "<nguyên văn bệnh án>",
  "entities": [
    {
      "text": "Hội chứng thận hư",
      "type": "CHẨN_ĐOÁN",
      "start": 89,
      "end": 106,
      "score": 0.97,
      "source": "encoder+kb",
      "negated": false,
      "assertion": "affirmed"
    }
  ]
}
```

`type` ∈ 5 giá trị: `TRIỆU_CHỨNG`, `CHẨN_ĐOÁN`, `THUỐC`, `TÊN_XÉT_NGHIỆM`, `KẾT_QUẢ_XÉT_NGHIỆM`. `source` cho biết thực thể đến từ đâu để debug: `rule` (nhánh B), `dict`/`rule_strength` (nhánh C), `encoder+kb`/`encoder+llm` (nhánh A).

## 5. Việc cần làm tiếp, đúng thứ tự

1. **Train encoder trên Kaggle** — `notebooks/train_ner_encoder.ipynb`, giờ đã chạy được (3 lỗi ở Mục 2 đã sửa và kiểm lại từ đúng nội dung file). Chưa có lần chạy đủ epoch.
2. **Nối nhánh A vào `ner_inference_e2e.ipynb`** — notebook suy luận đầu-cuối hiện dùng weight nào cho encoder cần trỏ tới Kaggle Dataset của bước 1.
3. **Chạy thử `llm_classifier.py` trên GPU thật** — hiện mới kiểm cú pháp, chưa có một lần gọi model thành công nào để biết bậc 3 của thác có hoạt động đúng không.
4. **Xây gold thủ công** trên vài file — mọi ngưỡng hiện tại (0.93, τ các loại) đều rút ra từ mẫu tự chọn, chưa có gì để đo độ chính xác thật.

## 6. Cách chạy

### Train
```
1. notebooks/train_ner_encoder.ipynb lên Kaggle
2. Settings: GPU T4 x2, Internet ON
3. Factory reset trước khi Run All (nếu session cũ còn thư mục fakeer/ đã clone,
   git clone sẽ bị bỏ qua và bạn chạy nhầm code cũ)
4. Tải weight về, upload lại thành Kaggle Dataset
```

### Suy luận
```
1. notebooks/ner_inference_e2e.ipynb lên Kaggle
2. Add dataset: kb/ (ICD + RxNorm) + weight encoder từ bước train
3. Dán bệnh án vào cell 2
4. Run All → /kaggle/working/ner_output.json
```

## 7. Kiểm chứng local trước khi push

```bash
python test_local.py
```
6/6 test: Text Alignment, Branch B, Branch C, NER Metrics, Overlap Resolver, Real Data.
**Không bao gồm** `negation_detector.py` và `llm_classifier.py` — test hai file đó riêng:
```bash
python src/negation_detector.py     # 10/10, không cần GPU
python src/llm_classifier.py        # cần GPU, CHƯA XÁC NHẬN chạy được
```
