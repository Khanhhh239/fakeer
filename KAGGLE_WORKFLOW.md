# Hướng dẫn chạy trên Kaggle

## Bước 1: Push code lên GitHub

```bash
# Init git (nếu chưa có)
git init
git add .
git commit -m "Initial commit: Medical NER Vietnamese"

# Tạo repo trên GitHub rồi push
git remote add origin https://github.com/YOUR_USERNAME/medical-ner-vietnamese.git
git branch -M main
git push -u origin main
```

## Bước 2: Chuẩn bị KB files

Bạn cần 3 file KB:

### 1. icd10_vi_full.csv
```csv
code,name
R50,Sốt không rõ nguyên nhân
R51,Đau đầu
J18,Viêm phổi
N18,Bệnh thận mạn
...
```

### 2. rxnorm_merged.csv
```csv
rxcui,name
3322,Paracetamol
10689,Aspirin
6851,Metformin
...
```

### 3. inn_usan.csv
```csv
inn,usan
paracetamol,acetaminophen
...
```

**Upload 3 file này thành một Kaggle Dataset:**
- Tên: `medical-kb-vietnamese`
- Files: 3 files CSV trên

## Bước 3: Training Notebook (Notebook 1)

### Create New Notebook
1. Tạo notebook mới trên Kaggle
2. Settings:
   - Accelerator: **GPU T4 x2** hoặc **GPU P100**
   - Internet: **ON**
   - Persistence: **Files only**

### Upload notebook
- Upload file `notebooks/train_ner_encoder.ipynb`

### Sửa REPO_URL
Trong cell 2, sửa:
```python
REPO_URL = "https://github.com/YOUR_USERNAME/medical-ner-vietnamese.git"
```

### Run
1. Run All
2. Chờ ~30-60 phút (training 10 epochs)
3. Kiểm tra `/kaggle/working/ner_encoder/`
4. Download folder này

### Create Dataset từ Model Weights
1. New Dataset
2. Upload folder `ner_encoder/`
3. Tên: `medical-ner-encoder-weights`

## Bước 4: Inference Notebook (Notebook 2)

### Create New Notebook
1. Tạo notebook mới
2. Settings:
   - Accelerator: **GPU T4** hoặc **CPU** (GPU nhanh hơn nhưng CPU cũng được)
   - Internet: **ON**

### Upload notebook
- Upload file `notebooks/ner_inference_e2e.ipynb`

### Add Input Datasets
Click "Add Input" và add:
1. `medical-ner-encoder-weights` (từ bước 3)
2. `medical-kb-vietnamese` (từ bước 2)

### Sửa paths trong notebook

**Cell 1:**
```python
REPO_URL = "https://github.com/YOUR_USERNAME/medical-ner-vietnamese.git"
```

**Cell 4:**
```python
RXNORM_PATH = '/kaggle/input/medical-kb-vietnamese/rxnorm_merged.csv'
INN_USAN_PATH = '/kaggle/input/medical-kb-vietnamese/inn_usan.csv'
```

**Cell 6:**
```python
MODEL_PATH = '/kaggle/input/medical-ner-encoder-weights'
```

**Cell 7:**
```python
ICD_PATH = '/kaggle/input/medical-kb-vietnamese/icd10_vi_full.csv'
```

### Chạy inference

**QUAN TRỌNG:** Chỉ cần chạy cell 1 và cell 2!

1. Run cell 1 (setup)
2. Paste bệnh án vào cell 2:
```python
TEXT = """
<paste bệnh án vào đây>
"""
```
3. Run từ cell 2 trở đi (hoặc Run All)
4. Kết quả: `/kaggle/working/ner_output.json`

## Bước 5: Kiểm tra kết quả

Output JSON format:
```json
{
  "text": "...",
  "entities": [
    {
      "text": "sốt cao",
      "type": "TRIỆU_CHỨNG",
      "start": 0,
      "end": 7,
      "score": 0.95,
      "source": "encoder+kb"
    }
  ]
}
```

### Validation tự động
Cell 9 sẽ tự động kiểm tra:
- ✓ Span nguyên văn
- ✓ Không chồng lấn
- ✓ Type hợp lệ
- ✓ Không span rỗng
- ✓ Offset hợp lệ

Nếu có lỗi, notebook sẽ DỪNG và báo lỗi cụ thể.

## Troubleshooting

### Lỗi: "ánh xạ offset HỎNG"
- Nguyên nhân: Văn bản có ký tự đặc biệt hoặc Unicode phức tạp
- Giải pháp: Kiểm tra cell 5, xem dòng nào bị lỗi

### Lỗi: "word_ids() not available"
- Nguyên nhân: Tokenizer không phải fast
- Giải pháp: Verify đang dùng `manhtt-079/vipubmed-deberta-base`

### Lỗi: OOM (Out of Memory)
- Training: Giảm `per_device_train_batch_size` từ 16 xuống 8
- Inference: Dùng CPU thay vì GPU, hoặc giảm `max_length` từ 512 xuống 256

### Kết quả không tốt
- Kiểm tra số lượng entities: bệnh án ~2000 ký tự nên ra ~35-45 entities
- Nếu ra >100 entities: có gì đó sai (có thể cascade không hoạt động)
- Nếu ra <10 entities: encoder không chạy hoặc threshold quá cao

## F1 mong đợi

- **PhoNER dev:** ~94% (nhưng đừng lấy làm mốc - bài toán dễ)
- **ViMQ dev:** ~80% ← **Mốc đúng**
- **Bệnh án thật:** Chưa có gold → chưa đo được

## Tips

1. **Test trên văn bản ngắn trước:** ~500 ký tự để kiểm tra pipeline
2. **Kiểm tra từng nhánh riêng:** Cell 3 (lab), Cell 4 (drug), Cell 6-7 (encoder)
3. **Xem tier statistics:** Cell 7 báo bao nhiêu % quyết bởi KB vs LLM
4. **Type distribution:** Cell 8 báo số lượng từng type

## Next Steps (Nâng cao)

1. **Thêm LLM tier 3:** Hiện tại tier 3 default TRIỆU_CHỨNG. Cần integrate vLLM với Qwen3-8B
2. **Fine-tune threshold:** Ngưỡng 0.93 từ 30 mẫu, cần điều chỉnh khi có gold
3. **Thêm thuốc Việt Nam:** Add vào `vietnamese_drugs` trong cell 4
4. **Xử lý phủ định:** "Không có suy thận" - chưa implement

## Support

Nếu gặp vấn đề, kiểm tra:
1. Cell nào báo lỗi?
2. Error message là gì?
3. Validation checklist (cell 9) pass chưa?
