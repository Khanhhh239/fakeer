# Updates - LLM Tier 3 & Negation Detection

## ✨ Features Mới Đã Thêm

### 1. LLM Tier 3 Classifier ✅

**File:** `src/llm_classifier.py`

**Tính năng:**
- Phân loại TRIỆU_CHỨNG vs CHẨN_ĐOÁN bằng Qwen
- Constrained decoding đảm bảo output là A hoặc B
- Parse logprobs để lấy confidence chính xác
- Support batch processing

**Cách dùng:**
```python
from llm_classifier import LLMClassifier

# Initialize
llm = LLMClassifier(model_name="Qwen/Qwen2.5-7B-Instruct")

# Single classification
label, conf = llm.classify("sốt cao", "Bệnh nhân sốt cao 39 độ")
# -> ('TRIỆU_CHỨNG', 0.87)

# Batch classification
spans = [
    {'text': 'sốt cao', 'context': '...'},
    {'text': 'viêm phổi', 'context': '...'}
]
results = llm.classify_batch(spans)
```

**Cascade integration:**
```python
from cascade_classifier import CascadeClassifier
from llm_classifier import LLMClassifier

cascade = CascadeClassifier(icd_path="...")
llm = LLMClassifier()

# Classify với LLM tier 3
classified = cascade.classify_batch(spans, llm_classifier=llm)
```

### 2. Negation Detection ✅

**File:** `src/negation_detector.py`

**Tính năng:**
- Phát hiện phủ định: "không có", "phủ nhận", "âm tính"
- Window-based detection (50 ký tự trước entity)
- Xử lý terminator: dấu chấm, "nhưng", "tuy nhiên"
- Support 15+ negation cues tiếng Việt

**Test results:** 10/10 passed ✅

**Cách dùng:**
```python
from negation_detector import NegationDetector

detector = NegationDetector(window_size=50)

# Annotate entities
entities = [
    {'text': 'suy thận', 'start': 20, 'end': 28, 'type': 'CHẨN_ĐOÁN'}
]

text = "Bệnh nhân không có suy thận"
annotated = detector.annotate_negation(entities, text)

# Output: [{'text': 'suy thận', ..., 'negated': True}]
```

## 📝 Cập Nhật Inference Notebook

### Thêm Cell 6.5 (sau cell 7 cũ - cascade):

```python
# Cell 6.5: Load LLM cho Tier 3 (Optional - nếu có GPU đủ mạnh)
ENABLE_LLM_TIER3 = True  # Đặt False nếu muốn skip LLM

if ENABLE_LLM_TIER3:
    try:
        from llm_classifier import LLMClassifier
        
        print("Loading LLM for Tier 3...")
        llm = LLMClassifier(model_name="Qwen/Qwen2.5-7B-Instruct")
        llm.load_model()
        print("✓ LLM loaded!")
    except Exception as e:
        print(f"⚠️ Could not load LLM: {e}")
        print("Will use default tier 3 (TRIỆU_CHỨNG)")
        llm = None
else:
    print("LLM Tier 3 disabled - using defaults")
    llm = None
```

### Update Cell 7 (cascade):

```python
# Cell 7: NHÁNH A Bước 3 - Thác tách TRIỆU_CHỨNG / CHẨN_ĐOÁN
from cascade_classifier import CascadeClassifier

# TODO: Update path
ICD_PATH = '/kaggle/input/medical-kb/icd10_vi_full.csv'

print("Loading cascade classifier...")
cascade = CascadeClassifier(
    icd_path=ICD_PATH,
    embedding_model="AITeamVN/Vietnamese_Embedding",
    threshold=0.93
)

print("\nClassifying SYM_DIS spans...")
# Add context for each span
for ent in encoder_entities:
    # Simple context: surrounding ±50 chars
    start = max(0, ent['start'] - 50)
    end = min(len(TEXT), ent['end'] + 50)
    ent['context'] = TEXT[start:end]

# Classify WITH LLM tier 3
classified_entities = cascade.classify_batch(
    encoder_entities,
    llm_classifier=llm if 'llm' in globals() else None
)

# Statistics
tier_stats = {}
for ent in classified_entities:
    tier = ent.get('tier', 'unknown')
    tier_stats[tier] = tier_stats.get(tier, 0) + 1

print(f"\n✓ Classification complete!")
print(f"Tier statistics:")
for tier, count in tier_stats.items():
    print(f"  {tier}: {count}")

# Update source
for ent in classified_entities:
    tier = ent.get('tier', '')
    if 'kb' in tier:
        ent['source'] = 'encoder+kb'
    elif 'llm' in tier:
        ent['source'] = 'encoder+llm'

print(f"\nSample results:")
for ent in classified_entities[:10]:
    print(f"  [{ent['type']}] '{ent['text']}' (tier: {ent['tier']})")
```

### Thêm Cell 8.5 (sau merge, trước checklist):

```python
# Cell 8.5: Negation Detection
from negation_detector import NegationDetector

print("Detecting negations...")
detector = NegationDetector(window_size=50)

# Annotate all entities
final_entities_with_neg = detector.annotate_negation(final_entities, TEXT)

# Statistics
negated_count = sum(1 for e in final_entities_with_neg if e.get('negated', False))
print(f"\n✓ Found {negated_count} negated entities out of {len(final_entities_with_neg)}")

# Show negated entities
if negated_count > 0:
    print("\nNegated entities:")
    for ent in final_entities_with_neg:
        if ent.get('negated', False):
            print(f"  [{ent['type']}] '{ent['text']}'")

# Update final entities
final_entities = final_entities_with_neg
```

### Update Cell 10 (JSON output):

```python
# Cell 10: Xuất JSON
import json

# Prepare output
result = {
    'text': TEXT,
    'entities': [
        {
            'text': ent['text'],
            'type': ent['type'],
            'start': ent['start'],
            'end': ent['end'],
            'score': ent['score'],
            'source': ent['source'],
            'negated': ent.get('negated', False),  # ← NEW
            'assertion': 'negated' if ent.get('negated', False) else 'affirmed'  # ← NEW
        }
        for ent in final_entities
    ]
}

# Save
output_path = '/kaggle/working/ner_output.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"✓ Saved to {output_path}")
print(f"\nTotal entities: {len(final_entities)}")
print(f"Negated: {sum(1 for e in final_entities if e.get('negated', False))}")
print(f"\nType breakdown:")
for t, count in sorted(type_counts.items()):
    print(f"  {t}: {count}")

# Pretty print first 20
print(f"\n{'='*60}")
print("First 20 entities:")
print(f"{'='*60}")
for i, ent in enumerate(final_entities[:20]):
    neg_mark = " [NEGATED]" if ent.get('negated', False) else ""
    print(f"{i+1:2d}. [{ent['type']:20s}] '{ent['text']}'{neg_mark}")

print(f"\n{'='*60}")
print("✓ INFERENCE COMPLETE!")
print(f"{'='*60}")
```

## 📊 JSON Output Format (Updated)

```json
{
  "text": "...",
  "entities": [
    {
      "text": "suy thận",
      "type": "CHẨN_ĐOÁN",
      "start": 20,
      "end": 28,
      "score": 0.95,
      "source": "encoder+kb",
      "negated": true,
      "assertion": "negated"
    }
  ]
}
```

## ⚡ Performance Impact

### LLM Tier 3:
- **Setup:** +30-60s (load model lần đầu)
- **Per entity:** +0.5-1s (GPU), +2-3s (CPU)
- **Batch (10 entities):** +2-5s (GPU), +10-15s (CPU)
- **Memory:** +4-6 GB VRAM (Qwen2.5-7B)

### Negation Detection:
- **Per entity:** <0.001s (rất nhanh)
- **Batch (100 entities):** <0.1s
- **Memory:** Negligible

## 💡 Tips

### Nếu OOM với LLM:
```python
# Option 1: Disable LLM
ENABLE_LLM_TIER3 = False

# Option 2: Giảm max_model_len
llm = LLMClassifier(model_name="Qwen/Qwen2.5-7B-Instruct")
llm.llm = LLM(
    model=llm.model_name,
    max_model_len=1024,  # Giảm từ 2048
    gpu_memory_utilization=0.3  # Giảm từ 0.5
)

# Option 3: Dùng CPU cho encoder, GPU cho LLM
```

### Kiểm tra tier distribution:
```python
# Sau khi classify
tier_stats = {}
for ent in classified_entities:
    tier = ent.get('tier', 'unknown')
    tier_stats[tier] = tier_stats.get(tier, 0) + 1

print("Tier distribution:")
for tier, count in tier_stats.items():
    pct = count / len(classified_entities) * 100
    print(f"  {tier}: {count} ({pct:.1f}%)")
```

**Mục tiêu:** Tier 1+2 (KB) quyết được ~60%, Tier 3 (LLM) ~40%

## 🧪 Testing

```bash
# Test negation (local)
python src/negation_detector.py

# Test LLM (cần GPU + vLLM)
python src/llm_classifier.py
```

## 📚 References

- **Negation cues:** Dựa trên NegEx algorithm (Chapman et al., 2001) adapted cho tiếng Việt
- **LLM:** Qwen2.5-7B-Instruct (Alibaba Cloud, 2024)
- **Constrained decoding:** vLLM logprobs-based approach

## 🎯 Metric Impact

**Với tier 3 LLM:**
- Dự kiến +3-5% F1 so với default
- Giảm bias về TRIỆU_CHỨNG

**Với negation:**
- +0.3 × (1 − negation_error_rate) theo metric gốc
- Critical cho clinical correctness
