# Prompt để test trên Ollama — bản viết lại sau khi soi lỗi thật

> Mọi prompt đều kết thúc bằng dòng cấm tiếng Trung/Anh (theo yêu cầu, vì Qwen từng phun tiếng Trung).

---

## Chẩn đoán sai của 3 prompt cũ

| Prompt | Triệu chứng hỏng | Nguyên nhân GỐC |
|---|---|---|
| **1. Sinh kịch bản** | `TH\|Tiêm antirôsin` (bịa thuốc), `TH\|Antibiotic uống` (tiếng Anh), `TX\|Phương pháp chẩn đoán lâm sàng` (không phải tên XN), `TC\|Đau vùng chậu` cho bệnh trứng cá (sai liên hệ) | **Không có few-shot** → model không biết độ hạt mong muốn. Và **bắt nó BỊA tên xét nghiệm** trong khi ta đã có sẵn 598 tên thật trong `kb/xetnghiem_ten.txt` |
| **2. Template** | Chỉ đảo thứ tự + xuống dòng, không thụt lề, không đánh số mục | **Mỗi lần gọi LLM là STATELESS** — câu "khác với khung trước" hoàn toàn vô nghĩa. Và LLM **mode-collapse khi bị bảo "hãy đa dạng"**. Đa dạng tổ hợp là việc của CODE, không phải của LLM |
| **3. Văn xuôi** | Ra hội thoại qua lại, quá ngắn; ép dài thì lặp lời sáo rỗng | Tôi bảo "viết hỏi–đáp giữa bệnh nhân và bác sĩ" → nó viết đối thoại. **Đo lại: 0/100 file đề thi là đối thoại.** Format thật là *bài viết* Q&A một chiều. Thêm nữa: 4 thực thể thì không có gì để viết 1500 ký tự, nên nó độn lời khuyên rỗng |

**Bài học chung:** không ép LLM làm việc nó dở (ngẫu nhiên hoá, tự kiềm chế bịa). Giao nó việc nó giỏi (viết văn, liệt kê từ đồng nghĩa), phần còn lại để code.

---

# PROMPT 1 — Sinh kịch bản ca bệnh

**Thay đổi chính:** thêm few-shot đầy đủ · cấm động từ dẫn · cấm từ meta · nêu rõ TX phải là *tên* xét nghiệm chứ không phải *phương pháp*.

```
Bạn là bác sĩ Việt Nam. Với chẩn đoán được cho, liệt kê các khái niệm y khoa
thường đi kèm trong bệnh án.

ĐỊNH DẠNG: mỗi dòng một mục, đúng dạng MÃ|nội dung
  TC = triệu chứng người bệnh cảm nhận hoặc bác sĩ quan sát được
  TH = tên thuốc điều trị
  TX = tên xét nghiệm / thăm dò / thủ thuật chẩn đoán

SỐ LƯỢNG: 5 dòng TC, 3 dòng TH, 3 dòng TX.

QUY TẮC BẮT BUỘC:
1. Chỉ ghi TÊN, không ghi động từ đi kèm.
   ĐÚNG: TH|amoxicillin        SAI: TH|Tiêm amoxicillin, TH|Uống amoxicillin
2. TH phải là tên thuốc CÓ THẬT (hoạt chất hoặc nhóm thuốc). Không được bịa.
   ĐÚNG: TH|paracetamol, TH|kháng sinh, TH|corticoid
   SAI:  TH|antirôsin, TH|thuốc đặc trị
3. TX phải là TÊN một xét nghiệm cụ thể, KHÔNG phải mô tả cách làm.
   ĐÚNG: TX|công thức máu, TX|siêu âm ổ bụng, TX|nội soi dạ dày
   SAI:  TX|Phương pháp chẩn đoán lâm sàng, TX|Quan sát triệu chứng, TX|Chẩn đoán lâm sàng
4. TC phải là điều người bệnh CẢM THẤY hoặc bác sĩ THẤY được trên người bệnh.
   KHÔNG ghi đường lây, thói quen, hay cách phòng bệnh.
   ĐÚNG: TC|sốt cao, TC|đau bụng vùng thượng vị
   SAI:  TC|Nhai hoặc mút đồ vật, TC|Sử dụng miệng lưỡi cắn
5. Mọi mục phải liên quan TRỰC TIẾP tới chẩn đoán đã cho.
6. Viết ngắn gọn 1-5 từ, như cách bác sĩ ghi bệnh án.
7. Không giải thích, không đánh số, không thêm chữ nào ngoài các dòng MÃ|nội dung.

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

BÂY GIỜ LÀM VỚI CHẨN ĐOÁN: "Bệnh dại"

Chỉ viết bằng tiếng Việt. Tuyệt đối không dùng tiếng Trung, tiếng Anh hay bất kỳ ngôn ngữ nào khác.
```

**Kiểm khi chạy xong:** đúng 11 dòng · không có động từ đầu dòng · không có `Phương pháp/Quan sát/Chẩn đoán lâm sàng` · không có chữ tiếng Anh · mọi mục liên quan bệnh dại.

*(Code sẽ đối chiếu tiếp với RxNorm / `kb/xetnghiem_ten.txt`; mục nào không khớp KB thì loại — nên prompt không cần hoàn hảo, chỉ cần bớt rác.)*

---

# PROMPT 2 — Đa dạng heading (ĐỔI HẲN CÁCH LÀM)

**Vì sao đổi:** yêu cầu LLM "sinh khung đa dạng" là sai từ gốc. Mỗi lần gọi là một phiên độc lập, nó không nhớ lần trước, và khi bị bảo "hãy đa dạng" thì nó mode-collapse ra vài mẫu quen.

**Cách đúng:** LLM chỉ lo **TỪ VỰNG** (tên mục — việc nó giỏi). **CODE lo CẤU TRÚC** (đánh số, bullet, thụt lề, thứ tự — việc code làm hoàn hảo).

### 2A — Prompt xin từ vựng (chạy 1 lần cho mỗi nhóm mục)

```
Bạn là bác sĩ Việt Nam. Trong bệnh án và phiếu khám, một mục có thể được đặt
tên theo nhiều cách khác nhau tuỳ bệnh viện và tuỳ bác sĩ.

Hãy liệt kê 25 cách đặt tên khác nhau cho mục ghi: CÁC TRIỆU CHỨNG NGƯỜI BỆNH ĐANG CÓ

Yêu cầu:
- Mỗi dòng một cách gọi, không đánh số, không giải thích.
- Chỉ ghi TÊN MỤC, không kèm dấu hai chấm, không kèm nội dung.
- Đa dạng độ dài: có cách gọi ngắn 1-2 từ, có cách gọi dài 4-6 từ.
- Dùng đúng từ ngữ bác sĩ Việt Nam hay dùng trong bệnh án thật.

Chỉ viết bằng tiếng Việt. Tuyệt đối không dùng tiếng Trung, tiếng Anh hay bất kỳ ngôn ngữ nào khác.
```

Chạy lại prompt trên, thay phần in hoa bằng từng nhóm:

| Nhóm | Thay vào chỗ in hoa |
|---|---|
| Triệu chứng | `CÁC TRIỆU CHỨNG NGƯỜI BỆNH ĐANG CÓ` |
| Lý do khám | `LÝ DO NGƯỜI BỆNH ĐẾN KHÁM HOẶC NHẬP VIỆN` |
| Diễn biến | `DIỄN BIẾN CỦA BỆNH THEO THỜI GIAN` |
| Bệnh nền | `CÁC BỆNH MẠN TÍNH ĐÃ CÓ TỪ TRƯỚC` |
| Kết quả XN | `KẾT QUẢ CÁC XÉT NGHIỆM ĐÃ LÀM` |
| Thủ thuật | `CÁC THỦ THUẬT VÀ THĂM DÒ ĐÃ THỰC HIỆN` |
| Thuốc | `CÁC THUỐC NGƯỜI BỆNH ĐANG DÙNG` |
| Khám | `KẾT QUẢ THĂM KHÁM LÂM SÀNG` |
| Hình ảnh | `KẾT QUẢ CHẨN ĐOÁN HÌNH ẢNH` |

→ 9 nhóm × 25 = **~225 tên mục**, gấp nhiều lần danh sách cứng cũ.

### 2B — Cấu trúc do CODE sinh (không dùng LLM)

Đây là chỗ tạo ra đa dạng thật. Code random độc lập từng tham số:

```python
NUMBERING = [None, '1.', '1)', 'I.', 'A.', 'Mục 1:', '1 -', '(1)']
BULLET    = ['-', '•', '*', '+', '‣', '·', None, '1.', 'a)', '–']
INDENT    = ['', '  ', '    ', '      ', '\t']
COLON     = [':', '', ' :', ' -', '...']
BLANKS    = [0, 1, 2]
CASE      = [str, str.upper, str.title]
LAYOUT    = ['bullet', 'inline', 'numbered']   # inline: "Triệu chứng: sốt, ho, đau đầu"
```

Ví dụ vài khung code sinh ra từ CÙNG bộ tham số ngẫu nhiên:

```
1. TRIỆU CHỨNG HIỆN TẠI
      - {SLOT}
      - {SLOT}

2. THUỐC ĐANG DÙNG
      - {SLOT}
```
```
I.  Lý do vào viện ...
	‣ {SLOT}
	‣ {SLOT}
II.  Các bệnh mạn tính ...
	‣ {SLOT}
```
```
Dấu hiệu lâm sàng: {SLOT}, {SLOT}, {SLOT}
Kết quả xét nghiệm đã làm: {SLOT}, {SLOT}
```
```
Mục 1: Diễn biến bệnh
  a) {SLOT}
  b) {SLOT}
Mục 2: Thăm dò đã thực hiện
  a) {SLOT}
```

Số tổ hợp: `8 × 10 × 5 × 5 × 3 × 3 × 3 ≈ 54.000` khung, chưa tính hoán vị thứ tự mục và 225 tên mục. **Không LLM nào sinh nổi mức đa dạng này** — nhưng code thì làm trong 3 dòng.

---

# PROMPT 3 — Văn xuôi (VIẾT LẠI HOÀN TOÀN)

**Ba lỗi đã sửa:**
1. ~~"hỏi–đáp giữa bệnh nhân và bác sĩ"~~ → **0/100 file đề thi là đối thoại**. Format thật: *một câu hỏi* + *một bài trả lời dài có mục*.
2. Ép độ dài bằng câu chữ vô dụng → **độ dài phải đến từ NỘI DUNG**: đưa nhiều thực thể hơn (12–15 thay vì 4) và **cho sẵn dàn ý các mục**.
3. Chống lặp lời sáo rỗng bằng cấm cụ thể.

```
Bạn là biên tập viên chuyên mục tư vấn sức khoẻ của một trang web y tế Việt Nam.
Hãy viết MỘT BÀI tư vấn hoàn chỉnh theo đúng bố cục dưới đây.

BỐ CỤC BẮT BUỘC (giữ nguyên 2 dòng tiêu đề này):

Câu hỏi từ người dùng:
[Người bệnh tự kể bằng lời thường ngày: hoàn cảnh, thấy khó chịu thế nào, lo lắng
 gì, rồi đặt câu hỏi. Viết liền mạch 4-6 câu. KHÔNG xuống dòng nhiều lần.]

Câu trả lời của bác sĩ:
Chào bạn,
[Sau đó viết bài trả lời gồm ĐÚNG 4 mục, mỗi mục có tiêu đề đánh số riêng:]
1. [Bệnh này là gì] — giải thích bản chất bệnh, 4-6 câu.
2. [Vì sao mắc / lây thế nào] — nguyên nhân, yếu tố nguy cơ, 4-6 câu.
3. [Cần làm xét nghiệm gì] — nêu các thăm dò cần thiết và ý nghĩa, 4-6 câu.
4. [Điều trị và theo dõi] — hướng xử trí, thuốc, dặn dò, 4-6 câu.
Trân trọng!

CÁC CỤM SAU PHẢI XUẤT HIỆN NGUYÊN VĂN TRONG BÀI, không sửa một chữ,
mỗi cụm dùng ĐÚNG MỘT LẦN:
- {entity_1}
- {entity_2}
- {entity_3}
...
- {entity_15}

QUY TẮC:
- Tổng bài 500-700 từ. Mục nào cũng phải đủ 4-6 câu, không được viết cụt.
- Mỗi câu phải mang MỘT THÔNG TIN Y KHOA MỚI.
- CẤM lặp lại ý đã nói ở câu trước dưới cách diễn đạt khác.
- CẤM các câu trấn an rỗng kiểu "đừng lo lắng", "hãy đến khám ngay",
  "bác sĩ sẽ giúp bạn" nếu không kèm thông tin y khoa cụ thể.
- CẤM viết dưới dạng đối thoại qua lại. Người bệnh chỉ hỏi MỘT lần ở đầu bài.
- Không dùng gạch đầu dòng trong phần trả lời, viết thành đoạn văn.

Chỉ viết bằng tiếng Việt. Tuyệt đối không dùng tiếng Trung, tiếng Anh hay bất kỳ ngôn ngữ nào khác.
```

### Ví dụ điền sẵn để test ngay trên Ollama

Thay khối `{entity_*}` bằng danh sách này (bệnh dại, 15 cụm):

```
- Bệnh dại
- sợ nước
- co thắt hầu họng
- sốt
- đau đầu
- mệt mỏi
- tăng tiết nước bọt
- kích thích
- vắc xin phòng dại
- huyết thanh kháng dại
- kháng sinh
- xét nghiệm kháng thể kháng dại
- công thức máu
- chụp cộng hưởng từ sọ não
- viêm não
```

**Kiểm khi chạy xong:**

| Tiêu chí | Đạt khi |
|---|---|
| Độ dài | 1.500–4.000 ký tự |
| Bố cục | Có đủ 2 dòng tiêu đề + 4 mục đánh số |
| Không đối thoại | Chỉ 1 lượt hỏi ở đầu |
| Đủ cụm | Cả 15 cụm xuất hiện **nguyên văn**, mỗi cụm đúng 1 lần |
| Không lặp | Không có câu trấn an rỗng lặp đi lặp lại |
| Ngôn ngữ | Không lẫn tiếng Trung/Anh |

Nếu vẫn ngắn: **tăng số cụm lên 18–20** trước khi nghĩ tới việc sửa câu chữ về độ dài — vì độ dài đến từ lượng nội dung phải nói, không đến từ việc ra lệnh viết dài.

---

# PROMPT 4 — Sinh kho ÂM (mới, chưa có ở bản trước)

Dùng để lấy các cụm **giống thực thể nhưng KHÔNG phải**, chèn vào text làm đối chứng âm.

```
Bạn là bác sĩ Việt Nam. Trong bệnh án có nhiều cụm từ TRÔNG GIỐNG tên bệnh,
tên thuốc hay tên xét nghiệm, nhưng thực chất KHÔNG PHẢI.

Hãy liệt kê 20 cụm từ thuộc nhóm: CÁC HÀNH ĐỘNG Y TẾ CỦA NHÂN VIÊN Y TẾ
(ví dụ: khám lâm sàng, theo dõi sát, chuyển tuyến trên)

Yêu cầu:
- Mỗi dòng một cụm, không đánh số, không giải thích.
- Đây phải là HÀNH ĐỘNG, không phải tên bệnh / tên thuốc / tên xét nghiệm.
- Ngắn 2-5 từ, đúng cách nói trong bệnh án Việt Nam.

Chỉ viết bằng tiếng Việt. Tuyệt đối không dùng tiếng Trung, tiếng Anh hay bất kỳ ngôn ngữ nào khác.
```

Chạy lại, thay phần in hoa bằng từng nhóm:

| # | Thay vào chỗ in hoa | Ví dụ mồi |
|---|---|---|
| 1 | `CÁC HÀNH ĐỘNG Y TẾ CỦA NHÂN VIÊN Y TẾ` | khám lâm sàng, chuyển tuyến |
| 2 | `TÊN CÁC KHOA PHÒNG TRONG BỆNH VIỆN` | khoa nội tổng hợp, phòng khám da liễu |
| 3 | `CÁC VẬT DỤNG VÀ HOÁ CHẤT KHÔNG PHẢI THUỐC CHỮA BỆNH` | băng phiến, long não, thuốc trừ sâu |
| 4 | `CÁC CỤM MÔ TẢ CƠ THỂ HOẠT ĐỘNG BÌNH THƯỜNG` | ăn ngủ bình thường, đại tiện bình thường |
| 5 | `CÁC THÓI QUEN VÀ YẾU TỐ NGUY CƠ` | hút thuốc lá, uống rượu bia, ăn mặn |
| 6 | `CÁC CỤM CHỈ THỜI GIAN VÀ THÔNG TIN HÀNH CHÍNH` | cách đây 3 ngày, giường số 5 |
| 7 | `CÁC THỦ THUẬT ĐIỀU TRỊ (không phải để chẩn đoán)` | truyền dịch, thở oxy, ghép thận |

⚠️ Nhóm 3 quan trọng nhất — `băng phiến`, `chăn màn` **đã bị model gán nhầm THUỐC ở bài nộp thật**.

⚠️ Kho ÂM **phải được loại khỏi kho DƯƠNG** trước khi chạy bước quét từ điển ngược, nếu không chính bước chống-bỏ-sót sẽ tự gán nhãn cho các ca âm này.

---

# Thứ tự test đề nghị

| # | Prompt | Xem gì |
|---|---|---|
| 1 | Prompt 1 với `"Bệnh dại"` | Còn bịa thuốc / còn từ meta / còn tiếng Anh không |
| 2 | Prompt 1 với `"Trứng cá"` | Các mục có còn lạc đề như `Đau vùng chậu` không |
| 3 | Prompt 3 (15 cụm bệnh dại) | Có ra **bài viết** thay vì **đối thoại** không · độ dài |
| 4 | Prompt 2A nhóm "Triệu chứng" | Có ra đủ 25 tên mục khác nhau không |
| 5 | Prompt 4 nhóm 3 (vật dụng) | Có ra `băng phiến`, `long não` không |

Gửi lại output, tôi chỉnh tiếp rồi mới viết code.
