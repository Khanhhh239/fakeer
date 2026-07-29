# Medical NER Vietnamese - Encoder + Cascade

Hệ thống trích xuất thực thể y khoa từ bệnh án tiếng Việt.

## Kiến trúc

```
Văn bản bệnh án
   │
   ├── NHÁNH A: Triệu chứng & Chẩn đoán
   │   ├─ Tách từ + ánh xạ offset (PyVi)
   │   ├─ Encoder BIO → SYM_DIS
   │   └─ Thác 3 bậc → TRIỆU_CHỨNG | CHẨN_ĐOÁN
   │
   ├── NHÁNH B: Xét nghiệm (luật regex)
   │   └─ TÊN_XÉT_NGHIỆM + KẾT_QUẢ_XÉT_NGHIỆM
   │
   └── NHÁNH C: Thuốc (từ điển RxNorm)
       └─ THUỐC
   │
   └─ Hợp nhất + khử chồng lấn → JSON
```

## 5 Loại Thực Thể

1. **TRIỆU_CHỨNG** - biểu hiện bệnh nhân khai/bác sĩ quan sát
2. **CHẨN_ĐOÁN** - tên bệnh hoặc hội chứng
3. **THUỐC** - tên thuốc + hàm lượng
4. **TÊN_XÉT_NGHIỆM** - tên xét nghiệm/chỉ số
5. **KẾT_QUẢ_XÉT_NGHIỆM** - giá trị đo được

## Cấu trúc thư mục

```
├── src/
│   ├── utils/
│   │   ├── text_alignment.py          # Ánh xạ offset (CRITICAL!)
│   │   └── overlap_resolver.py        # Giải quyết chồng lấn
│   ├── data_prep/
│   │   ├── convert_phoner.py          # Convert PhoNER_COVID19
│   │   └── convert_vimq.py            # Convert ViMQ
│   ├── branch_b_lab_tests.py          # Nhánh B - xét nghiệm
│   ├── branch_c_drugs.py              # Nhánh C - thuốc
│   └── cascade_classifier.py          # Thác 3 bậc
├── notebooks/
│   ├── train_ner_encoder.ipynb        # Training notebook (Kaggle)
│   └── ner_inference_e2e.ipynb        # Inference notebook (Kaggle)
├── input/                              # 100 bệnh án test
├── requirements.txt
└── README.md
```

## Setup Local (Test)

```bash
# Install dependencies
pip install -r requirements.txt

# Test các module
python src/utils/text_alignment.py
python src/branch_b_lab_tests.py
python src/branch_c_drugs.py
python src/utils/overlap_resolver.py
```

## Workflow Kaggle

### 1. Training (Notebook 1)

**Môi trường:** Kaggle GPU (T4 x2 hoặc P100), Internet ON

**Steps:**
1. Tải PhoNER_COVID19 + ViMQ từ GitHub
2. Convert sang BIO format thống nhất (chỉ giữ SYM_DIS)
3. Train ViPubmedDeBERTa với siêu tham số từ paper
4. Save model weights + metrics

**Output:** `/kaggle/working/ner_encoder/` → Upload thành Kaggle Dataset

**F1 mong đợi:** ~80% (ViMQ-NER benchmark)

### 2. Inference (Notebook 2)

**Môi trường:** Kaggle GPU hoặc CPU, Internet ON

**Kaggle Datasets cần add:**
1. NER encoder weights (từ notebook 1)
2. `icd10_vi_full.csv` - KB ICD-10 tiếng Việt
3. `rxnorm_merged.csv` + `inn_usan.csv` - KB thuốc

**Input:** Paste văn bản bệnh án vào cell 2

**Output:** `/kaggle/working/ner_output.json`

```json
{
  "text": "...",
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

## Kiểm tra chất lượng

Notebook 2 có checklist tự động (cell 9):

✓ Span nguyên văn (exact match với văn bản gốc)  
✓ Không chồng lấn  
✓ Type hợp lệ (chỉ 5 loại)  
✓ Không span rỗng  
✓ Offset hợp lệ  

## Data Sources

- **PhoNER_COVID19** (NAACL 2021) - 10 type, chỉ dùng SYMPTOM_AND_DISEASE
- **ViMQ** (ICONIP 2021) - 3 type, chỉ dùng SYMPTOM_AND_DISEASE
- **ICD-10 Tiếng Việt** - 14,792 mã / 17,094 tên
- **RxNorm** - 83,320 RxCUI / 129,690 tên thuốc

## Model

- **Encoder:** `manhtt-079/vipubmed-deberta-base` (86M parameters)
- **Embedding:** `AITeamVN/Vietnamese_Embedding` (cho cascade)
- **LLM (optional):** `Qwen/Qwen3-8B` hoặc `Qwen/Qwen2.5-7B-Instruct`

## Ràng buộc

- ✓ Self-host only (no API calls)
- ✓ Model ≤ 9B parameters
- ✓ Span nguyên văn từng ký tự
- ✓ Sai type → phạt 2x
- ✓ Trích thừa → phạt 3x

## Tham khảo

Kế hoạch chi tiết: `KEHOACH_NER.md`

## Lưu ý quan trọng

### Ánh xạ offset (text_alignment.py)
- Đã test 100/100 file: PASS
- KHÔNG bỏ qua `assert ok == False`
- PHẢI chuẩn hóa NFC trước khi so sánh

### Encoder
- Chỉ train SYM_DIS (không train DRUG từ ViMQ - sai miền)
- Tokenizer PHẢI là fast (có `word_ids()`)
- ViHealthBERT không dùng được (tokenizer không fast)

### Thác phân loại
- Ngưỡng 0.93 từ 30 mẫu (chưa kiểm chứng đầy đủ)
- Bậc 1+2 quyết được 60% ở độ chính xác 100%
- Bậc 3 cần LLM (hiện tại default TRIỆU_CHỨNG)

### Từ điển thuốc
- RxNorm không có biệt dược Việt Nam
- Cần add manually vào `vietnamese_drugs`
- Ví dụ: Medrol, Zestril, Vastarel, Nitralmyl

## License

MIT
