# Kế hoạch sinh dữ liệu huấn luyện tổng hợp — bản đầy đủ

**Ràng buộc:** model ≤9B, không API ngoài.
**Mục tiêu:** ~6.000 thực thể + ~2.000 ca đối chứng âm, nhãn chính xác, phân bố khớp đề thi.
**Phạm vi:** NER 5 loại trước; **candidate linking làm sau nhưng đã tính đến ngay từ khâu sinh data**.

---

## 0. Nguyên lý bất di bất dịch

> **LLM không bao giờ gán nhãn. Nó chỉ viết văn và đề xuất kiến thức y khoa.**
>
> **Nhãn có trước → sinh text quanh nhãn.** Nhưng text phải là VĂN THẬT, không phải chuỗi KB dán liền.

Hai cái bẫy đã đo được, kế hoạch này chặn cả hai:

| Bẫy | Bằng chứng | Cơ chế chặn |
|---|---|---|
| LLM gán nhãn sai | `dataset2` recall **53%** | LLM không gán nhãn; nhãn có trước hoặc neo bằng tìm chuỗi chính xác |
| Sinh ngược nhưng dán chuỗi KB | `data/dataset` **55.6%** từ nằm trong thực thể | Cổng mật độ 8–18%, trượt là loại mẫu |

---

## 1. ĐIỀU CHỈNH ĐIỂM 7 — thuốc chung chung (sửa nhận định trước của tôi)

Trước đó tôi nói *"không map được RxNorm cũng không sao vì chỉ làm NER"*. **Nhận định đó sai** vì candidate linking sẽ làm sau — lúc đó `thuốc hạ sốt` không tra ra được mã nào.

### Cách xử lý đúng: giữ lại, nhưng ĐÁNH DẤU

Không được loại `thuốc hạ sốt`, `kháng sinh`, `thuốc nam` khỏi data — vì **đề thi có đầy** kiểu nói đó, loại đi thì model mù. Nhưng phải ghi rõ nó thuộc nhóm nào để bước candidate sau biết đường xử lý.

**Bổ sung trường `linkable` vào metadata sinh data** (không xuất ra file nhãn cuối, chỉ dùng nội bộ):

| Nhóm THUỐC | Ví dụ | `linkable` | Bước candidate sau này |
|---|---|---|---|
| Hoạt chất cụ thể | `omeprazole`, `furosemid 40mg`, `Chlorpheniramin 4mg` | `true` | Tra RxNorm → có mã |
| Biệt dược | `Medrol 16mg`, `Omez 20mg`, `Zestril` | `true` | Tra RxNorm brand → có mã |
| **Nhóm thuốc chung** | `kháng sinh`, `thuốc hạ sốt`, `thuốc giảm đau`, `corticoid` | **`false`** | **ABSTAIN — trả `candidates: []`** |
| Không xác định | `thuốc nam`, `thuốc đông y`, `thực phẩm chức năng` | **`false`** | **ABSTAIN** |

Lợi ích kép:
1. **NER**: model học nhận diện cả 4 nhóm → không bỏ sót
2. **Candidate sau này**: đã có sẵn nhãn `linkable` để huấn luyện/hiệu chỉnh bộ abstain, không phải đoán

**Tỷ lệ đề xuất trong data:** 65% linkable / 35% không linkable — phản ánh thực tế đề thi (`kháng sinh`, `corticoid` xuất hiện rất nhiều trong văn tư vấn).

### Kho THUỐC gồm 3 nguồn

1. **Hoạt chất tách từ RxNorm** — đo được **21.484 tên duy nhất** (không phải 17k như tôi nói ban đầu; con số cũ đếm thiếu vì chỉ lấy term nguyên văn ≤2 từ)
   ```
   "Chlorpheniramine 0.4 MG/ML Oral Solution" → tách "Chlorpheniramine" → dựng "Chlorpheniramin 4mg"
   ```
   Bỏ dạng đóng gói thương mại (`Tribenzor 40/5/12.5 (olmesartan medoxomil / ...)`) — bác sĩ Việt không viết vậy.

2. **Biến thể chính tả Việt** — rụng `-e` cuối: `furosemide→furosemid`, `amlodipine→amlodipin`; cầu INN↔USAN: `paracetamol↔acetaminophen`

3. **Nhóm chung tiếng Việt** — danh sách thủ công ~80 mục, `linkable=false`

---

## 2. Tầng 0 — Kho nguồn

### 2.1. Kho surface form DƯƠNG (thực thể thật)

| Loại | Nguồn | Mục tiêu |
|---|---|---|
| `CHẨN_ĐOÁN` | ICD-VN ≤6 từ, **phân tầng đủ 22 chương** (mỗi chương ≥30 term) + khai thác từ text thật | ≥1.200 form |
| `TRIỆU_CHỨNG` | ICD chương R + khai thác từ 1.277 bullet đề thi + 490 nhãn `dataset2` | ≥1.000 form |
| `THUỐC` | 3 nguồn ở mục 1 | ≥1.500 form |
| `TÊN_XÉT_NGHIỆM` | **`kb/xetnghiem_ten.txt`, 598 tên trích tự động từ bảng giá thật** (xem 2.2) | 598 form |
| `KẾT_QUẢ_XÉT_NGHIỆM` | **Sinh theo luật** (xem 2.2) | vô hạn |

**Về phủ chương ICD:** mục tiêu không phải liệt kê hết bệnh mà là **phủ hết KIỂU ĐẶT TÊN** — `viêm...`, `hội chứng...`, `u ác tính...`, `gãy...`, `rối loạn...`, `nhiễm...`. Lấy đều tuyệt đối trên 14.627 term sẽ đầy bệnh hiếm mà đề thi không có. Nên: **mỗi chương ≥30 term để đủ khuôn, phần dư dồn vào chương phổ biến** (hô hấp, tiêu hoá, cơ xương khớp, da liễu, tim mạch).

### 2.2. `TÊN_XÉT_NGHIỆM` — trích tự động, KHÔNG gõ tay

Loại này thiếu nhất (13 mẫu ở `dataset2`) và ban đầu tôi định gõ tay danh sách viết tắt (`WBC, HGB, CRP...`) — **đúng cái đã bị nhắc nhở**. Sửa lại: đã **trích tự động** 598 tên thật từ một bảng giá viện phí (không có KB chuẩn nào cho xét nghiệm ở Việt Nam — không LOINC, ICD chương Z chỉ là "khám sức khoẻ" không liệt kê xét nghiệm).

**Cách trích** (chi tiết ở `kb/README.md`): bảng gốc bị làm phẳng khi copy (mỗi ô một dòng). Không tách được bằng hình dạng chuỗi đơn thuần — thử đầu tiên dùng "chữ hoa/ngắn/không dấu cách" để nhận mã lab đã **nhầm chính tên xét nghiệm** (`ACTH`, `ADH`, `CEA` trông giống hệt mã nội bộ `DƯ-MDLS`). Sửa bằng nhìn trước 1 token: dựa vào VỊ TRÍ trong cấu trúc bảng (đứng trước mã khác = mã; đứng trước giá = tên), không dựa vào nội dung chữ. Trích được 598/~610 bản ghi.

→ **`kb/xetnghiem_ten.txt`** dùng thẳng làm kho DƯƠNG cho loại này, không cần sinh gì thêm.

**Kết quả xét nghiệm — sinh theo LUẬT CẤU TRÚC** (không phải từ vựng, nên gõ công thức là hợp lý, khác với việc gõ tên riêng):
```
số + đơn vị (chấm)  : 14.99 G/L, 6.4 mmol/l, 92 g/L, 2.5 ng/mL
số + đơn vị (phẩy)  : 4,49 T/l, 6,4 mmol/l          ← thập phân kiểu Việt
tỷ lệ               : 130/76 mmHg, 120/80
định tính           : âm tính, dương tính, (+), (-), (++), (±)
mũi tên / xu hướng  : ↑, ↓, tăng, giảm, tăng nhẹ
mô tả               : men gan tăng, không thấy bất thường, bình thường, trong giới hạn
ngưỡng              : < 0.01, > 200, ≤ 5, ≥ 10
```
Đơn vị (`mmol/l`, `g/L`...) lấy từ chính whitelist `UNIT` đã dùng trong `branch_b_lab_tests.py` — tái dùng luật đã kiểm, không bịa thêm.

**Cách ghép tên (từ `xetnghiem_ten.txt`) ↔ kết quả (sinh theo luật) — 8 format dòng**, trải đều để không lệch như luật V1:
```
1. Ure: 6,4 mmol/l              ← dấu hai chấm
2. Ure : 6,4 mmol/l             ← có cách trước dấu
3. Ure = 6,4 mmol/l             ← dấu bằng
4. Ure 6,4 mmol/l               ← không dấu phân tách
5. - Ure: 6,4 mmol/l            ← có bullet
6. • Ure: 6,4 mmol/l            ← bullet khác
7. Ure ↑                        ← chỉ mũi tên, KHÔNG có số
8. Ure                          ← ĐỨNG MỘT MÌNH, không có kết quả
   WBC : 14.99 G/L NEUT% : 82.9 %   ← nhiều cặp DÍNH LIỀN trên một dòng
```
Format 7 và 8 là yêu cầu riêng của bạn và cũng là lỗ hổng đã đo: luật V1 bắt buộc "số + đơn vị" nên bỏ sót **85%** tên xét nghiệm (`nội soi` 30 lần → bắt 0).

### 2.3. Kho ÂM — "giống thực thể nhưng KHÔNG phải" (phần mới, quan trọng)

Đây là thứ cả hai bộ data hiện tại **hoàn toàn không có**, và là nguyên nhân model gán bừa (`chăn màn`, `băng phiến` thành THUỐC).

| Nhóm | Ví dụ | Vì sao dễ nhầm |
|---|---|---|
| **Hành động y tế** | khám lâm sàng, theo dõi, tư vấn, chuyển tuyến, nhập viện, tái khám, xuất viện | Xuất hiện đúng chỗ thực thể hay xuất hiện |
| **Khoa / phòng / chuyên ngành** | khoa nội tổng hợp, phòng khám da liễu, chuyên khoa tim mạch, bác sĩ Da liễu | Chứa tên bệnh lý/chuyên ngành |
| **Chứa chữ "thuốc" nhưng KHÔNG phải thuốc** | **thuốc lá**, thuốc trừ sâu, thuốc nhuộm tóc, thuốc tẩy | Bẫy từ vựng kinh điển |
| **Sinh lý bình thường** | ăn ngủ bình thường, đại tiện bình thường, kinh nguyệt đều, da niêm hồng | Cấu trúc câu giống mô tả triệu chứng |
| **Yếu tố nguy cơ / thói quen** | hút thuốc lá, uống rượu bia, ăn mặn, ít vận động, béo phì do nếp gấp da | Liên quan y khoa nhưng không phải triệu chứng |
| **Thời gian / nhân khẩu** | cách đây 3 ngày, từ sáng nay, 29 tuổi, bệnh nhân nam, giường số 5 | Đứng cạnh thực thể, hay bị nuốt vào span |
| **Vật dụng / môi trường** | băng phiến, long não, chăn màn, quần áo ẩm | **Đã bị gán nhầm THUỐC ở bài nộp thật** |
| **Đơn vị hành chính bệnh án** | Lý do vào viện, Tiền sử bệnh, Không ghi rõ, trang 2/5, phần bệnh án bị mờ | Là heading/placeholder, không phải nội dung |
| **Điều trị không phải xét nghiệm** | phẫu thuật cắt ruột thừa, ghép thận, truyền dịch, thở oxy | Giống thủ thuật chẩn đoán |

**Quy tắc sống còn:** kho ÂM phải **loại trừ khỏi kho DƯƠNG** dùng cho bước quét từ điển ngược (mục 5.3), nếu không nó sẽ tự gán nhãn cho chính các ca âm này.

---

## 3. Tầng 1 — Kịch bản ca bệnh nhất quán

Dùng LLM **đúng sở trường** (kiến thức y khoa), không dùng để gán nhãn.

```
Cho chẩn đoán chính: "{diagnosis}"  (lấy từ ICD, đã phân tầng theo chương)
Liệt kê khái niệm y khoa thường đi kèm, mỗi dòng một mục:
TC|<triệu chứng>              (4-6 mục)
TH|<thuốc điều trị>           (2-3 mục)
TX|<xét nghiệm thường chỉ định> (2-3 mục)
Dùng cách viết của bác sĩ Việt Nam, ngắn gọn. Không giải thích.
```

**Chốt chặn ảo giác:** mọi chuỗi trả về **phải khớp KB** mới được dùng — `TH` khớp RxNorm hoặc danh sách nhóm chung; `TC`/`CD` khớp ICD hoặc kho surface form. Không khớp ⇒ **loại mục đó** (không loại cả ca). LLM bịa tên thuốc cũng vô hại vì chuỗi bịa không có trong KB.

---

## 4. Tầng 2A — Khối bệnh án cấu trúc: KHÔNG dùng LLM khi điền

### 4.1. Ngân hàng template do LLM sinh (chạy MỘT LẦN, offline)

Theo ý bạn — để đa dạng, không từ ngữ cứng. Nhưng tách bạch để **không mất tính đúng của nhãn**:

- **LLM sinh KHUNG**: tên heading, thứ tự mục, kiểu bullet, mức thụt lề → tạo ngân hàng **80–120 template**
- **Code điền thực thể** vào khung → vị trí tính theo cấu tạo, **nhãn đúng 100%**

LLM đa dạng hoá cái vỏ, code giữ cái ruột. Nếu để LLM tự đặt thực thể vào text thì mất đặc tính "nhãn đúng theo cấu tạo".

Prompt sinh template (1 lần):
```
Sinh 20 biến thể khung bệnh án tiếng Việt. Mỗi khung gồm các mục có tiêu đề
và các dòng gạch đầu dòng để trống dạng {SLOT}. Đa dạng tên tiêu đề, thứ tự,
ký hiệu gạch đầu dòng. KHÔNG điền nội dung y khoa.
```
Kiểm tự động: template phải có ≥3 heading và ≥4 `{SLOT}`, không chứa chữ y khoa nào.

### 4.2. Điền bằng code — offset chính xác tuyệt đối

```python
def build_block(template, case, rng):
    """Điền case vào template. Offset tính theo cấu tạo -> nhãn đúng 100%."""
    out, ents, cur = [], [], 0
    for line in template:
        if '{SLOT}' not in line:
            out.append(line); cur += len(line) + 1          # heading/placeholder
            continue
        text, etype = case.pop_next()                        # thực thể tiếp theo
        prefix = line.split('{SLOT}')[0]                     # "    - " hoặc "    - Ure: "
        start = cur + len(prefix)
        filled = prefix + text
        out.append(filled)
        ents.append({'text': text, 'type': etype, 'position': [start, start + len(text)]})
        cur += len(filled) + 1
    return '\n'.join(out), ents
```

**Chi phí LLM: 0 giây/mẫu. Độ chính xác nhãn: 100%.**

---

## 5. Tầng 2B — Văn xuôi hỏi–đáp bằng LLM

### 5.1. Prompt

```
Viết đoạn hỏi–đáp bệnh nhân ↔ bác sĩ bằng tiếng Việt tự nhiên.

BẮT BUỘC dùng NGUYÊN VĂN, không sửa một chữ:
  - {entity_1}
  - {entity_2}
  ...

BẮT BUỘC nhắc tới (nhưng đây KHÔNG phải bệnh/thuốc, chỉ là bối cảnh):
  - {distractor_1}      ← ca âm, xem 6.1
  - {distractor_2}

YÊU CẦU:
- 180-260 từ. Bệnh nhân hỏi, bác sĩ trả lời.
- KHÔNG nhắc khái niệm y khoa nào khác ngoài danh sách trên.
- Không gạch đầu dòng, không liệt kê.
```

### 5.2. Neo nhãn — tìm chuỗi chính xác

Mỗi cụm bắt buộc phải tìm thấy **đúng 1 lần**. Không thấy hoặc thấy nhiều lần ⇒ **sinh lại** (tối đa 3 lần). Không bao giờ "đoán gần đúng".

### 5.3. Quét từ điển ngược — chặn false negative

LLM có thể tự thêm khái niệm ngoài danh sách (ta yêu cầu 4 cụm, nó viết thêm `sốt cao`). Cụm đó nằm trong text mà **không có nhãn** ⇒ dạy model bỏ sót.

Giải: quét **toàn bộ kho DƯƠNG** lên text đã sinh; cụm nào xuất hiện mà chưa gán thì **gán bổ sung bằng khớp từ điển** (chính xác, không qua LLM).

⚠️ Kho **ÂM phải được loại trừ** khỏi bước quét này.

---

## 6. HARD CASE — thiết kế đầy đủ

Đây là phần quyết định chất lượng model. Cả hai bộ data hiện tại **không có ca khó nào**.

### 6.1. Đối chứng âm chủ động (distractor injection)

Chèn có chủ đích chuỗi từ kho ÂM vào text, và **cố tình KHÔNG gán nhãn**. Vì sinh ngược nên ta **biết chắc** cái gì không được gán — đây là siêu năng lực của hướng làm này.

```
Text sinh ra:
"Bệnh nhân nam 29 tuổi, hút thuốc lá 10 năm, vào khoa nội tổng hợp
 vì đau bụng vùng hạ sườn phải. Đã khám lâm sàng, chẩn đoán viêm dạ dày,
 điều trị bằng omeprazole. Bệnh nhân ăn ngủ bình thường."

Nhãn (chỉ 3):
  đau bụng vùng hạ sườn phải  -> TRIỆU_CHỨNG
  viêm dạ dày                 -> CHẨN_ĐOÁN
  omeprazole                  -> THUỐC

KHÔNG gán (4 ca âm cố ý):
  hút thuốc lá          (yếu tố nguy cơ, KHÔNG phải triệu chứng, và "thuốc lá" ≠ THUỐC)
  khoa nội tổng hợp     (đơn vị hành chính)
  khám lâm sàng         (hành động y tế)
  ăn ngủ bình thường    (sinh lý bình thường)
```

**Tỷ lệ:** mỗi mẫu chèn 2–4 ca âm. Tổng ~2.000 ca âm trên toàn bộ dataset.

### 6.2. Cặp đối lập tối thiểu (minimal pair)

Sinh **cùng một câu, chỉ khác một chi tiết**, một bên là thực thể một bên không. Đây là cách hiệu quả nhất dạy model ranh giới.

| Có nhãn | Không nhãn |
|---|---|
| `Bệnh nhân dùng **thuốc giảm đau**` | `Bệnh nhân hút **thuốc lá**` |
| `Chỉ định **nội soi dạ dày**` | `Chỉ định **phẫu thuật cắt ruột thừa**` (điều trị, không phải XN) |
| `Chẩn đoán **viêm da tiếp xúc**` | `Khám tại **phòng khám da liễu**` |
| `Xét nghiệm **chức năng gan**` | `Bệnh nhân có **chức năng vận động** tốt` |
| `Ghi nhận **sốt cao**` | `Bệnh nhân **không sốt**` → xem 6.3 |

### 6.3. Phủ định — quy ước phải chốt

**Đây là điểm cần bạn quyết**, tôi đề xuất mặc định và nêu rõ lý do:

| Câu | Đề xuất | Lý do |
|---|---|---|
| `bệnh nhân **không sốt**` | Gán `sốt` = TRIỆU_CHỨNG | Khái niệm CÓ được nhắc tới; phủ định thuộc về trường `assertions` chứ không phải NER |
| `**phủ nhận đau ngực**` | Gán `đau ngực` = TRIỆU_CHỨNG | như trên |
| `**loại trừ viêm ruột thừa**` | Gán `viêm ruột thừa` = CHẨN_ĐOÁN | như trên |
| `**không có tiền sử về bệnh**` | **KHÔNG gán gì** | Không nhắc khái niệm cụ thể nào. `dataset2` gán nhãn ca này là **SAI** |
| `**chưa ghi nhận bất thường**` | **KHÔNG gán gì** | như trên |

Sinh ~600 mẫu phủ định, chia đều 5 khuôn: `không`, `phủ nhận`, `chưa`, `loại trừ`, `không thấy`.

### 6.4. Xét nghiệm KHÔNG có kết quả (yêu cầu riêng của bạn)

Chính là lỗ hổng đã đo: luật V1 đòi "số + đơn vị" nên bỏ sót 85% tên xét nghiệm.

```
Các thủ thuật đã thực hiện
- nội soi dạ dày                    ← TÊN_XÉT_NGHIỆM, KHÔNG có kết quả
- chọc dò dịch não tủy              ← TÊN_XÉT_NGHIỆM, KHÔNG có kết quả

Bác sĩ chỉ định làm công thức máu và siêu âm ổ bụng.
                     ^^^^^^^^^^^^^     ^^^^^^^^^^^^^^  cả hai đều là TÊN_XÉT_NGHIỆM
```

**Tỷ lệ bắt buộc: ≥40% số `TÊN_XÉT_NGHIỆM` đứng một mình, không kèm kết quả.**

### 6.5. Ranh giới span khó

| Ca | Xử lý | Ví dụ |
|---|---|---|
| Liệt kê ngăn bởi dấu phẩy | **Tách riêng từng cái** | `Công thức máu, CRP, máu lắng` → **3** thực thể |
| Nối bằng "và" | Tách riêng | `sốt và ho` → 2 thực thể |
| Có bổ ngữ vị trí | Lấy **cả bổ ngữ** nếu là một khái niệm y khoa | `đau bụng vùng hạ sườn phải` = 1 thực thể (không tách) |
| Có bổ ngữ hoàn cảnh | **Bỏ bổ ngữ** | `mệt mỏi khi gắng sức trong tuần qua` → chỉ `mệt mỏi` |
| Ngoặc giải thích | **2 thực thể riêng** | `Rối loạn chuyển hóa tinh bột (amyloidosis)` → 2 |
| Giai đoạn/độ | Lấy cả | `ung thư phổi giai đoạn IV`, `gan nhiễm mỡ độ 2` |
| Hư từ ở biên | **Cắt bỏ** | `và đau bụng` → `đau bụng`; `răng khôn hàm dưới **cho** mọc lệch` → bỏ `cho` |

Sinh ≥500 mẫu chứa các ca này.

### 6.6. Chất vừa THUỐC vừa XÉT NGHIỆM

Cùng một chữ, khác loại theo ngữ cảnh — chỉ dạy được bằng cặp đối lập:

| Ngữ cảnh | Loại |
|---|---|
| `Glucose 5% x 1000ml truyền tĩnh mạch` | **THUỐC** (có hàm lượng + đường dùng) |
| `Glucose máu: 13,2 mmol/l` | **TÊN_XÉT_NGHIỆM** + **KẾT_QUẢ** |
| `Albumin 20% truyền` | **THUỐC** |
| `Albumin: 32 g/l` | **TÊN_XÉT_NGHIỆM** + **KẾT_QUẢ** |

Áp dụng cho: `glucose`, `albumin`, `creatinin`, `protein`, `calcium`, `kali`, `sắt`, `vitamin K`, `insulin`.
Sinh ≥300 cặp.

### 6.7. Ngữ cảnh giáo dục vs ngữ cảnh bệnh nhân

Đề thi trộn bài giảng bệnh học với bệnh án thật. Cần dạy model cả hai đều được trích (theo suy luận từ phân rã WER, gold **có** tính vùng tư vấn), nhưng phải hiểu khác biệt:

```
Bệnh nhân: "Em bị viêm dạ dày"              → viêm dạ dày, của bệnh nhân
Bác sĩ:    "Viêm dạ dày là bệnh thường gặp"  → viêm dạ dày, giảng chung
Giả định:  "Có phải em bị viêm gan không?"   → viêm gan, câu hỏi giả định
Lời khuyên:"Không nên tự ý dùng kháng sinh"  → kháng sinh, lời khuyên chung
```

Sinh đủ 4 ngữ cảnh cho cùng một thực thể.

### 6.8. Nhiễu văn bản THẬT

Chỉ mô phỏng lỗi **có thật trong đề thi**:

| Dạng | Ví dụ có thật trong đề thi | Tỷ lệ |
|---|---|---|
| Dính hai từ | `bệnh dạithường`, `điên dạiở`, `địnhkhai` | 3% |
| Thiếu cách sau dấu câu | `viêm dạ dày.Bệnh nhân` | 2% |
| Lặp từ | `chụp chụp ct sọ não` ← **có thật trong `input/3.txt`** | 1% |
| Viết hoa bất thường | `VIÊM DẠ DÀY`, `Viêm Dạ Dày` | 2% |
| Khoảng trắng thừa | `đau  bụng`, `Căng thẳng  nhiều` | 2% |

**Ba ràng buộc bắt buộc:**
1. Nhiễu **chỉ rơi NGOÀI span thực thể**
2. Mỗi lần chèn phải **dịch lại toàn bộ offset phía sau**
3. **KHÔNG** hoán vị ký tự trong từ (`Khho anội`, `36 tổui`) — dạng này không tồn tại trong đề thi

---

## 7. Phân bố & số lượng

### 7.1. Theo loại

Hai lực kéo ngược: **số lượng tuyệt đối** quyết định có học được không; **tỷ lệ tương đối** quyết định có gán bừa không. Cân bằng cứng 20/20/20/20/20 sẽ khiến model over-predict loại hiếm.

Đo trên đề thi: bullet dưới heading xét nghiệm/thủ thuật = **82/1277 = 6.4%** — TX/KQ thật sự là thiểu số.

| Loại | Tỷ lệ | Số lượng | Ghi chú |
|---|---|---|---|
| `TRIỆU_CHỨNG` | 33% | ~1.980 | |
| `CHẨN_ĐOÁN` | 25% | ~1.500 | phân tầng đủ 22 chương ICD |
| `THUỐC` | 16% | ~960 | 65% linkable / 35% nhóm chung |
| `TÊN_XÉT_NGHIỆM` | 15% | ~900 | **≥40% không kèm kết quả** |
| `KẾT_QUẢ_XÉT_NGHIỆM` | 11% | ~660 | trải đều 7 dạng viết |
| **Tổng dương** | | **~6.000** | |
| **Ca âm (không nhãn)** | | **~2.000** | kho ÂM, mục 6.1 |

Oversample TX/KQ so với tỷ lệ thật (6.4% → 26%) để học được, nhưng không cân bằng cứng.

### 7.2. Theo cấu trúc tài liệu

| Loại tài liệu | Tỷ lệ | Mô tả |
|---|---|---|
| Văn xuôi + khối cấu trúc | 65% | Giống đề thi nhất |
| Chỉ văn xuôi | 25% | Giống `dataset2` |
| Chỉ khối cấu trúc | 10% | Bệnh án thuần |

Tổng ~500 file, mỗi file 1.500–4.000 ký tự.

---

## 8. Cổng kiểm định — 9 điều kiện

Trượt bất kỳ ⇒ loại mẫu, sinh lại.

| # | Điều kiện | Ngưỡng | Chống lỗi |
|---|---|---|---|
| 1 | `raw[start:end] == text` mọi thực thể | 100% | Lệch offset |
| 2 | **Tỷ lệ từ nằm trong thực thể** | **8–18%** | Bệnh `data/dataset` (55.6%) |
| 3 | Không có span chồng lấn | 0 | Nhãn mâu thuẫn |
| 4 | Mọi cụm bắt buộc tìm thấy đúng 1 lần | 100% | LLM bỏ quên/sửa chữ |
| 5 | Quét từ điển ngược: không còn cụm dương chưa gán | 0 sót | False negative |
| 6 | **Không có chuỗi thuộc kho ÂM bị gán nhãn** | 0 | Ca âm bị gán nhầm |
| 7 | Độ dài file 1.500–4.000 ký tự | — | Tài liệu quá ngắn |
| 8 | Nhiễu không rơi vào trong span | 0 vi phạm | Phá nhãn |
| 9 | Tỷ lệ mỗi loại lệch <15% so với mục tiêu | — | Lệch phân bố |

Ghi log tỷ lệ loại. **Loại >40% ⇒ dừng sửa prompt, không hạ ngưỡng.**

---

## 9. Tập kiểm định — điều kiện tiên quyết

Dữ liệu tổng hợp luôn có rủi ro **lệch phân bố**: model giỏi trên data sinh ra, kém trên đề thi thật. Chỉ một cách phát hiện:

> **Gán tay 5–10 file từ chính bộ đề thi**, CHỈ để đo, KHÔNG train.

Không có tập này thì train xong không biết tốt hay xấu — quay lại đoán mù. Theo dõi P/R/F1 **theo từng loại**, cộng thêm chỉ số riêng cho hard case:
- Tỷ lệ gán nhầm trên kho ÂM (phải gần 0)
- Recall trên `TÊN_XÉT_NGHIỆM` không kèm kết quả
- Độ chính xác biên span (exact match vs partial)

---

## 10. Thi công

| # | Việc | Cần GPU? | Ước tính |
|---|---|---|---|
| 1 | T0 — kho DƯƠNG (tách hoạt chất RxNorm, phân tầng ICD 22 chương, khai thác text thật) | ❌ | 1 buổi |
| 2 | T0 — **kho ÂM** (9 nhóm, mục 2.3) | ❌ | nửa buổi |
| 3 | T0 — sinh XÉT NGHIỆM theo luật, 6 dạng tên × 7 dạng kết quả × 8 format dòng | ❌ | nửa buổi |
| 4 | T2A — ngân hàng template (LLM 1 lần) + code điền | ✅ 5 phút | 1 buổi |
| 5 | Cổng kiểm định 9 điều kiện + báo cáo | ❌ | nửa buổi |
| 6 | **Gán tay 5–10 file đề thi làm tập kiểm định** | ❌ | 1–2 giờ |
| 7 | Hard case: 6.1–6.8 | ❌ phần lớn | 1 buổi |
| 8 | T1 + T2B — sinh kịch bản & văn xuôi | ✅ ~40 phút | 1 buổi |
| 9 | T4 — nhiễu hoá | ❌ | nửa buổi |
| 10 | Train encoder 5 loại + đo trên (6) | ✅ ~1 giờ | 1 buổi |

**Bước 1–3, 5–7, 9 không cần GPU** — làm được ngay. Riêng bước 3 và 4 lấp đúng hai lỗ hổng lớn nhất (xét nghiệm & khối cấu trúc) mà gần như không tốn LLM.

**Tổng GPU: dưới 2 giờ.**

---

## 11. Vì sao kế hoạch này chặn được mọi lỗi đã gặp

| Lỗi đã gặp | Bằng chứng | Cơ chế chặn |
|---|---|---|
| LLM gán nhãn sai | `dataset2` recall 53% | LLM không gán nhãn (§0) |
| LLM ảo giác tên thuốc/bệnh | — | KB xác thực mọi chuỗi (§3) |
| Dán chuỗi KB, mất ngữ cảnh | `data/dataset` 55.6% | Cổng #2: mật độ 8–18% |
| Dùng dạng chuẩn KB phi tự nhiên | RxNorm 87% không dùng được | Tách hoạt chất + dựng lại kiểu Việt (§1) |
| Thiếu khối bệnh án cấu trúc | 0/100 cả hai bộ | T2A template, nhãn đúng 100% (§4) |
| Thiếu xét nghiệm | KQ chỉ 13 mẫu | 598 tên trích tự động + kết quả sinh theo luật, 8 format ghép (§2.2) |
| Bỏ sót XN không có kết quả | luật V1 bắt 15% | ≥40% XN đứng một mình (§6.4) |
| Gán bừa (`chăn màn`→THUỐC) | bài nộp thật | Kho ÂM + cổng #6 (§2.3, §6.1) |
| False negative | — | Quét từ điển ngược, cổng #5 (§5.3) |
| Nhãn sai ca phủ định | `dataset2` `không có tiền sử về bệnh` | Quy ước phủ định chốt rõ (§6.3) |
| Biên span dính hư từ | `dataset2` `...cho mọc lệch` | Quy ước biên (§6.5) |
| Nhiễu nhân tạo sai kiểu | `data/dataset` `Khho anội` | Chỉ mô phỏng nhiễu có thật (§6.8) |
| Lệch phân bố tổng hợp↔thật | — | Tập kiểm định gán tay (§9) |
| Thuốc chung chung không tra được mã | — | Trường `linkable` (§1) |
| Gõ tay từ vựng thay vì quét (lỗi của chính tôi, mới bị bắt) | bản đầu của plan này tự gõ danh sách `WBC, HGB...` | Trích tự động bằng parser nhìn-trước-1-token từ bảng giá thật — 598 tên, không gõ tay (§2.2) |
