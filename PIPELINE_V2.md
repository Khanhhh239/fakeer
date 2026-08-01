# PIPELINE V2 — thiết kế đầy đủ

Bản thiết kế để duyệt trước khi code. Mọi con số đo từ 100 file `input/` và
bài nộp thật `ner_submit.zip` (19.07 điểm, WER 75.97%).

---

## 0. Ba nguyên lý rút ra từ đo đạc

### NL1 — Bỏ sót và trích thừa phạt NGANG NHAU; chỉ sai loại phạt gấp đôi

`WER = (S+D+I)/N_ref`. Một khái niệm `w` từ:

| | Chi phí |
|---|---|
| Bỏ sót | `+w/N` |
| Trích thừa | `+w/N` |
| Đúng text, sai loại | `+2w/N` (gold miss **và** pred thừa) |

→ Ngưỡng tối ưu cho "có trích không" là **0.5**.
→ Toàn bộ ngân sách thận trọng phải dồn vào **quyết định loại**, không phải
quyết định trích.

V1 làm ngược: chặn rất chặt việc trích (TAU 0.75/0.55) nhưng để loại tự do.

### NL2 — Cấu trúc tài liệu tự khai báo loại, và V1 bỏ qua hoàn toàn

**99% bullet (1264/1277) có heading cha**, và heading nói thẳng loại:

| Heading | Số bullet | Loại đúng |
|---|---|---|
| đặc điểm triệu chứng / triệu chứng hiện tại / dấu hiệu lâm sàng | 353 | TRIỆU_CHỨNG |
| các bệnh lý mạn tính / mãn tính | 123 | CHẨN_ĐOÁN |
| kết quả xét nghiệm / kết quả chẩn đoán hình ảnh | 73 | TÊN + KẾT_QUẢ |
| các thủ thuật đã thực hiện | 55 | TÊN_XÉT_NGHIỆM |
| thuốc trước khi nhập viện | 43 | THUỐC |

Đối chiếu với bài nộp — V1 mâu thuẫn trực tiếp với heading:

| Heading | Trống | Loại V1 đã gán |
|---|---|---|
| các thủ thuật đã thực hiện (55) | **34** | THUỐC 15, CHẨN_ĐOÁN 8, TRIỆU_CHỨNG 6, **TÊN_XÉT_NGHIỆM 0** |
| các bệnh lý mạn tính (123) | 28 | CHẨN_ĐOÁN 72, **TRIỆU_CHỨNG 46** |

46 span dưới "bệnh lý mạn tính" bị gán TRIỆU_CHỨNG — mỗi cái phạt **gấp đôi**.
55 bullet thủ thuật không sinh ra một TÊN_XÉT_NGHIỆM nào.

**Đây là tín hiệu miễn phí, độ phủ 99%, hiện đang bị vứt đi.**

### NL3 — Trần của V1 bị chặn bởi nguồn, không bởi tham số

| Nguồn V1 | Bắt được | Trần cứng |
|---|---|---|
| Encoder PhoNER | TRIỆU_CHỨNG, CHẨN_ĐOÁN | F1 0.82, domain lệch |
| Luật `số + đơn vị` | 2 loại xét nghiệm | **Chỉ khi có số+đơn vị** |
| RxNorm | THUỐC | Tốt |

`siêu âm tim`, `nội soi dạ dày`, `chụp CT sọ não` không bao giờ khớp
`số + đơn vị` → không ngưỡng nào cứu được. Đo: **TÊN_XÉT_NGHIỆM bắt 14.5%**
(nội soi 30→0, siêu âm 26→0, X-quang 15→0).

Phải đổi nguồn, không phải đổi tham số.

---

## 1. Pipeline V2

```
                    input/N.txt
                         │
   ┌─────────────────────▼─────────────────────┐
   │ K1  PHÂN ĐOẠN CÓ NGỮ CẢNH        (CPU)    │
   │     → unit = (text, start, end, heading,  │
   │              zone, is_bullet)             │
   └─────────────────────┬─────────────────────┘
                         │
        ┌────────────────┼────────────────┬──────────────┐
        ▼                ▼                ▼              ▼
   ┌─────────┐     ┌──────────┐    ┌──────────┐   ┌───────────┐
   │ K2 LLM  │     │ K3 LUẬT  │    │ K4 RxNorm│   │ K5 ENCODER│
   │ 5 loại  │     │ số+đơn vị│    │  THUỐC   │   │  (vote)   │
   │ NGUỒN   │     │ tất định │    │ từ điển  │   │  phụ trợ  │
   │ CHÍNH   │     │          │    │          │   │           │
   └────┬────┘     └────┬─────┘    └────┬─────┘   └─────┬─────┘
        │               │               │               │
   ┌────▼───────────────▼───────────────▼───────────────▼─────┐
   │ K6  NEO & XÁC THỰC — span PHẢI là substring văn bản gốc  │
   │     text == src[start:end], sai → BỎ                      │
   └────────────────────────┬──────────────────────────────────┘
                            │
   ┌────────────────────────▼──────────────────────────────────┐
   │ K7  HỢP NHẤT — heading prior + vote nguồn + giải xung đột │
   └────────────────────────┬──────────────────────────────────┘
                            │
   ┌────────────────────────▼──────────────────────────────────┐
   │ K8  HẬU XỬ LÝ — chuẩn biên, DP chồng lấn, mở rộng KB      │
   └────────────────────────┬──────────────────────────────────┘
                            │
                    submit/N.json  (format BTC)
```

---

## 2. K1 — Phân đoạn có ngữ cảnh

**Đây là khối quan trọng nhất của V2** vì nó sinh ra `heading` (NL2) và làm cho
LLM chỉ phải đọc 1 dòng thay vì 3000 ký tự.

### Đầu ra: một `unit`

```python
{
  'text'      : 'Công thức máu, CRP, máu lắng',
  'start'     : 1843, 'end': 1871,          # src[start:end] == text
  'heading'   : 'Kết quả xét nghiệm',        # heading gần nhất phía trên
  'zone'      : 'clinical',                  # 'clinical' | 'advice'
  'is_bullet' : True,
}
```

### Thuật toán

1. Duyệt từng dòng, giữ offset tuyệt đối.
2. Nhận **heading**: dòng không phải bullet, ≤60 ký tự, không kết thúc bằng `.`,
   bắt đầu bằng chữ hoa (có thể có tiền tố `N.`). → cập nhật `heading` hiện tại.
3. Nhận **bullet**: `^\s*[-•*]\s+(.+)$` → 1 unit, `is_bullet=True`.
4. Dòng văn xuôi: tách câu theo `[.;!?]` + xuống dòng. Câu > 40 từ tách tiếp
   theo dấu phẩy. → nhiều unit, `is_bullet=False`.
5. `zone`: `clinical` nếu nằm sau mốc bệnh án cấu trúc (mục `2.`/`3.` hoặc
   heading bệnh án đầu tiên), ngược lại `advice`.

**Bất biến bắt buộc**: `src[u.start:u.end] == u.text` với mọi unit.
Test bằng assert trên cả 100 file trước khi chạy tiếp.

### Vì sao `zone` là một trường, không phải bộ lọc

Chưa biết gold có tính vùng tư vấn không (mật độ 2 vùng gần bằng nhau:
11.4 vs 9.7 /1000 ký tự → dữ liệu **không** kết luận được).

→ Để `zone` thành **tham số bật/tắt**, không hard-code. Nộp 2 lần đọc ra ngay
câu trả lời. Đây là thiết kế cho phép *đo*, thay vì đoán.

**Ước tính**: ~4000 unit / 100 file (1277 bullet + phần văn xuôi).

---

## 3. K2 — LLM sinh thực thể (nguồn chính)

### Vì sao LLM phải là nguồn chính, không phải lớp vá

Chỉ LLM mới làm được 3 việc mà luật không làm được mà **không** phải hard-code
từ điển tên xét nghiệm:

1. `Công thức máu, CRP, máu lắng` → 3 TÊN_XÉT_NGHIỆM (không có số+đơn vị nào).
2. Phân biệt `men gan` (TÊN, khi liệt kê) với `men gan tăng` (KẾT_QUẢ, có kết
   luận) — bằng ngữ cảnh, không bằng hình dạng chuỗi.
3. `Lưỡi đỏ như dâu tây` → TRIỆU_CHỨNG (encoder domain-lệch bỏ sót).

### Prompt

System (cố định, dùng chung):

```
Bạn là bác sĩ trích xuất thông tin từ bệnh án tiếng Việt.
Liệt kê thực thể y khoa trong ĐOẠN được cho.

TC = TRIỆU_CHỨNG   biểu hiện bệnh nhân khai / bác sĩ quan sát
                   (sốt, khó thở, yếu nửa người, lưỡi đỏ như dâu tây)
CD = CHẨN_ĐOÁN     tên bệnh, hội chứng
                   (viêm dạ dày, hội chứng thận hư, tai biến mạch máu não)
TH = THUỐC         tên thuốc, nhóm thuốc
                   (omeprazole, kháng sinh, thuốc giảm đau opioid)
TX = TÊN_XÉT_NGHIỆM  tên xét nghiệm / thăm dò / thủ thuật chẩn đoán
                   (công thức máu, CRP, siêu âm tim, nội soi dạ dày, chụp CT)
KQ = KẾT_QUẢ_XÉT_NGHIỆM  giá trị hoặc kết luận của xét nghiệm
                   (6,4 mmol/l, âm tính, men gan tăng, 92 g/L)

QUY TẮC:
1. COPY NGUYÊN VĂN từ đoạn. Không sửa chữ, không đổi dấu.
2. Lấy cụm ĐẦY ĐỦ NHẤT. "đau bụng vùng hạ sườn phải" là MỘT thực thể,
   không tách thành "đau bụng".
3. Bỏ qua: thời gian, tuổi, tên người, lời khuyên, câu hỏi, "Không ghi rõ".
4. Mục đang xét cho biết loại thường gặp — hãy dùng nó.

Mỗi dòng một thực thể:  MÃ|nguyên văn
Không có gì:            KHÔNG
```

User (mỗi unit):

```
Mục: {heading}
Đoạn: {text}
```

Kèm 4 few-shot lấy từ chính domain, trong đó **bắt buộc có 1 ví dụ trả `KHÔNG`**
(nếu không, LLM sẽ luôn cố sinh ra thứ gì đó — lỗi kinh điển).

### Tham số

`temperature=0`, `max_tokens=160`, batch theo file.

### Vì sao format `MÃ|text` chứ không JSON

Ít token hơn, không có lỗi cú pháp JSON (thiếu ngoặc, dấu phẩy thừa), parse
bằng `split('|', 1)` — không thể hỏng. JSON chỉ có lợi khi cần cấu trúc lồng,
ở đây không cần.

---

## 4. K3–K5 — Ba nguồn còn lại

| Khối | Vai trò V1 | Vai trò V2 | Lý do |
|---|---|---|---|
| K3 luật số+đơn vị | Nguồn chính XN | **Xác nhận độ chính xác cao** | Tất định, 14/14 test pass — giữ nguyên, chỉ đổi vai |
| K4 RxNorm | Nguồn chính THUỐC | Giữ nguyên | 138k tên, chính xác cao |
| K5 encoder | Nguồn chính TC/CD | **Phiếu bầu phụ** | F1 0.82 domain lệch — không còn là nguồn duy nhất |

Không bỏ khối nào. V2 chỉ **đổi thứ tự tin cậy**, giữ mọi thứ đang hoạt động.

---

## 5. K6 — Neo & xác thực (hàng rào chống ảo giác)

Bất biến sống còn: **LLM không bao giờ được "viết ra" một span.**
Nó chỉ được *chỉ vào* một đoạn trong văn bản gốc.

```
anchor(gen_text, unit) →
  1. exact substring                    → nhận
  2. không phân biệt hoa/thường          → nhận
  3. chuẩn hoá khoảng trắng thừa         → nhận
  4. bỏ dấu câu ở hai biên               → nhận
  5. fuzzy: trượt cửa sổ cùng số từ,
     Levenshtein ≤ 15%                   → nhận, neo vào vị trí khớp tốt nhất
  6. thất bại                            → BỎ
```

Sau khi neo, span **luôn** lấy lại từ `src[start:end]` — không dùng chuỗi LLM sinh.
Nhờ đó `text == src[start:end]` đúng theo cấu trúc, không phải nhờ may mắn.

Bậc 5 (fuzzy) tồn tại vì LLM hay sửa chính tả (`dạiở` → `dại ở`), bỏ nó thì
mất recall một cách vô ích.

### Ba chặn bổ sung

1. **Giới hạn mật độ**: unit < 15 từ mà sinh > 6 thực thể → giữ các span dài
   nhất không chồng nhau, bỏ phần còn lại.
2. **Chặn cấu trúc theo loại** (đã có ở `65acb97`): số thuần ≠ TÊN_XÉT_NGHIỆM;
   KẾT_QUẢ phải có chữ số hoặc là định tính âm/dương tính.
3. **Chặn placeholder**: `Không ghi rõ`, `Không rõ`, `N/A` → bỏ.

---

## 6. K7 — Hợp nhất (nơi quyết định loại)

Đây là khối gánh NL1: *dồn toàn bộ thận trọng vào quyết định loại*.

### 6.1 Heading prior

```python
HEAD_PRIOR = {
  'triệu chứng|dấu hiệu lâm sàng|biểu hiện' : 'TRIỆU_CHỨNG',
  'bệnh lý mạn|bệnh lý mãn|bệnh mãn|
   chẩn đoán|phát hiện chẩn đoán'            : 'CHẨN_ĐOÁN',
  'thủ thuật|phẫu thuật'                     : 'TÊN_XÉT_NGHIỆM',
  'kết quả xét nghiệm|chẩn đoán hình ảnh|
   cận lâm sàng'                             : 'XÉT_NGHIỆM(TX|KQ)',
  'thuốc|điều trị'                           : 'THUỐC',
}
```

Không phải luật trích xuất — là **ngữ cảnh tài liệu**, đúng như cách bác sĩ
đọc: thấy mục "Các thủ thuật đã thực hiện" thì biết bên dưới là thủ thuật.

### 6.2 Chấm điểm

```
score(span, type) = w_nguồn
                  + 0.15 · [heading prior khớp type]
                  - 0.30 · [heading prior mâu thuẫn type]
                  + 0.20 · [≥2 nguồn độc lập đồng ý type]
```

| Nguồn | `w_nguồn` |
|---|---|
| Luật số+đơn vị | 1.00 |
| RxNorm khớp chính xác | 0.95 |
| LLM | 0.70 |
| Encoder | 0.60 |

### 6.3 Giải xung đột loại

Khi hai nguồn cho **cùng span** nhưng **khác loại** — đây chính là ca phạt gấp
đôi, phải xử lý riêng, không để điểm số tự quyết:

1. Luật số+đơn vị có ý kiến → **thắng tuyệt đối** (tất định).
2. RxNorm khớp chính xác và loại là THUỐC → **thắng**.
3. Còn lại → **heading prior quyết**.
4. Heading im lặng → hỏi LLM lần 2 dạng chọn-2-đáp-án
   (`StructuredOutputsParams(choice=[...])`, đã có sẵn ở V1), nhận nếu
   hậu nghiệm > 0.5; không đạt → **bỏ span** (thà mất 1× còn hơn sai 2×).

Bước 4 là chỗ duy nhất trong V2 áp ngưỡng cao — đúng chỗ nó có giá trị.

### 6.4 Ngưỡng

| Quyết định | Ngưỡng | Cơ sở |
|---|---|---|
| Có trích không | **0.50** | NL1, chứng minh toán |
| Chọn loại khi xung đột | **> 0.50** hậu nghiệm, thiếu → bỏ | phạt gấp đôi |

Bỏ hẳn TAU_TYPE=0.75 / TAU_LAB=0.55 của V1 — cả hai đều không có cơ sở.

**Lưu ý bắt buộc**: hàm `_posterior()` chỉ tính khi thấy **đủ mọi key** trong
top-k logprob, thiếu → trả 0.0. Đây là bug đã trả giá ở V1 (chuẩn hoá trên số
key có mặt → score luôn 1.0). Giữ nguyên bản đã sửa.

---

## 7. K8 — Hậu xử lý

1. **Chuẩn biên**: cắt bullet `-•*`, dấu câu, hư từ biên (`và`, `các`, `bị`,
   `có`, `là`). *(bug bullet đã sửa ở `65acb97`)*
2. **Giải chồng lấn**: DP chọn tập không chồng, tối đa `Σ score`
   (`select_non_overlapping`, đã có).
3. **Mở rộng span cụt bằng KB ICD** hai chiều (đã có, chưa đo hiệu quả).
4. **Xuất format BTC**: mảng phẳng, `candidates: []`, `assertions: []`,
   `position: [start, end]` *(đã xác nhận chấm được — 19.07 điểm không lỗi schema)*.
5. **Assert cuối**: nguyên văn + không chồng lấn + đủ 100 file.

---

## 8. Kiến trúc chạy — giữ 2 phase

Không đổi thứ đang chạy được. Lý do xung đột CUDA vẫn còn: torch (encoder) khởi
tạo CUDA ở tiến trình cha → vLLM spawn EngineCore lỗi `CUDA initialization error`.

| | Nội dung | GPU |
|---|---|---|
| **Phase 1** | K1 phân đoạn, K3 luật, K4 RxNorm, K5 encoder → `phase1/`, `units/` | torch |
| **Phase 2** | K2 LLM, K6 neo, K7 hợp nhất, K8 hậu xử lý → `submit/` | vLLM |

Phase 1 ghi thêm `units/N.json` (đầu ra K1) để Phase 2 không phải phân đoạn lại.

### Chi phí

Đo thật từ log Phase 2: **batch 50 prompt / 1.6s** (2×T4, TP=2).
V2 sinh danh sách thay vì 1 token → `max_tokens=160`.

| | Ước tính |
|---|---|
| Phase 1 | ~2 phút (đã đo: 61s/100 file) |
| Phase 2, ~4000 unit | **12–25 phút** |

Nằm gọn trong một kernel Kaggle.

---

## 9. Đo lường — điều kiện tiên quyết

V2 sửa hai lỗ hổng đo được, nhưng **không có gold thì vẫn là đánh cược**, lần
này trên kiến trúc mới nên sai sẽ khó truy hơn.

Gold nội bộ **5 file**: `3` (bệnh án đầy đủ), `21` (hỗn hợp), `2` (nhiều XN
liệt kê), `13` (gần thuần tư vấn), `24` (nhiều XN có số).

Đo trước khi nộp: P/R theo từng loại, WER mô phỏng, V1 vs V2.

Trả lời dứt điểm được câu hỏi treo: **gold có tính vùng tư vấn không** — câu
hỏi mà dữ liệu không tự trả lời được và hiện đang chi phối 49% số thực thể.

---

## 10. Tác động kỳ vọng

| Thay đổi | Sửa lỗi gì | Định lượng |
|---|---|---|
| Heading prior (NL2) | Sai loại (phạt ×2) | 46 span CD↦TC + 29 span thủ thuật sai loại |
| LLM-first cho XN | Bỏ sót | TÊN_XÉT_NGHIỆM 14.5% → kỳ vọng >70% (207 lần bỏ sót) |
| LLM trên bullet trống | Bỏ sót | 505 bullet trắng (39.6%) |
| Ngưỡng 0.5 | Bỏ sót | Toàn cục, gần như miễn phí |
| Bullet/dash *(đã xong)* | Sai text | `- ast`, `• Troponin I/T` |
| Chặn cấu trúc loại *(đã xong)* | Sai loại | `421`→TÊN, `PT - INR`→KẾT_QUẢ |

---

## 11. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| LLM-first đảo từ thiếu sang thừa | 3 chặn ở §5 + gold để đo |
| Vùng tư vấn: tăng recall ở đó có thể phản tác dụng | `zone` là tham số bật/tắt, probe 2 lần nộp |
| Heading prior sai ở file không theo template | Prior là **cộng điểm**, không phải ép cứng — vẫn thua nguồn tất định |
| LLM tách nhỏ cụm (`đau bụng` thay vì `đau bụng vùng hạ sườn phải`) | Quy tắc 2 trong prompt + ưu tiên span dài khi chồng lấn |
| Gold tôi tự gán lệch gold BTC | Chỉ dùng đo **thay đổi tương đối**, không tin tuyệt đối |

---

## 12. Thứ tự thi công

| # | Việc | Phụ thuộc |
|---|---|---|
| 1 | K1 phân đoạn + assert bất biến trên 100 file | — |
| 2 | Gold 5 file + bộ chấm nội bộ | K1 |
| 3 | Đo V1 trên gold → có mốc so sánh | 2 |
| 4 | K2 LLM + K6 neo | K1 |
| 5 | K7 hợp nhất + heading prior | 4 |
| 6 | Đo V2 trên gold, chỉnh ngưỡng bằng số | 3, 5 |
| 7 | Chạy 100 file, nộp | 6 |

Bước 2–3 là thứ V1 không có. Không có nó, bước 6 lại thành đoán.
