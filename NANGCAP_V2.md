# NÂNG CẤP V2 — chẩn đoán từ bài nộp thật và thiết kế lại

Viết sau lần nộp đầu tiên: **19.07 điểm, WER 75.97%**.
Mọi con số dưới đây đo từ chính `ner_submit.zip` đã nộp (2137 thực thể / 100 file)
đối chiếu với 100 file `input/*.txt`. Không có con số nào là ước đoán.

---

## 1. Chẩn đoán: vấn đề KHÔNG phải trích thừa, mà là BỎ SÓT

Suốt quá trình xây V1 tôi tối ưu theo nguyên tắc *"thà bỏ sót còn hơn làm thừa"*.
Đo lại trên bài nộp thật cho thấy nguyên tắc đó **sai với metric này**, và chính
nó là nguyên nhân lớn nhất kéo điểm xuống.

### 1.1 Vì sao nguyên tắc đó sai — chứng minh bằng công thức của đề

`WER = (S + D + I) / N_ref`, trong đó D = xoá (bỏ sót), I = chèn (trích thừa).

Gọi một khái niệm có `w` từ:

| Hành động | Chi phí WER |
|---|---|
| Bỏ sót một khái niệm gold | `D += w` → **+w/N** |
| Trích một khái niệm không có trong gold | `I += w` → **+w/N** |
| Trích đúng text, **sai loại** | `D += w` và `I += w` → **+2w/N** |

→ **Bỏ sót và trích thừa phạt NGANG NHAU.** Chỉ *sai loại* mới phạt gấp đôi.

Suy ra ngưỡng tối ưu. Với span mà xác suất nó thuộc gold là `q`:
- Kỳ vọng chi phí nếu trích: `(1−q)·w`
- Kỳ vọng chi phí nếu bỏ: `q·w`
- Trích có lợi khi `q > 0.5`

Tương tự với độ chắc về loại `p`: trích có lợi khi `p > 0.5`.

**Ngưỡng tối ưu lý thuyết là 0.5, không phải 0.75 / 0.55 như V1 đang đặt.**
Nguyên tắc đúng phải phát biểu lại là: *thà bỏ sót còn hơn gán SAI LOẠI* —
chỉ áp cho quyết định loại, không áp cho quyết định có trích hay không.

### 1.2 Số liệu bỏ sót

**Recall proxy** (không cần gold): trong bệnh án cấu trúc, mỗi dòng bullet
`- ...` gần như chắc chắn chứa ít nhất một thực thể.

```
Tổng bullet có nội dung : 1274
Bullet KHÔNG trích gì   : 505  (39.6%)
```

Mẫu bullet bị bỏ trắng hoàn toàn — đều là thực thể hiển nhiên:

| File | Bullet bị bỏ | Đáng ra là |
|---|---|---|
| 2 | `Lưỡi đỏ như dâu tây` | TRIỆU_CHỨNG (dấu hiệu kinh điển Kawasaki) |
| 2 | `Đỏ gan bàn tay – chân` | TRIỆU_CHỨNG |
| 2 | `Công thức máu, CRP, máu lắng` | TÊN_XÉT_NGHIỆM ×3 |
| 2 | `Men gan, albumin` | TÊN_XÉT_NGHIỆM ×2 |
| 2 | `Siêu âm tim` | TÊN_XÉT_NGHIỆM |
| 3 | `nhìn song thị` | TRIỆU_CHỨNG |
| 3 | `không thể chịu lực ở chân phải, liên tục khuỵu chân` | TRIỆU_CHỨNG |
| 1 | `Rối loạn vận động` | TRIỆU_CHỨNG |

### 1.3 Lỗ hổng nghiêm trọng nhất: TÊN_XÉT_NGHIỆM

Đối chiếu 38 từ khoá xét nghiệm phổ biến với bài nộp:

```
Lần xuất hiện trong 100 file : 242
Được trích là XÉT_NGHIỆM     :  35  (14.5%)
BỎ SÓT                       : 207
```

| Từ khoá | Xuất hiện | Trích được |
|---|---|---|
| nội soi | 30 | **0** |
| siêu âm | 26 | **0** |
| X-quang | 15 | **0** |
| men gan | 13 | **0** |
| lipid máu | 11 | **0** |
| sinh thiết | 8 | **0** |
| cộng hưởng từ | 7 | **0** |
| đông máu | 6 | **0** |
| ure | 6 | 6 |
| creatinin | 13 | 8 |

**Nguyên nhân gốc — lỗi thiết kế, không phải lỗi ngưỡng:**
`branch_b_lab_tests.py` chỉ nhận một đoạn là xét nghiệm khi nó khớp
`VALUE_ONLY = số + ĐƠN VỊ trong danh sách trắng`. Nhưng:

- **Xét nghiệm hình ảnh và thủ thuật không bao giờ có "số + đơn vị"** —
  `siêu âm tim`, `nội soi dạ dày`, `chụp CT sọ não`, `sinh thiết` → không bao giờ khớp.
- **Tên xét nghiệm liệt kê không kèm giá trị** cũng không khớp —
  `Công thức máu, CRP, máu lắng`.
- Encoder chỉ được train 2 loại (TRIỆU_CHỨNG / CHẨN_ĐOÁN từ nhãn
  `SYMPTOM_AND_DISEASE` của PhoNER_COVID19) nên **không có nguồn nào khác**
  bù lại được.

Kết quả: `TÊN_XÉT_NGHIỆM` chỉ có **67 thực thể / 100 file = 0,67 mỗi file**,
trong khi đây là 1 trong 5 loại được chấm.

### 1.4 Những lỗi đã sửa xong (commit `65acb97`)

| Lỗi | Bằng chứng trong bài nộp |
|---|---|
| Gạch đầu dòng dính vào tên | `"- ast"`, `"• Troponin I/T"`, `"- lipase"` |
| LLM đảo vai tên ↔ kết quả | `"HGB (Hemoglobin)"`, `"PT - INR"` → gán KẾT_QUẢ; `"421"`, `"336"` → gán TÊN |
| Tiêu đề đoạn bị trích | `"Kết quả xét nghiệm"`, `"Kết quả laboratory"` |

Đã sửa nhưng **chỉ chữa phần ngọn**. Lỗ hổng recall ở 1.2/1.3 mới là phần chính.

### 1.5 Cấu trúc dữ liệu test — đã hiểu ra

Test không phải bệnh án thuần. Nó là **bài tư vấn y khoa web (Q&A) được ghép
với một khối bệnh án cấu trúc**, thường theo template đánh số:

```
1.  Tiền sử bệnh          ← nội dung web Q&A (đôi khi bị cắt cụt giữa câu)
2.  Tiền sử bệnh hiện tại ← bệnh án cấu trúc, indent 4 space, bullet '-'
    Lý do nhập viện
    - yếu sức nửa người bên phải
    ...
3.  Đánh giá tại bệnh viện
    Dấu hiệu lâm sàng / Kết quả xét nghiệm / Các thủ thuật đã thực hiện
```

Đo được: 92/100 file có dấu hiệu khối cấu trúc; 70/100 có mốc đánh số rõ.
Thực thể hiện trích: **1090 trong khối cấu trúc, 1047 ngoài (49%)**.

**Câu hỏi chưa trả lời được:** gold có tính thực thể trong phần tư vấn chung
không (ví dụ `ung thư máu`, `đa u tủy` ở file 21 là bác sĩ giảng bệnh học, không
phải bệnh của bệnh nhân). Mật độ thực thể hai vùng gần bằng nhau
(11,4 vs 9,7 trên 1000 ký tự) nên **không kết luận được từ dữ liệu**.
→ Phải giải bằng gold nội bộ hoặc probe leaderboard, **không đoán**.

---

## 2. Thiết kế V2: LLM-first, ràng buộc bằng code

### 2.1 Vì sao phải đổi kiến trúc chứ không chỉnh tham số

Kiến trúc V1 đặt **luật** làm nguồn chính và **LLM** làm lớp vá. Trần của nó bị
chặn bởi chính luật:

| Nguồn | Loại bắt được | Trần |
|---|---|---|
| Encoder (PhoNER) | TRIỆU_CHỨNG, CHẨN_ĐOÁN | F1 0.82, domain lệch (bản tin COVID ≠ bệnh án) |
| Luật số+đơn vị | 2 loại xét nghiệm | **Chỉ khi có số + đơn vị** → mất toàn bộ hình ảnh/thủ thuật |
| Từ điển RxNorm | THUỐC | Tốt, giữ nguyên |

Không có cách chỉnh ngưỡng nào làm `siêu âm tim` khớp `VALUE_ONLY`. Phải đổi nguồn.

### 2.2 Kiến trúc mới

```
Văn bản gốc
   │
   ├─ Bước 1: tách ĐƠN VỊ NHỎ (mỗi bullet, mỗi câu) + giữ offset chính xác
   │
   ├─ Bước 2: LLM sinh thực thể cho TỪNG đơn vị  ◄── NGUỒN CHÍNH (recall)
   │           Qwen3-8B, cả 5 loại trong một lượt
   │
   ├─ Bước 3: VERIFY bằng code — span phải là substring NGUYÊN VĂN
   │           không khớp → BỎ (hàng rào chống ảo giác, không tin lời LLM)
   │
   ├─ Bước 4: HỢP NHẤT với nguồn độ-chính-xác-cao
   │           • luật Tier-0 (số+đơn vị)  • từ điển RxNorm  • encoder
   │           chồng lấn → ưu tiên nguồn chính xác cao
   │
   └─ Bước 5: hậu xử lý — giải chồng lấn (DP), chuẩn biên, xuất format BTC
```

**Điểm mấu chốt giữ nguyên từ V1:** span **luôn** được cắt từ văn bản gốc và
verify `text == src[start:end]`. LLM không bao giờ được phép "viết ra" một span.
Đây là bất biến đã cứu V1 khỏi ảo giác, giữ nguyên trong V2.

### 2.3 Vì sao LLM-first bắt được cái luật không bắt được

Một prompt duy nhất trên đơn vị `- Công thức máu, CRP, máu lắng` cho ra 3
`TÊN_XÉT_NGHIỆM`. Không luật nào làm được điều đó mà không hard-code từ điển
tên xét nghiệm — thứ vừa không đầy đủ vừa đi ngược yêu cầu "đừng hard-code luật".

LLM cũng là thứ duy nhất phân biệt được `men gan tăng` (KẾT_QUẢ, vì có kết luận)
với `men gan` (TÊN, khi chỉ liệt kê) — bằng ngữ cảnh, không bằng hình dạng chuỗi.

### 2.4 Kiểm soát ảo giác — 4 lớp, tất cả bằng code

1. **Substring cứng**: span không có nguyên văn trong đơn vị → bỏ.
2. **Giới hạn số lượng**: một đơn vị < 15 từ mà LLM sinh > 6 thực thể → nghi
   ngờ, chỉ giữ các span dài nhất không chồng nhau.
3. **Chặn cấu trúc theo loại** (đã có ở `65acb97`, giữ và mở rộng):
   số thuần không thể là TÊN_XÉT_NGHIỆM; KẾT_QUẢ phải có chữ số hoặc là
   định tính âm/dương tính.
4. **Nguồn chính xác cao thắng**: chồng lấn với luật/từ điển → lấy luật/từ điển.

### 2.5 Chi phí chạy — đã ước tính từ log thật

Log Phase 2 thật: batch 50 prompt xong trong **1,6s** (2 GPU T4, TP=2).
100 file ≈ 3000–5000 đơn vị. Output dài hơn (danh sách thay vì 1 token),
`max_tokens=160`.

→ Ước tính **12–25 phút** cho toàn bộ 100 file. Hoàn toàn khả thi trong
một kernel Kaggle. (V1 Phase 2 hiện chạy ~12 phút.)

---

## 3. Điều kiện tiên quyết: PHẢI CÓ GOLD NỘI BỘ

Đây là việc quan trọng nhất, và là thứ V1 thiếu từ đầu.

**Hiện trạng: đang bay mù.** Không biết recall thật, không biết precision thật,
không biết gold có tính phần tư vấn chung không. Mỗi thay đổi đều là đánh cược,
và mỗi lần nộp chỉ trả về **một** con số.

**Đề xuất:** gán nhãn thủ công **5 file** (khoảng 1–2 giờ), chọn đại diện:

| File | Vì sao chọn |
|---|---|
| 3 | Bệnh án cấu trúc đầy đủ nhất (mục 1/2/3, nhiều bullet) |
| 21 | Hỗn hợp: tư vấn chung + khối bệnh án chèn |
| 2 | Nhiều xét nghiệm liệt kê không kèm giá trị |
| 13 | Gần như thuần tư vấn, khối chèn rất nhỏ |
| 24 | Nhiều xét nghiệm có số + đơn vị |

Có 5 file này thì:
- Đo được P/R/WER thật **trước khi nộp**
- Trả lời dứt điểm câu hỏi "gold có tính phần tư vấn chung không"
- Chỉnh ngưỡng bằng số đo thay vì cảm giác
- Mỗi thay đổi biết ngay tốt lên hay xấu đi

**Không có bước này, V2 vẫn là đánh cược — chỉ là đánh cược đắt hơn.**

### 3.1 Phương án thay thế nếu không làm gold: probe leaderboard

Nếu được nộp nhiều lần, dùng chính leaderboard làm oracle. Mỗi lần nộp đổi
đúng **một** biến để đọc được tín hiệu sạch:

| Lần | Cấu hình | Đọc được gì |
|---|---|---|
| A | V2 đầy đủ, trích cả hai vùng | Baseline mới |
| B | Chỉ trích trong khối bệnh án cấu trúc | Gold có tính phần tư vấn không |
| C | Hạ mọi ngưỡng về 0.5 | Đang thiếu hay đang thừa |

Chậm hơn gold nội bộ và tốn lượt nộp, nhưng vẫn hơn đoán.

---

## 4. Lộ trình theo thứ tự ưu tiên

| # | Việc | Tác động ước tính | Công |
|---|---|---|---|
| 1 | **Gold nội bộ 5 file** | Điều kiện tiên quyết cho mọi việc dưới | 1–2h |
| 2 | **LLM-first cho TÊN/KẾT_QUẢ xét nghiệm** | Lớn nhất — đang bắt 14,5% | Trung bình |
| 3 | **LLM-first cho TRIỆU_CHỨNG/CHẨN_ĐOÁN** trên bullet trống | Lớn — 39,6% bullet trắng | Trung bình |
| 4 | **Hạ ngưỡng về 0.5** (có cơ sở toán ở §1.1) | Vừa, gần như miễn phí | Rất nhỏ |
| 5 | Mở rộng span cụt bằng KB (đã có, chưa đo hiệu quả) | Chưa rõ — cần gold để đo | Đã xong |
| 6 | Quyết định vùng tư vấn chung | Có thể rất lớn, **cả hai chiều** | Cần gold/probe |

**Việc số 4 làm được ngay và gần như chắc chắn có lợi** — có chứng minh toán học,
không cần gold.

**Việc 2 và 3 là phần "nhảy vọt"** nhưng nên làm *sau* khi có gold, để biết
mình đang đi đúng hướng thay vì lặp lại sai lầm của V1 ở quy mô lớn hơn.

---

## 5. Rủi ro đã nhận diện

| Rủi ro | Cách giảm |
|---|---|
| LLM-first sinh quá nhiều → đảo từ thiếu thành thừa | Có gold để đo; 4 lớp chặn ở §2.4 |
| Gold nội bộ tôi tự gán có thể lệch gold BTC | Chỉ dùng để đo *thay đổi tương đối*, không tin tuyệt đối |
| Cắt vùng tư vấn có thể sai hướng | Không làm cho đến khi có bằng chứng — hiện đang thiếu chứ không thừa |
| Chạy lâu hơn, rủi ro hết giờ kernel | Giữ kiến trúc 2 phase; checkpoint theo file |

---

## 6. Điều cần nói thẳng

V1 đạt 19,07 với WER 75,97%. Phần lớn khoảng cách đến điểm cao **không** nằm ở
tinh chỉnh — nó nằm ở chỗ hai trong năm loại gần như không có nguồn nào bắt
được, và gần 40% bullet bị bỏ trắng.

Sửa được hai chỗ đó là nhảy vọt thật. Nhưng làm mà không có gold thì vẫn là
đánh cược — và lần này đánh cược trên một kiến trúc mới, nên nếu sai sẽ khó
biết sai ở đâu.

Thứ tự đúng là: **gold trước, kiến trúc sau.**
