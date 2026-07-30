# Medical NER Vietnamese - 5 Types

Repo này dùng cho bài toán trích xuất thực thể y khoa từ văn bản/bệnh án tiếng Việt. Đầu ra là JSON gồm đúng 5 loại:

| type | nghĩa | ví dụ |
|---|---|---|
| `TRIỆU_CHỨNG` | biểu hiện bệnh nhân khai hoặc bác sĩ quan sát | `sốt cao`, `đau bụng`, `khó thở` |
| `CHẨN_ĐOÁN` | tên bệnh hoặc hội chứng | `viêm phổi`, `thiếu men G6PD`, `bệnh Kawasaki` |
| `THUỐC` | tên thuốc, kèm hàm lượng nếu đứng liền sau | `Medrol 16mg`, `Furosemid 40 mg` |
| `TÊN_XÉT_NGHIỆM` | tên xét nghiệm/chỉ số/thăm dò | `Ure`, `Creatinin`, `WBC` |
| `KẾT_QUẢ_XÉT_NGHIỆM` | giá trị đo được | `6,4 mmol/l`, `14.99 G/L`, `âm tính` |

Các span phải là lát cắt nguyên văn từ văn bản gốc (`text[start:end] == entity["text"]`). Vì sai type và trích thừa bị phạt nặng, pipeline ưu tiên độ chắc chắn hơn là sinh thêm span bừa.

## Trạng thái hiện tại

- Notebook train Kaggle đã train đủ 10 epoch trong log ngày 2026-07-29 và đạt `eval_f1 = 0.8203216033558611` trên dev. Lỗi cuối cùng là `NameError: classification_report is not defined`; đã sửa bằng metric tự viết `entity_f1/format_report`, không cần `seqeval`.
- Notebook inference đã sửa lỗi keyword cascade: `classify_batch(..., llm_classifier=None)` thay cho tham số sai `llm_client`.
- Notebook inference đã đổi `REPO_URL` sang repo thật: `https://github.com/Khanhhh239/fakeer.git`.
- Root docs cũ/trùng/lỗi thời đã được dọn. README này là tài liệu chính; `kb/README.md` mô tả riêng các file KB.

## Cấu trúc

```text
src/
  data_prep/
    convert_phoner.py          # PhoNER_COVID19 -> BIO SYM_DIS
    convert_vimq.py            # ViMQ -> BIO SYM_DIS
  utils/
    text_alignment.py          # PyVi + offset map về văn bản gốc
    ner_metrics.py             # entity-level strict F1, thay seqeval
    overlap_resolver.py        # weighted interval scheduling
  branch_b_lab_tests.py        # TÊN_XÉT_NGHIỆM + KẾT_QUẢ_XÉT_NGHIỆM
  branch_c_drugs.py            # THUỐC bằng RxNorm + luật hàm lượng
  cascade_classifier.py        # SYM_DIS -> TRIỆU_CHỨNG / CHẨN_ĐOÁN
  llm_choice_classifier.py     # lựa chọn N nhãn bằng vLLM, chưa chạy GPU thật
  negation_detector.py         # gắn negated/assertion
notebooks/
  train_ner_encoder.ipynb
  ner_inference_e2e.ipynb
kb/
  icd10_vi_full.csv
  icd10_en.csv
  rxnorm_merged.csv
  inn_usan.csv
input/
  1.txt ... 100.txt
```

## Pipeline Train

Notebook: `notebooks/train_ner_encoder.ipynb`.

1. Cài `transformers`, `datasets`, `pyvi`, `accelerate` trên Kaggle.
2. Clone repo `Khanhhh239/fakeer.git`, tìm `src/data_prep`.
3. Tải và convert 2 nguồn dữ liệu:
   - PhoNER_COVID19: chỉ giữ `SYMPTOM_AND_DISEASE`, map thành `SYM_DIS`; các type khác -> `O`.
   - ViMQ: span là word index inclusive `[i, j]`; chỉ giữ `SYMPTOM_AND_DISEASE`; `medical_procedure` và `drug` -> `O`.
4. Gộp train/dev, tokenizer bằng `manhtt-079/vipubmed-deberta-base`.
5. Căn nhãn subword:
   - subword đầu tiên của mỗi từ giữ nhãn BIO;
   - subword sau và special token đặt `-100`.
6. Train `AutoModelForTokenClassification` với 3 nhãn: `O`, `B-SYM_DIS`, `I-SYM_DIS`.
7. Đánh giá bằng entity-level strict F1 trong `src/utils/ner_metrics.py`.
8. Lưu `/kaggle/working/ner_encoder/` gồm model, tokenizer, `label_map.json`, `metrics.json`.

Lưu ý Kaggle:

- Không dùng `seqeval`; Kaggle Python 3.12 có thể vỡ metadata/install.
- Không truyền `classifier_dropout` cho DeBERTaV2; tham số này không hợp với `DebertaV2ForTokenClassification`.
- Với `transformers` mới, `Trainer` dùng `processing_class=tokenizer`, không dùng `tokenizer=`.

## Pipeline Inference

Notebook: `notebooks/ner_inference_e2e.ipynb`.

1. Dán văn bản bệnh án vào biến `TEXT`.
2. Nhánh B chạy trực tiếp trên văn bản gốc:
   - tách đoạn theo `\n`, `;`, `:`, dấu phẩy không nằm giữa hai chữ số;
   - đoạn dạng `số + đơn vị y khoa` hoặc `âm tính/dương tính/(+)` -> `KẾT_QUẢ_XÉT_NGHIỆM`;
   - đoạn ngay trước, nếu ngắn và có chữ, -> `TÊN_XÉT_NGHIỆM`.
3. Nhánh C chạy trực tiếp trên văn bản gốc:
   - nạp RxNorm/INN-USAN;
   - quét n-gram tên thuốc;
   - nối hàm lượng ngay sau tên thuốc;
   - thuốc ngoài RxNorm có dạng `TênRiêng + hàm lượng` được bắt bằng luật `rule_strength`.
4. Nhánh A:
   - PyVi tách từ và `text_alignment.py` giữ offset về văn bản gốc;
   - encoder BIO sinh span `SYM_DIS`;
   - `cascade_classifier.py` tách `SYM_DIS` thành `TRIỆU_CHỨNG` hoặc `CHẨN_ĐOÁN`:
     - tier 1: ICD chương R -> `TRIỆU_CHỨNG`;
     - tier 2: ICD ngoài chương R, cosine >= 0.93 -> `CHẨN_ĐOÁN`;
     - tier 3: hiện notebook để `llm_classifier=None`, nên fallback là `TRIỆU_CHỨNG`.
5. Hợp nhất nhánh A/B/C bằng `overlap_resolver.py`, chọn tập span không chồng lấn có tổng score tốt nhất.
6. Checklist bắt buộc:
   - span nguyên văn;
   - không chồng lấn;
   - type thuộc đúng 5 loại;
   - không span rỗng;
   - offset hợp lệ.
7. Xuất `/kaggle/working/ner_output.json`.

Schema:

```json
{
  "text": "...",
  "entities": [
    {
      "text": "viêm phổi",
      "type": "CHẨN_ĐOÁN",
      "start": 120,
      "end": 129,
      "score": 1.0,
      "source": "encoder+kb"
    }
  ]
}
```

## Cách chạy Kaggle

Train:

```text
1. Upload notebooks/train_ner_encoder.ipynb lên Kaggle.
2. Settings: GPU T4 x2 hoặc P100, Internet ON.
3. Run All.
4. Sau khi xong, download /kaggle/working/ner_encoder/.
5. Upload folder đó thành Kaggle Dataset để dùng cho inference.
```

Inference:

```text
1. Upload notebooks/ner_inference_e2e.ipynb lên Kaggle.
2. Add Dataset chứa ner_encoder từ bước train.
3. Add Dataset chứa kb/*.csv.
4. Sửa MODEL_PATH/RXNORM_PATH/INN_USAN_PATH/ICD_PATH nếu tên Kaggle Dataset khác mặc định trong notebook.
5. Dán bệnh án vào TEXT.
6. Run All.
```

## Kiểm thử local

```bash
pip install -r requirements.txt
python test_local.py
```

`test_local.py` kiểm các phần không cần GPU: alignment, lab, drug, span candidates, metric, overlap và vài mẫu input thật. LLM/vLLM cần GPU thật nên không được coi là đã nghiệm thu nếu chỉ chạy local CPU.

## Ghi chú từ test data

Đã đọc nhiều mẫu trong `input/`: có bài tư vấn y khoa dài, bullet, bệnh án nhập viện, thuốc bị ẩn bằng `*******`, chỉ số không có đơn vị, tiếng Việt có dấu/khác chuẩn và phủ định kiểu `Phủ nhận đau ngực`. Vì vậy pipeline không nên gom tất cả vào một model sinh tự do; cách ba nhánh hiện tại giúp giữ offset nguyên văn và kiểm soát false positive tốt hơn.
