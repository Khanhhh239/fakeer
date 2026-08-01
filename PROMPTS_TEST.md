# Prompt để test trên Ollama — bản 3

---

## Nhận xét output vòng 2

| Prompt | Kết quả | Nhận định |
|---|---|---|
| **3. Văn xuôi** | ⚠️ Bố cục đúng, còn 2 lỗi | Vẫn lộ ngoặc vuông — **nhưng khác lần trước**: `2. [Nguyên nhân và cách mắc bệnh] — nói về nguyên nhân:` chính là **câu mô tả trong prompt mới của tôi** bị biến thành tiêu đề. Bỏ ngoặc chưa đủ. Và chỉ dùng **10/15** cụm |
| **4. Kho ÂM** | ❌ Trôi hẳn | Chép nguyên 5 ví dụ của tôi rồi trôi sang `điện thoại di động`, `tắc kè hoa`, `gỗ sồi`, `vải organza`. Output không xuống dòng |

### Lỗi gốc vòng 2

**1. Model biến câu MÔ TẢ của tôi thành tiêu đề.**
Tôi viết `Mục 2 nói về nguyên nhân và cách mắc bệnh` để mô tả → nó xuất ra
`2. [Nguyên nhân và cách mắc bệnh] — nói về nguyên nhân:`.
→ Không đủ nếu chỉ bỏ ngoặc. Phải **chỉ thẳng mẫu ĐÚNG và mẫu SAI**.

**2. Nhóm ÂM tôi định nghĩa quá rộng.**
`"vật dụng không dùng để chữa bệnh"` — xét về logic thì `tắc kè hoa`, `điện thoại di động`, `gỗ sồi` đều thoả. Model không sai, **định nghĩa của tôi sai**.
→ Phải neo vào **văn bản y tế thật**, không hỏi trừu tượng.

**3. Thiếu cụm KHÔNG phải lỗi model.**
5 cụm thiếu — `sợ nước`, `co thắt hầu họng`, `tăng tiết nước bọt`, `kích thích`, `viêm não` — đều là triệu chứng dại **giai đoạn muộn**. Kịch bản là "vừa bị cắn hôm qua, đang lo lắng", người bệnh chưa phát bệnh. Model **viết đúng y khoa** khi không nhét chúng vào.
→ Lỗi ở chỗ tôi bó 15 cụm không nhất quán với kịch bản. Xem chính sách xử lý ở mục "Thiếu cụm" bên dưới.

---

# PROMPT 1 — Sinh kịch bản ca bệnh *(giữ nguyên bản 2, chưa test lại)*

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
   ĐÚNG: TC|sốt cao, TC|đau vùng thượng vị
   SAI:  TC|Nhai hoặc mút đồ vật, TC|Sử dụng miệng lưỡi cắn
5. Mọi mục phải liên quan TRỰC TIẾP tới chẩn đoán đã cho.
6. Mỗi mục 1-5 từ, viết như bác sĩ ghi bệnh án.
7. KHÔNG chú thích tên nước ngoài trong ngoặc. SAI: TC|sợ nước (hydrophobia)
8. Viết xong 11 dòng thì DỪNG. Không giải thích, không hỏi lại.

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

# PROMPT 2 — ĐÃ BỎ, dùng `kb/heading_lamsang.txt` (67 tên mục quét từ đề thi thật)

Cấu trúc do code sinh:
```python
NUMBERING = [None, '1.', '1)', 'I.', 'A.', 'Mục 1:', '1 -', '(1)']
BULLET    = ['-', '•', '*', '+', '‣', '·', None, '1.', 'a)', '–']
INDENT    = ['', '  ', '    ', '      ', '\t']
COLON     = [':', '', ' :', ' -', '...']
BLANKS    = [0, 1, 2];  CASE = [str, str.upper, str.title]
LAYOUT    = ['bullet', 'inline', 'numbered']
```
≈54.000 khung × 67 tên mục × hoán vị thứ tự.

---

# PROMPT 3 — Văn xuôi (sửa lỗi tiêu đề)

**Sửa chính:** thay vì mô tả từng mục (bị biến thành tiêu đề), **cho sẵn 4 tiêu đề mẫu** và **chỉ rõ mẫu SAI**.

```
CHỈ VIẾT BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc, tiếng Anh.

Bạn là biên tập viên chuyên mục tư vấn sức khoẻ của một trang web y tế Việt Nam.
Viết MỘT BÀI tư vấn hoàn chỉnh.

Bài gồm đúng các phần sau, viết liền mạch:

Câu hỏi từ người dùng:
(4 đến 6 câu, người bệnh tự kể: hoàn cảnh, khó chịu ra sao, lo lắng gì, rồi hỏi)

Câu trả lời của bác sĩ:
Chào bạn,
1. Bệnh dại là bệnh gì
(4 đến 6 câu)
2. Vì sao mắc bệnh dại
(4 đến 6 câu)
3. Những xét nghiệm cần làm
(4 đến 6 câu)
4. Điều trị và theo dõi
(4 đến 6 câu)
Trân trọng!

CÁCH VIẾT TIÊU ĐỀ MỤC — rất quan trọng:
ĐÚNG:  1. Bệnh dại là bệnh gì
ĐÚNG:  2. Vì sao mắc bệnh dại
SAI:   1. [Bệnh này là gì] — giải thích bản chất bệnh:
SAI:   2. [Nguyên nhân và cách mắc bệnh] — nói về nguyên nhân:
Tiêu đề là một câu ngắn bình thường. Không dùng dấu ngoặc vuông.
Không dùng dấu gạch ngang rồi mô tả lại. Không chép chữ trong hướng dẫn này.

CÁC CỤM SAU PHẢI XUẤT HIỆN NGUYÊN VĂN trong bài, không sửa một chữ:
- Bệnh dại
- sợ nước
- co thắt hầu họng
- sốt
- đau đầu
- mệt mỏi
- tăng tiết nước bọt
- vắc xin phòng dại
- huyết thanh kháng dại
- xét nghiệm kháng thể kháng dại
- công thức máu
- chụp cộng hưởng từ sọ não
- viêm não

QUY TẮC:
- Tổng bài 500 đến 700 từ. Mục nào cũng đủ 4 đến 6 câu.
- Mỗi câu mang một thông tin y khoa mới. Cấm lặp ý đã nói.
- Cấm câu trấn an rỗng như "đừng lo lắng", "hãy đến khám ngay" nếu không
  kèm thông tin y khoa cụ thể.
- Cấm viết dạng đối thoại qua lại. Người bệnh chỉ hỏi một lần ở đầu bài.
- Cấm chú thích tên bệnh bằng tiếng nước ngoài trong ngoặc.
  Viết "Bệnh dại", KHÔNG viết "Bệnh dại (rabies)" hay "Bệnh dại (狂犬病)".
- Cấm MỌI từ tiếng Anh, kể cả tên khoa học của bệnh hay triệu chứng.
  Viết "chó cắn" không viết "dog bite". Viết "vi rút dại" không viết "vi rút rabies".
  Viết "sợ nước" không viết "sợ nước (hydrophobia)".
  Nếu định viết tên tiếng Anh của bất kỳ bệnh hay triệu chứng nào, hãy BỎ nó đi.
- Không dùng gạch đầu dòng trong phần trả lời, viết thành đoạn văn.

Nhắc lại: chỉ tiếng Việt. Không chữ Hán. Không tiếng Anh. Không ngoặc vuông.
```

> **Đã bỏ 2 cụm** `kích thích` và `kháng sinh` khỏi danh sách (còn 13). Lý do ở mục dưới.

---

## Thiếu cụm thì sao — chính sách xử lý

Đây là câu hỏi quan trọng nhất của vòng này. Trả lời: **thiếu cụm là chuyện BÌNH THƯỜNG, không cần ép đủ.**

### Vì sao thiếu

5 cụm thiếu ở vòng 2 (`sợ nước`, `co thắt hầu họng`, `tăng tiết nước bọt`, `kích thích`, `viêm não`) đều là biểu hiện dại **giai đoạn muộn**. Kịch bản là *"vừa bị cắn hôm qua"* — người bệnh chưa phát bệnh. Model **viết đúng y khoa** khi không nhét chúng vào. Ép nó dùng sẽ tạo ra văn bản **sai về mặt y học** — tệ hơn nhiều so với việc thiếu vài nhãn.

### Cách xử lý đúng — 3 tầng

**Tầng 1 — Chấp nhận một phần (quan trọng nhất).**
Không cần đủ 15. Chỉ cần **gán nhãn đúng những cụm ĐÃ xuất hiện**. 10 nhãn đúng vẫn là 10 mẫu huấn luyện tốt.

```python
import re
def anchor_all(text, required):
    """PHƯƠNG ÁN B: gán nhãn MỌI lần xuất hiện, không đòi "đúng 1 lần".
    Khớp theo RANH GIỚI TỪ — `sốt` là chuỗi con của `sốt nhẹ`, `hạ sốt`."""
    ents, seen = [], 0
    for surface, etype in required:
        pat = r'(?<![\wÀ-ỹ])' + re.escape(surface) + r'(?![\wÀ-ỹ])'
        hits = list(re.finditer(pat, text, re.IGNORECASE))
        if hits: seen += 1
        for m in hits:
            ents.append({'text': text[m.start():m.end()], 'type': etype,
                         'position': [m.start(), m.end()]})
    if seen / len(required) < 0.6:      # quá ít cụm -> mẫu loãng, sinh lại
        return None
    return resolve_overlap(ents)        # `đau đầu` nằm trong `đau đầu dữ dội` -> giữ cụm dài
```

Ngưỡng 60%: vòng 2 đạt 10/15 = 67% → **nhận, không phải sinh lại**.

**Tầng 2 — Bó thực thể phải nhất quán với kịch bản.**
Lỗi gốc là tôi trộn triệu chứng sớm và muộn vào cùng một ca. Sửa: chọn **một giai đoạn**, rồi lấy thực thể hợp giai đoạn đó.

| Kịch bản | Thực thể nên đưa |
|---|---|
| Vừa bị cắn, dự phòng | vết cắn, vắc xin phòng dại, huyết thanh kháng dại, xét nghiệm kháng thể kháng dại |
| Đã phát bệnh | sợ nước, co thắt hầu họng, tăng tiết nước bọt, viêm não, chụp cộng hưởng từ sọ não |

Hai kịch bản → **hai tài liệu riêng**, không nhồi chung.

**Tầng 3 — Quét từ điển ngược vẫn bắt được phần dôi ra.**
Model có thể tự thêm cụm ngoài danh sách (ví dụ nó viết `vết cắn`, `nhiễm trùng` mà ta không yêu cầu). Bước quét từ điển ngược gán nhãn luôn những cụm đó → **bù lại phần thiếu**.

### Cụm nên bỏ khỏi danh sách yêu cầu

| Cụm | Vì sao bỏ |
|---|---|
| `kích thích` | Quá đa nghĩa. Model dùng theo nghĩa thường (`chất kích thích`, `kích thích thần kinh`) → dễ trùng nhiều lần, không neo được |
| `kháng sinh` | Không dùng điều trị bệnh dại. Ép vào tạo nội dung sai y khoa |
| `sốt` | ⚠️ Giữ nhưng cẩn thận — là **chuỗi con** của `sốt nhẹ`, `hạ sốt`, `sốt cao`. Code phải khớp theo **ranh giới từ**, không dùng `in` thuần |

---

# PROMPT 4 — Kho ÂM: **BỎ LLM, lấy từ LỖI THẬT của model**

## Vì sao bỏ cả ba cách trước

| Cách đã thử | Kết quả | Vì sao hỏng |
|---|---|---|
| Hỏi LLM theo nhóm trừu tượng | `tắc kè hoa`, `điện thoại di động`, `gỗ sồi` | Định nghĩa nhóm quá rộng — model không sai, **đề bài của tôi sai** |
| Đưa đoạn văn thật cho LLM chỉ ra | chỉ ra 2 mục | Chậm, sản lượng thấp, **không mở rộng được** — đúng như bạn nói |
| Trừ KB khỏi n-gram văn bản thật | `bác`, `hỏi`, `nên`, `đây` | Ra toàn hư từ. Hard negative là tính chất **ngữ nghĩa**, không phải tần suất |

## Cách đúng: khai thác từ chính bài nộp

Negative có giá trị nhất là cái **model ĐÃ gán sai thật**, không phải cái ta tưởng tượng ra. Ta có sẵn 2.316 span từ bài nộp V2 — đó là mỏ negative thật, và nó **tự mở rộng** theo mỗi lần chạy.

```python
# Span "đáng ngờ" = trượt KB VÀ không khớp khuôn hợp lệ nào
OK_PATTERN = [
    r'^(thuốc|kháng sinh|viên|dịch truyền)',                       # nhóm thuốc chung
    r'^(chụp|siêu âm|nội soi|xét nghiệm|cấy|sinh thiết|chọc dò|đo|test)',
]
suspicious = [s for s in spans
              if not in_kb(s) and not any(re.match(p, s.text.lower()) for p in OK_PATTERN)]
```

Chạy trên bài nộp V2 ra **243 span trượt KB**, lọc tiếp bằng khuôn còn khoảng **40–60 ca đáng ngờ thật**. Duyệt tay 15 phút là xong, và **đó chính là những ca model đang sai**:

```
thuốc                  ← từ trần, không phải tên thuốc
điều trị triệu chứng   ← không phải tên thuốc
thuốc điều trị         ← không phải tên thuốc
truyền dịch tĩnh mạch  ← điều trị, không phải xét nghiệm
truyền tĩnh mạch       ← nt
dịch tiết              ← không phải xét nghiệm
```

Cộng với các ca đã biết từ vòng soi trước: `chăn màn`, `băng phiến`, `long não`, `men G6PD`, `tan huyết`, `khoa nội tổng hợp`.

## Vì sao cách này giải được đúng phản biện của bạn

| Phản biện | Cách này trả lời |
|---|---|
| "không kiếm ra text y khoa để làm vậy" | **Không cần text mới.** Dùng chính output model đã sinh trên 100 file có sẵn |
| Không mở rộng được | **Tự mở rộng** — mỗi lần train xong, chạy lại, lỗi mới lại thành negative mới (vòng lặp hard negative mining chuẩn) |
| Tốn công duyệt tay | Chỉ 40–60 ca/vòng, 15 phút. Và **duyệt lỗi thật có giá trị hơn nhiều** so với duyệt danh sách LLM bịa |

## Số lượng cần — không nhiều như tưởng

Negative dùng làm **distractor chèn vào text sinh ra**, không phải để liệt kê cho đủ:

```
300 negative × chèn 2–4 cái/tài liệu × 500 tài liệu  →  thừa sức phủ
```

Nên **~300 mục là đủ**, không cần hàng nghìn. Nguồn:

| Nguồn | Số lượng | Công |
|---|---|---|
| Lỗi thật từ bài nộp V2 (mục trên) | ~50 | 15 phút duyệt |
| Đã ghi nhận trong các vòng soi trước | ~20 | có sẵn |
| 7 nhóm × ~15 mục, LLM sinh có few-shot **lấy từ 2 nguồn trên** | ~100 | 20 phút |
| Sinh theo luật: `khoa X`, `phòng khám X` với X từ danh sách chuyên khoa | ~50 | code |
| Bổ sung khi soi output các vòng sau | tăng dần | — |

Điểm mấu chốt: LLM vẫn dùng được ở dòng 3, **nhưng few-shot phải là lỗi thật đã quan sát**, không phải ví dụ tôi bịa. Đó là khác biệt giữa vòng này và vòng trước.

---

# Thứ tự test vòng 4

| # | Việc | Xem gì |
|---|---|---|
| 1 | Prompt 3 (đã bỏ ngoặc vuông) | Tiêu đề sạch chưa · còn lọt `rabies`/`hydrophobia` không |
| 2 | Prompt 1 — `"Bệnh dại"` | Đủ 11 dòng · không bịa thuốc · không từ meta |
| 3 | Prompt 1 — `"Trứng cá"` | Còn lạc đề không |
| 4 | — | **Bỏ Prompt 4**, chuyển sang khai thác lỗi thật (mục trên) |
