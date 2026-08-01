# Kế hoạch sinh dữ liệu huấn luyện tổng hợp

**Ràng buộc:** model ≤9B, không gọi API ngoài.
**Mục tiêu:** 3.000–5.000 thực thể, nhãn chính xác, phân bố khớp đề thi.

---

## 0. Nguyên lý nền — điều quyết định thành bại

> **LLM KHÔNG BAO GIỜ được gán nhãn. Nó chỉ được VIẾT VĂN.**

Hướng đi của bạn (có sẵn nhãn → sinh text) là **đúng**, và lý do đúng nằm ở chỗ:

| Hướng | Nhãn đến từ đâu | Sai sót |
|---|---|---|
| Thuận: text thật → LLM gán nhãn | LLM quyết định span + type | Kế thừa **toàn bộ** lỗi của LLM. `dataset2` đo được **recall 53%** |
| **Ngược: nhãn có trước → LLM viết text** | **Biết trước theo cấu tạo** | LLM không hề gán nhãn ⇒ **không thể gán sai** |

Trả lời thẳng câu hỏi *"dùng text thật thì lấy gì NER chất lượng ra label?"*:

**Không có gì tự động đủ tốt.** Đó chính là điều `dataset2` chứng minh — LLM gán nhãn trên text thật chỉ đạt recall ~53%, bỏ sót `tiểu rắt`, `đau vùng hạ vị`, `u xơ tiền liệt`... ngay trong đoạn bác sĩ trả lời. Nên:

- **Text thật** → chỉ dùng làm **tập kiểm định**, gán tay, số lượng nhỏ (5–10 file)
- **Sinh ngược** → dùng làm **tập huấn luyện**, số lượng lớn

### Nhưng sinh ngược có MỘT cái bẫy — và `data/dataset` đã rơi vào

Sinh ngược **không** tự động đúng. `data/dataset` cũng sinh ngược, và hỏng vì **cách sinh text**: nó *dán chuỗi KB liền nhau* thay vì *viết văn*. Kết quả: 55.6% từ nằm trong thực thể, không còn ngữ cảnh để học.

**Sinh ngược đúng = nhãn có trước + văn bản phải là VĂN THẬT.** Toàn bộ kế hoạch dưới đây xoay quanh việc bảo đảm vế thứ hai.

---

## 1. Kiến trúc 5 tầng

```
T0  KHO SURFACE FORM     mined từ text thật + KB đã lọc
         │                (KHÔNG lấy dạng chuẩn của KB)
         ▼
T1  KỊCH BẢN CA BỆNH     LLM đề xuất bộ khái niệm y khoa NHẤT QUÁN
         │                → KB xác thực từng cái, loại cái bịa
         ▼
    ┌────┴────────────────────────────┐
    ▼                                 ▼
T2A KHỐI CẤU TRÚC              T2B PHẦN VĂN XUÔI
    Template điền chỗ trống         LLM viết, BẮT BUỘC chứa
    KHÔNG dùng LLM                  nguyên văn các cụm cho trước
    → nhãn ĐÚNG 100%                → dò lại bằng tìm chuỗi chính xác
    theo cấu tạo                    → thiếu/lệch ⇒ SINH LẠI
    └────┬────────────────────────────┘
         ▼
T3  CỔNG KIỂM ĐỊNH        6 điều kiện, trượt bất kỳ ⇒ LOẠI mẫu
         ▼
T4  NHIỄU HOÁ CÓ KIỂM SOÁT  mô phỏng lỗi gõ THẬT của đề thi
         │                   (không bao giờ chạm vào bên trong span)
         ▼
    Dataset + báo cáo chỉ số
```

---

## 2. Tầng 0 — Kho surface form (nền móng)

### Vấn đề: KB không dùng trực tiếp được

Đo trên chính KB của dự án:

| KB | Tổng | Dạng dùng được trong văn bản Việt |
|---|---|---|
| RxNorm | 129.690 term | **13.2%** (≤2 từ, không chứa số) |
| ICD-10 VN | 14.627 term | **28%** (≤6 từ) |

87% RxNorm là kiểu `Tribenzor 40/5/12.5 (olmesartan medoxomil / amLODIPine (as amLODIPine besylate) / HCTZ) Oral Tablet` — **bác sĩ Việt không bao giờ viết như vậy**. 6.415 term ICD dài ≥10 từ là mô tả phân loại, không phải cách ghi bệnh án.

`data/dataset` lấy mẫu đúng từ phần này ⇒ văn bản phi tự nhiên.

### Cách xây kho đúng

**Nguồn 1 — Khai thác từ văn bản THẬT (ưu tiên cao nhất).**
Ta có 100 file đề thi (không nhãn nhưng là text thật) + 100 file `dataset2`. Khai thác cụm ứng viên:
- Toàn bộ nội dung bullet trong khối bệnh án (1.277 bullet) — đây là cách ghi thật
- 490 thực thể đã gán của `dataset2` — surface form thật, đã kiểm
- Cụm đứng sau các mẫu dẫn: `"chẩn đoán ..."`, `"bệnh nhân bị ..."`, `"xét nghiệm ..."`

**Nguồn 2 — KB đã lọc.**
- RxNorm: giữ term ≤2 từ, không chứa số → ~17.000 tên hoạt chất
- ICD-VN: giữ term ≤6 từ → ~4.159 tên bệnh
- Bỏ hoàn toàn phần còn lại

**Nguồn 3 — Sinh theo luật (cho `KẾT_QUẢ_XÉT_NGHIỆM`).**
Loại này **không cần LLM và không cần KB** — sinh bằng công thức:
```
{giá trị} {đơn vị}   → "6,4 mmol/l", "14.99 G/L", "92 g/L", "2.5 ng/mL"
{kết luận}           → "âm tính", "dương tính", "men gan tăng", "tăng nhẹ"
```
Nhãn chính xác tuyệt đối, chi phí bằng không. Đây là loại đang thiếu nhất (13 mẫu) mà lại dễ sinh nhất.

**Đầu ra T0:** file `inventory.json`
```json
{
  "TRIỆU_CHỨNG":        ["đau bụng vùng hạ sườn phải", "khó thở khi gắng sức", ...],
  "CHẨN_ĐOÁN":          ["viêm dạ dày", "hội chứng thận hư", ...],
  "THUỐC":              ["omeprazole", "kháng sinh", "thuốc giảm đau opioid", ...],
  "TÊN_XÉT_NGHIỆM":     ["công thức máu", "siêu âm tim", "nội soi dạ dày", ...],
  "KẾT_QUẢ_XÉT_NGHIỆM": ["6,4 mmol/l", "âm tính", "men gan tăng", ...]
}
```
Mục tiêu: **≥800 surface form mỗi loại** để đủ đa dạng, tránh model học thuộc.

---

## 3. Tầng 1 — Kịch bản ca bệnh (chống vô lý y khoa)

**Vấn đề:** ghép ngẫu nhiên sinh ra ca vô nghĩa — *"bệnh nhân gãy xương đùi, điều trị bằng thuốc nhỏ mắt, xét nghiệm nội soi dạ dày"*. Model học vào sẽ nhiễu.

**Giải:** dùng LLM ĐÚNG SỞ TRƯỜNG của nó — **kiến thức y khoa**, không phải gán nhãn.

Prompt (Qwen3-8B):
```
Cho chẩn đoán chính: "{diagnosis}"
Liệt kê các khái niệm y khoa thường đi kèm, mỗi dòng một mục:
TC|<triệu chứng>     (4-6 mục)
TH|<thuốc điều trị>  (2-3 mục)
TX|<xét nghiệm thường chỉ định>  (2-3 mục)
Dùng cách viết của bác sĩ Việt Nam, ngắn gọn. Không giải thích.
```

**Chốt chặn ảo giác — đây là điểm mấu chốt:**
Mỗi chuỗi LLM trả về **phải được KB xác thực** mới được dùng:
- `TH|...` → phải khớp RxNorm (sau chuẩn hoá) hoặc nằm trong danh sách nhóm thuốc đã duyệt
- `TC|`, `CD|` → phải khớp ICD hoặc kho surface form T0
- Không khớp ⇒ **loại bỏ mục đó**, không loại cả ca

LLM có bịa tên thuốc cũng vô hại: chuỗi bịa không có trong RxNorm ⇒ bị loại trước khi vào dữ liệu.

**Đầu ra T1:** một `case` gồm 8–14 khái niệm nhất quán, mỗi cái đã biết loại và đã được KB xác thực.

---

## 4. Tầng 2A — Khối bệnh án cấu trúc: KHÔNG DÙNG LLM

Đây là phần **đang thiếu 100%** ở cả hai bộ, và cũng là phần **dễ làm đúng nhất**. Khối này trong đề thi rõ ràng sinh từ template (còn nguyên placeholder `Không ghi rõ`), nên tái tạo bằng code là đủ.

Vì tự ghép chuỗi nên **biết chính xác từng offset** — không cần tìm kiếm, không thể sai.

```python
def build_clinical_block(case, rng):
    """Sinh khối bệnh án + nhãn. Offset tính theo cấu tạo -> đúng 100%."""
    parts, ents = [], []
    cursor = 0

    def emit(line):                       # dòng không chứa thực thể
        nonlocal cursor
        parts.append(line); cursor += len(line) + 1

    def emit_bullet(text, etype):         # dòng bullet CÓ thực thể
        nonlocal cursor
        prefix = '    - '
        start = cursor + len(prefix)
        parts.append(prefix + text)
        ents.append({'text': text, 'type': etype,
                     'position': [start, start + len(text)]})
        cursor += len(prefix) + len(text) + 1

    emit('2.  Tiền sử bệnh hiện tại')
    emit('    Lý do nhập viện')
    for s in case['symptoms'][:2]:
        emit_bullet(s, 'TRIỆU_CHỨNG')
    emit('    Đặc điểm triệu chứng')
    emit('    - Mức độ nghiêm trọng: Không ghi rõ')     # placeholder, KHÔNG gán nhãn
    emit('    Các bệnh lý mạn tính')
    for d in case['diagnoses'][:2]:
        emit_bullet(d, 'CHẨN_ĐOÁN')
    emit('')
    emit('3.  Đánh giá tại bệnh viện')
    emit('    Kết quả xét nghiệm')
    for t, v in case['tests']:
        emit_bullet(t, 'TÊN_XÉT_NGHIỆM')
        emit_bullet(v, 'KẾT_QUẢ_XÉT_NGHIỆM')
    emit('    Các thủ thuật đã thực hiện')
    for p in case['procedures']:
        emit_bullet(p, 'TÊN_XÉT_NGHIỆM')
    emit('    Thuốc trước khi nhập viện')
    for m in case['drugs']:
        emit_bullet(m, 'THUỐC')

    return '\n'.join(parts), ents
```

**Bắt buộc đa dạng hoá** (nếu không model học thuộc template):
- Xáo thứ tự các mục, bỏ ngẫu nhiên 1–3 mục
- Đổi luân phiên tên heading: `Triệu chứng hiện tại` / `Các triệu chứng hiện tại` / `Dấu hiệu lâm sàng`
- Đổi ký hiệu bullet: `-` / `•` / `*`
- Đổi độ thụt lề: 0 / 2 / 4 dấu cách
- Đôi khi viết `- Tên xét nghiệm: giá trị` trên **một dòng** thay vì hai dòng (đề thi có cả hai kiểu)

**Chi phí: 0 giây LLM. Độ chính xác nhãn: 100%.** Riêng tầng này đã lấp được lỗ hổng lớn nhất.

---

## 5. Tầng 2B — Phần văn xuôi: LLM viết có ràng buộc

Prompt:
```
Viết một đoạn hỏi–đáp giữa bệnh nhân và bác sĩ bằng tiếng Việt tự nhiên.

BẮT BUỘC dùng NGUYÊN VĂN, không sửa một chữ nào, các cụm sau:
- đau bụng vùng hạ sườn phải
- buồn nôn
- viêm dạ dày
- omeprazole

YÊU CẦU:
- Dài 180-260 từ.
- KHÔNG nhắc tới khái niệm y khoa nào khác ngoài các cụm trên.
- Viết như bài tư vấn y tế trên web: bệnh nhân hỏi, bác sĩ trả lời.
- Không dùng gạch đầu dòng, không liệt kê.
```

### Neo nhãn: tìm chuỗi chính xác, không suy đoán

```python
def anchor_required(text, required):
    """required = [(surface_form, type), ...]. Trả None nếu mẫu KHÔNG dùng được."""
    ents = []
    for surface, etype in required:
        hits = [m.start() for m in re.finditer(re.escape(surface), text)]
        if len(hits) == 0:
            return None                    # LLM bỏ quên -> SINH LẠI
        if len(hits) > 1:
            return None                    # xuất hiện nhiều lần -> mơ hồ, SINH LẠI
        s = hits[0]
        ents.append({'text': surface, 'type': etype,
                     'position': [s, s + len(surface)]})
    return ents
```

Không tìm thấy ⇒ sinh lại (tối đa 3 lần) ⇒ vẫn hỏng thì bỏ ca. **Không bao giờ "đoán gần đúng".**

### Lưới an toàn cho FALSE NEGATIVE — phần quan trọng nhất của tầng này

Rủi ro lớn nhất: LLM tự thêm khái niệm y khoa **ngoài danh sách**. Ví dụ ta yêu cầu 4 cụm nhưng nó viết thêm `"sốt cao"`. Cụm đó **có thật trong text mà không có nhãn** ⇒ dạy model bỏ sót ⇒ đúng căn bệnh đang mắc.

**Giải: quét từ điển ngược.**

```python
def sweep_unlabeled(text, ents, inventory):
    """Quét TOÀN BỘ kho surface form trên text. Cụm nào xuất hiện mà chưa
    có nhãn -> hoặc gán bổ sung (khớp từ điển = chính xác, không cần LLM),
    hoặc loại mẫu. Đây là chỗ biến điểm yếu thành điểm mạnh."""
    taken = [(e['position'][0], e['position'][1]) for e in ents]
    extra = []
    for etype, forms in inventory.items():
        for f in forms:
            for m in re.finditer(re.escape(f), text):
                a, b = m.start(), m.end()
                if any(a < y and x < b for x, y in taken):
                    continue                       # đã nằm trong span khác
                extra.append({'text': f, 'type': etype, 'position': [a, b]})
                taken.append((a, b))
    return extra
```

Cụm thêm được gán bằng **khớp từ điển chính xác**, không qua LLM ⇒ nhãn vẫn tin được.

---

## 6. Tầng 3 — Cổng kiểm định (trượt 1 điều kiện là loại cả mẫu)

| # | Điều kiện | Ngưỡng | Chống lỗi gì |
|---|---|---|---|
| 1 | `raw[start:end] == text` với **mọi** thực thể | 100% | Lệch offset |
| 2 | **Tỷ lệ từ nằm trong thực thể** | **8% – 18%** | Bệnh của `data/dataset` (55.6%) |
| 3 | Không có 2 span chồng lấn | 0 ca | Nhãn mâu thuẫn |
| 4 | Mọi cụm bắt buộc tìm thấy đúng 1 lần | 100% | LLM bỏ quên / sửa chữ |
| 5 | Quét từ điển ngược không còn cụm chưa gán | 0 sót | False negative |
| 6 | Độ dài file 1.500–4.000 ký tự | — | Tài liệu quá ngắn (382 ký tự) |

Điều kiện **số 2 là quan trọng nhất** — nó là thứ duy nhất phân biệt "sinh ngược đúng" với "dán chuỗi KB".

Ghi log tỷ lệ loại. **Nếu loại >40%, dừng lại sửa prompt**, đừng hạ ngưỡng.

---

## 7. Tầng 4 — Nhiễu hoá có kiểm soát

Đề thi thật **có lỗi gõ tự nhiên**: `"bệnh dạithường"`, `"điên dạiở"`, `"địnhkhai"` — dạng **dính hai từ liền nhau**, không phải hoán vị ký tự.

```python
def add_realistic_noise(text, ents, rate=0.03):
    """Chỉ dính từ ở ranh giới câu/từ, TUYỆT ĐỐI không chạm vào bên trong
    span thực thể (sẽ phá nhãn). Mọi thay đổi phải dịch lại offset."""
```

**Ba quy tắc bắt buộc:**
1. Chỉ nhiễu ở vùng **ngoài** mọi span thực thể
2. Mỗi lần sửa phải **dịch lại toàn bộ offset** phía sau
3. Tỷ lệ **3–5%**, không hơn

**Không làm:** hoán vị ký tự trong từ (`Khho anội`, `36 tổui`) — dạng nhiễu này **không tồn tại** trong đề thi, học vào chỉ tổ hại.

---

## 8. Kế hoạch số lượng & chi phí

| Nguồn | Số file | Thực thể/file | Tổng thực thể | Cần LLM? | Nhãn |
|---|---|---|---|---|---|
| **T2A** khối cấu trúc | 400 | ~8 | **3.200** | ❌ Không | 100% đúng theo cấu tạo |
| **T2B** văn xuôi | 400 | ~5 | **2.000** | ✅ Có (đã kiểm định) | Neo bằng tìm chuỗi chính xác |
| **Tổng** | 400 (ghép cả 2 vào cùng file) | ~13 | **~5.200** | | |

Mỗi file = phần văn xuôi + khối cấu trúc chèn vào → **đúng cấu trúc đề thi**.

**Chi phí thời gian (Qwen3-8B, 2×T4 — đã đo throughput ở pipeline hiện tại):**

| Bước | Ước tính |
|---|---|
| T1 sinh kịch bản (400 lượt) | ~8 phút |
| T2A khối cấu trúc | **~0 giây** (thuần code) |
| T2B văn xuôi (400 lượt, ~250 từ) | ~25 phút |
| Sinh lại phần bị loại (~30%) | ~10 phút |
| **Tổng** | **< 1 giờ GPU** |

Tỷ lệ loại dự kiến 25–40%, nên sinh dư ~1.5 lần.

---

## 9. Tập kiểm định — không có là mù

Dữ liệu tổng hợp luôn có rủi ro **lệch phân bố**: model giỏi trên data sinh ra nhưng kém trên đề thi thật. Chỉ một cách duy nhất phát hiện được:

> **Gán tay 5–10 file từ chính bộ đề thi**, chỉ dùng để ĐO, không dùng để train.

Không có tập này thì train xong không biết tốt hay xấu, lại quay về đoán mù như hiện tại. Đây là **điều kiện tiên quyết**, không phải tuỳ chọn.

Chỉ số theo dõi: P/R/F1 **theo từng loại** trên tập kiểm định thật, so với model hiện tại (F1 0.8178 nhưng chỉ 2 loại).

---

## 10. Vì sao kế hoạch này tránh được cả hai cái bẫy đã gặp

| Bẫy đã gặp | Cơ chế chặn |
|---|---|
| LLM gán nhãn sai (`dataset2`, recall 53%) | **LLM không bao giờ gán nhãn.** Nhãn có trước, hoặc neo bằng tìm chuỗi chính xác |
| LLM ảo giác tên thuốc/bệnh | **KB xác thực** mọi chuỗi ở T1; không khớp ⇒ loại |
| Dán chuỗi KB, mất ngữ cảnh (`data/dataset`, 55.6%) | **Cổng số 2**: tỷ lệ từ trong thực thể phải 8–18%, ngoài khoảng ⇒ loại mẫu |
| Dùng dạng chuẩn KB phi tự nhiên | T0 chỉ lấy surface form **khai thác từ text thật** + KB đã lọc (RxNorm ≤2 từ, ICD ≤6 từ) |
| Thiếu khối bệnh án cấu trúc | T2A sinh bằng template, **không cần LLM**, nhãn đúng 100% |
| False negative (thực thể không nhãn) | **Quét từ điển ngược** (cổng số 5) |
| Nhiễu nhân tạo sai kiểu | T4 chỉ mô phỏng lỗi dính từ **có thật** trong đề thi, và không bao giờ chạm vào span |
| Lệch phân bố tổng hợp ↔ thật | Tập kiểm định gán tay trên **file đề thi thật** |

---

## 11. Thứ tự thi công

| # | Việc | Phụ thuộc | Ước tính |
|---|---|---|---|
| 1 | T0 — dựng `inventory.json` (khai thác + lọc KB + sinh KẾT_QUẢ theo luật) | — | 1 buổi |
| 2 | T2A — code sinh khối cấu trúc + đa dạng hoá | 1 | 1 buổi |
| 3 | T3 — code 6 cổng kiểm định + báo cáo chỉ số | 1 | nửa buổi |
| 4 | **Gán tay 5–10 file đề thi làm tập kiểm định** | — | 1–2 giờ |
| 5 | T1 + T2B — sinh kịch bản & văn xuôi bằng Qwen | 1, 3 | 1 buổi + 1h GPU |
| 6 | T4 — nhiễu hoá | 3 | nửa buổi |
| 7 | Train encoder 5 loại + đo trên tập kiểm định (4) | tất cả | 1 buổi |

**Có thể làm ngay bước 1–4 mà không cần GPU.** Riêng bước 2 (khối cấu trúc) đã lấp được lỗ hổng lớn nhất và không tốn một giây LLM nào — nên làm trước tiên.
