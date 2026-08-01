# Prompt để test trên Ollama — bản 2, sau khi soi output thật

---

## Nhận xét output vòng 1

| Prompt | Kết quả | Nhận định |
|---|---|---|
| **1. Kịch bản** | chưa test lại sau khi thêm few-shot | chờ |
| **2A. Tên mục** | ❌ **HỎNG NẶNG** | Đến mục ~15 là trôi hẳn: hỏi "tên mục thủ thuật" thì trả về `Triệu chứng`, `Dấu hiệu lâm sàng`; hỏi "tên mục khám lâm sàng" thì trả về `Tím tái da`, `Khó thở`, `Đi tiểu ra máu` — **liệt kê NỘI DUNG thay vì TÊN MỤC**. Lộ tiếng Trung `征象`. Còn tự bịa lượt `user Xin lỗi...` |
| **3. Văn xuôi** | ✅ **ĐÚNG HƯỚNG**, còn 3 lỗi | Bố cục chuẩn rồi: `Câu hỏi từ người dùng:` + `Câu trả lời của bác sĩ:` + 4 mục đánh số, **không còn đối thoại**. Nhưng: lộ `狂犬病`, lộ `dog bite`/`vi rút rabies`, và **copy nguyên dấu ngoặc `[Bệnh này là gì]` của tôi vào bài** |
| **4. Kho ÂM** | ⚠️ Được một nửa | Dùng được: `theo dõi`, `tăng liều`, `đặt ống nội khí quản`. Rác: `tiến hành`, `thay đổi`, `điều chỉnh` (động từ trần, không ai nhầm là thực thể), `lavage` (tiếng Anh), `hăm sóc` (sai chính tả), `đóng băng` (vô nghĩa) |

### 4 lỗi gốc rút ra

1. **Cấm ở cuối là chưa đủ.** Tiếng Trung vẫn lọt 2 lần (`征象`, `狂犬病`). Đặc biệt `狂犬病` là **tên tiếng Trung của bệnh dại** — Qwen "chu đáo" chú thích thêm. Phải cấm **ở đầu và cuối**, và cấm riêng **chú thích trong ngoặc**.
2. **Không được đặt dấu ngoặc vuông trong phần mô tả.** `[Bệnh này là gì]` tôi viết làm chú thích thì nó copy nguyên vào bài.
3. **Việc liệt kê trừu tượng bị trôi sau ~10 mục.** Xin 25 thì 15 mục cuối là rác. Phải có few-shot + hạ số lượng.
4. **Nhiều thứ không cần LLM.** Heading đã quét được **67 tên mục lâm sàng thật** từ chính đề thi — xem mục 2 dưới.

---

# PROMPT 1 — Sinh kịch bản ca bệnh

```
CHỈ TRẢ LỜI BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc, tiếng Anh.

Bạn là bác sĩ Việt Nam. Với chẩn đoán được cho, liệt kê các khái niệm y khoa
thường đi kèm trong bệnh án.

ĐỊNH DẠNG: mỗi dòng một mục, đúng dạng MÃ|nội dung
  TC = triệu chứng người bệnh cảm nhận hoặc bác sĩ quan sát được
  TH = tên thuốc điều trị
  TX = tên xét nghiệm / thăm dò / thủ thuật chẩn đoán

SỐ LƯỢNG: 5 dòng TC, 3 dòng TH, 3 dòng TX. Tổng đúng 11 dòng.

QUY TẮC:
1. Chỉ ghi TÊN, không ghi động từ đi kèm.
   ĐÚNG: TH|amoxicillin        SAI: TH|Tiêm amoxicillin
2. TH phải là tên thuốc CÓ THẬT. Không bịa.
   ĐÚNG: TH|paracetamol, TH|kháng sinh, TH|corticoid
   SAI:  TH|antirôsin, TH|thuốc đặc trị, TH|Antibiotic uống
3. TX phải là TÊN một xét nghiệm cụ thể, KHÔNG phải mô tả cách làm.
   ĐÚNG: TX|công thức máu, TX|siêu âm ổ bụng, TX|nội soi dạ dày
   SAI:  TX|Phương pháp chẩn đoán lâm sàng, TX|Quan sát triệu chứng
4. TC phải là điều người bệnh CẢM THẤY hoặc bác sĩ THẤY trên người bệnh.
   Không ghi đường lây, thói quen, cách phòng bệnh.
   ĐÚNG: TC|sốt cao, TC|đau vùng thượng vị
   SAI:  TC|Nhai hoặc mút đồ vật, TC|Sử dụng miệng lưỡi cắn
5. Mọi mục phải liên quan TRỰC TIẾP tới chẩn đoán đã cho.
6. Mỗi mục 1-5 từ, viết như bác sĩ ghi bệnh án.
7. KHÔNG chú thích tên nước ngoài trong ngoặc.
   SAI: TC|sợ nước (hydrophobia)
8. Viết xong 11 dòng thì DỪNG. Không giải thích, không hỏi lại, không thêm gì.

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

Nhắc lại: chỉ tiếng Việt. Không chữ Hán. Không tiếng Anh. Không chú thích trong ngoặc.
```

---

# PROMPT 2 — ĐÃ BỎ, THAY BẰNG QUÉT DỮ LIỆU THẬT

Prompt 2A hỏng nặng và **không cần sửa** — vì đã quét được heading thật từ chính 100 file đề thi:

```
kb/heading_lamsang.txt   67 tên mục lâm sàng
kb/heading_hoidap.txt     8 tên mục hỏi–đáp
```

Đây là toàn bộ heading xuất hiện ≥2 lần trong đề thi (419 heading duy nhất, lọc còn 75 cái đáng tin). Vài cái đầu:

```
Lý do nhập viện                  Tiền sử bệnh hiện tại
Đánh giá tại bệnh viện           Triệu chứng hiện tại
Đặc điểm triệu chứng             Thời điểm khởi phát triệu chứng
Bệnh sử hiện tại                 Các sự kiện trước khi nhập viện
Diễn biến bệnh                   Các bệnh lý mạn tính
Thuốc trước khi nhập viện        Các thủ thuật đã thực hiện
Cận lâm sàng                     Kết quả xét nghiệm
Kết quả chẩn đoán hình ảnh       Dấu hiệu lâm sàng
Tiền sử phẫu thuật / thủ thuật   Các phát hiện chẩn đoán khác
```

**Tốt hơn LLM ở mọi mặt:** có thật, đúng phân bố đề thi, không lộ tiếng Trung, không trôi đề, và **miễn phí**.

### Đa dạng cấu trúc do CODE sinh

```python
NUMBERING = [None, '1.', '1)', 'I.', 'A.', 'Mục 1:', '1 -', '(1)']
BULLET    = ['-', '•', '*', '+', '‣', '·', None, '1.', 'a)', '–']
INDENT    = ['', '  ', '    ', '      ', '\t']
COLON     = [':', '', ' :', ' -', '...']
BLANKS    = [0, 1, 2]
CASE      = [str, str.upper, str.title]
LAYOUT    = ['bullet', 'inline', 'numbered']
```

`8 × 10 × 5 × 5 × 3 × 3 × 3 ≈ 54.000` khung × 67 tên mục × hoán vị thứ tự. LLM không sinh nổi mức này — nhưng đây đúng là thứ code làm tốt nhất, và cũng là chỗ bạn kêu "chẳng đa dạng gì".

---

# PROMPT 3 — Văn xuôi (sửa 3 lỗi, giữ nguyên bố cục vì đã đúng)

**Sửa:** bỏ hết dấu ngoặc vuông (bị copy nguyên) · cấm ngôn ngữ ở đầu+cuối · cấm chú thích ngoặc.

```
CHỈ VIẾT BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc, tiếng Anh.

Bạn là biên tập viên chuyên mục tư vấn sức khoẻ của một trang web y tế Việt Nam.
Viết MỘT BÀI tư vấn hoàn chỉnh.

BỐ CỤC — giữ nguyên hai dòng tiêu đề, viết nội dung thật vào chỗ mô tả:

Câu hỏi từ người dùng:
Người bệnh tự kể bằng lời thường ngày gồm: hoàn cảnh xảy ra, thấy khó chịu
thế nào, lo lắng gì, rồi đặt câu hỏi. Viết liền mạch 4 đến 6 câu.

Câu trả lời của bác sĩ:
Chào bạn,
Rồi viết đúng 4 mục, mỗi mục bắt đầu bằng số thứ tự và một tiêu đề ngắn do
bạn tự đặt, sau đó là 4 đến 6 câu văn:
Mục 1 nói về bản chất của bệnh này là gì.
Mục 2 nói về nguyên nhân và cách mắc bệnh.
Mục 3 nói về các xét nghiệm cần làm và ý nghĩa của chúng.
Mục 4 nói về cách điều trị, thuốc dùng và dặn dò theo dõi.
Kết thúc bằng dòng: Trân trọng!

CÁC CỤM SAU PHẢI XUẤT HIỆN NGUYÊN VĂN TRONG BÀI, không sửa một chữ,
mỗi cụm dùng đúng một lần. Phải dùng HẾT, không bỏ sót cụm nào:
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

QUY TẮC:
- Tổng bài 500 đến 700 từ. Mục nào cũng đủ 4 đến 6 câu, không viết cụt.
- Mỗi câu mang một thông tin y khoa mới.
- Cấm lặp lại ý đã nói dưới cách diễn đạt khác.
- Cấm câu trấn an rỗng như "đừng lo lắng", "hãy đến khám ngay",
  "bác sĩ sẽ giúp bạn" nếu không kèm thông tin y khoa cụ thể.
- Cấm viết dạng đối thoại qua lại. Người bệnh chỉ hỏi một lần ở đầu bài.
- Cấm chú thích tên bệnh bằng tiếng nước ngoài trong ngoặc.
  Viết "Bệnh dại", KHÔNG viết "Bệnh dại (rabies)" hay "Bệnh dại (狂犬病)".
- Cấm dùng từ tiếng Anh. Viết "chó cắn", không viết "dog bite".
  Viết "vi rút dại", không viết "vi rút rabies".
- Không dùng gạch đầu dòng trong phần trả lời, viết thành đoạn văn.
- Không chép lại các dòng hướng dẫn ở trên vào bài viết.

Nhắc lại: chỉ tiếng Việt. Không chữ Hán. Không tiếng Anh. Không chú thích trong ngoặc.
```

**Kiểm sau khi chạy:**

| Tiêu chí | Đạt khi |
|---|---|
| Độ dài | 1.500–4.000 ký tự |
| Bố cục | Đủ 2 dòng tiêu đề + 4 mục đánh số + `Trân trọng!` |
| Không lộ hướng dẫn | Không thấy chữ `Mục 1 nói về...` trong bài |
| Đủ cụm | **15/15** cụm xuất hiện nguyên văn *(vòng 1 chỉ đạt 10/15)* |
| Ngôn ngữ | Không có chữ Hán, không có từ tiếng Anh |

Nếu vẫn thiếu cụm: **giảm còn 12 cụm** thay vì ép. Thiếu cụm thì code loại mẫu và sinh lại, không phải lỗi chết người.

---

# PROMPT 4 — Kho ÂM (thêm few-shot, hạ số lượng)

**Sửa:** vòng 1 ra động từ trần (`tiến hành`, `thay đổi`) — không ai nhầm mấy cái đó là thực thể nên vô dụng làm ca âm. Cần **cụm danh từ nhìn giống thực thể**.

```
CHỈ TRẢ LỜI BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc, tiếng Anh.

Trong bệnh án tiếng Việt có nhiều cụm từ TRÔNG GIỐNG tên bệnh, tên thuốc hoặc
tên xét nghiệm, nhưng thực chất KHÔNG PHẢI. Tôi cần thu thập các cụm đó.

Hãy liệt kê 15 cụm thuộc nhóm: CÁC VẬT DỤNG VÀ HOÁ CHẤT KHÔNG DÙNG ĐỂ CHỮA BỆNH

VÍ DỤ đúng cho nhóm này:
thuốc lá
thuốc trừ sâu
băng phiến
long não
thuốc nhuộm tóc

YÊU CẦU:
- Mỗi dòng một cụm, không đánh số, không giải thích.
- Phải là CỤM DANH TỪ, 1 đến 4 từ. Không phải động từ.
  ĐÚNG: băng phiến, thuốc trừ sâu
  SAI:  tiến hành, thay đổi, điều chỉnh
- Phải là thứ dễ bị nhầm là thuốc hoặc bệnh, nhưng thật ra không phải.
- Viết đúng chính tả tiếng Việt có dấu.
- Liệt kê xong 15 dòng thì DỪNG, không viết thêm gì.

Nhắc lại: chỉ tiếng Việt. Không chữ Hán. Không tiếng Anh.
```

Chạy lại prompt trên, thay phần in hoa **và cả 5 dòng ví dụ** theo bảng:

| # | Thay chỗ in hoa | Thay 5 dòng ví dụ |
|---|---|---|
| 1 | `CÁC VẬT DỤNG VÀ HOÁ CHẤT KHÔNG DÙNG ĐỂ CHỮA BỆNH` | thuốc lá / thuốc trừ sâu / băng phiến / long não / thuốc nhuộm tóc |
| 2 | `TÊN CÁC KHOA PHÒNG TRONG BỆNH VIỆN` | khoa nội tổng hợp / phòng khám da liễu / khoa cấp cứu / phòng mổ / khoa truyền nhiễm |
| 3 | `CÁC CỤM MÔ TẢ CƠ THỂ HOẠT ĐỘNG BÌNH THƯỜNG` | ăn ngủ bình thường / đại tiện bình thường / kinh nguyệt đều / da niêm hồng / tinh thần tỉnh táo |
| 4 | `CÁC THÓI QUEN VÀ YẾU TỐ NGUY CƠ` | hút thuốc lá / uống rượu bia / ăn mặn / ít vận động / thức khuya |
| 5 | `CÁC CỤM CHỈ THỜI GIAN VÀ THÔNG TIN HÀNH CHÍNH` | cách đây ba ngày / giường số năm / khoa phòng điều trị / số hồ sơ / ngày ra viện |
| 6 | `CÁC THỦ THUẬT ĐIỀU TRỊ, KHÔNG PHẢI ĐỂ CHẨN ĐOÁN` | truyền dịch / thở oxy / ghép thận / phẫu thuật cắt ruột thừa / xạ trị |

**Nhóm 1 quan trọng nhất** — `băng phiến`, `chăn màn` đã bị model gán nhầm THUỐC ở bài nộp thật.

⚠️ Kho ÂM **phải loại khỏi kho DƯƠNG** trước khi chạy quét từ điển ngược, nếu không chính bước chống-bỏ-sót sẽ tự gán nhãn cho các ca âm này.

---

# Xử lý lỗi Ollama tự bịa lượt hội thoại

Vòng 1 có đoạn `user Xin lỗi, có vẻ như có sự hiểu lầm...` — model tự sinh lượt của người dùng rồi tự trả lời. Đây là lỗi **stop token** của Ollama, không phải lỗi nội dung.

Cách xử lý:
- Đã thêm câu `"Viết xong ... thì DỪNG"` vào cuối mỗi prompt
- Khi chạy bằng code, đặt `stop=["user", "User", "\nuser", "assistant"]`
- Nếu vẫn bị: cắt output tại dòng đầu tiên chứa `user` hoặc `assistant`

---

# Thứ tự test vòng 2

| # | Prompt | Xem gì |
|---|---|---|
| 1 | Prompt 1 — `"Bệnh dại"` | Đủ 11 dòng · không bịa thuốc · không từ meta · không tiếng Anh |
| 2 | Prompt 1 — `"Trứng cá"` | Còn lạc đề như `Đau vùng chậu`, `Chụp X-quang ổ bụng` không |
| 3 | Prompt 3 | Có còn lộ `[Bệnh này là gì]` không · đủ 15/15 cụm · không chữ Hán |
| 4 | Prompt 4 nhóm 1 | Ra danh từ (`băng phiến`) hay động từ trần (`tiến hành`) |
| 5 | — | **Bỏ qua Prompt 2**, đã có `kb/heading_lamsang.txt` |
