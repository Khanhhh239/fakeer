# Đánh giá 2 bộ dữ liệu & Yêu cầu sinh dữ liệu huấn luyện

**Gửi:** bộ phận Data
**Mục đích:** train model NER 5 loại (`TRIỆU_CHỨNG`, `CHẨN_ĐOÁN`, `THUỐC`, `TÊN_XÉT_NGHIỆM`, `KẾT_QUẢ_XÉT_NGHIỆM`) cho bài thi trích xuất khái niệm y khoa tiếng Việt.

**Kết luận ngắn:**

| Bộ | Kết luận | Lý do |
|---|---|---|
| `data/dataset` (100 file, 853 thực thể) | ❌ **KHÔNG dùng được** | Văn bản là chuỗi KB dán liền, không phải câu. Train vào sẽ làm model tệ đi. |
| `dataset2` (100 file, 490 thực thể) | ⚠️ **Dùng được, nhưng chỉ đạt ~1/6 lượng cần** | Văn bản thật, nhãn ổn, nhưng thiếu hoàn toàn phần bệnh án cấu trúc + thiếu 3/5 loại |

Cần sinh thêm **3.000–5.000 thực thể** theo đặc tả ở Phần 2.

---

# PHẦN 1 — PHÂN TÍCH LỖI

## 1A. Bộ `data/dataset` — KHÔNG dùng được

### Lỗi 1 (chí mạng): Văn bản không có ngữ cảnh — 55.6% số từ nằm trong thực thể

| Bộ dữ liệu | Tỷ lệ từ nằm trong thực thể |
|---|---|
| **`data/dataset`** | **55.6%** |
| `dataset2` | 8.2% |
| Đề thi thật | ~15% |
| *Văn bản NER tự nhiên (chuẩn ngành)* | *5–15%* |

**Nguyên văn `doc_000.txt`:**

```
Khho anội tổng hợp - giường số 56 tuổi. không có gì đặc biệệt — U ác tính ở
miệng - hầu, không xác địnhkhai Táhc bệnh sử 159.0 mg/dL47 tuổi  bệnh nhân
nam, 233.5mg/L — đã tư vấn cho gia đình
```

**Nguyên văn `doc_019.txt`:**

```
phần bệnh án bị mờ | crovalimab189.0 ng/mL
Thoái hóa tủy răngdexmedetomidine 0.18 MG Sublingual Filmhpần bệnh án bị ,mờ
maralixibat 9.5 MG/ML Oral Solution36 tổui bệnh nhân ữ không thấy như đã mô tả
```

Đây không phải câu tiếng Việt. Đây là **các chuỗi lấy nguyên văn từ từ điển RxNorm/ICD-10 dán liền nhau**, chèn thêm vài cụm mẫu (`"đã tư vấn cho gia đình"`, `"phần bệnh án bị mờ"`).

Bằng chứng lấy nguyên văn từ KB:

| Chuỗi trong dataset | Nguồn |
|---|---|
| `calcium ascorbate 50 MG / ferrous asparto glycinate 50 MG / polysaccharide iron complex 100 MG / succinic acid 50 MG Oral Capsule` | RxNorm, nguyên văn |
| `Tràn dịch màng tinh hoàn và/hoặc nang mào tinh hoàn` | ICD-10 VN, nguyên văn |
| `hội chứng hoặc loạn thần Korsakov, không do rượu` | ICD-10 VN, nguyên văn |
| `Gãy xương tác động đến nhiều vùng của một chi dưới, gãy hở` | ICD-10 VN, nguyên văn |

**Vì sao đây là lỗi chí mạng:**

Model NER học nhận diện thực thể **dựa vào ngữ cảnh xung quanh** — nó học rằng sau `"bệnh nhân bị ..."` hoặc `"chẩn đoán ..."` thường là một khái niệm y khoa. Ở bộ này **không có ngữ cảnh nào cả**, vì hơn một nửa văn bản chính là thực thể.

Hậu quả: model sẽ học **thuộc lòng danh sách chuỗi KB**, không học nhận diện. Đây là kiểu hỏng nguy hiểm nhất — điểm đo trên chính bộ này sẽ rất cao (vì thuộc lòng được), nhưng đưa vào văn bản thật là sập hoàn toàn. **Train vào còn tệ hơn không train.**

### Lỗi 2: Nhiễu ký tự nhân tạo

| Trong dataset | Đúng ra là |
|---|---|
| `Khho anội tổng hợp` | Khoa nội tổng hợp |
| `36 tổui bệnh nhân ữ` | 36 tuổi bệnh nhân nữ |
| `khai táh;c bệnh sử` | khai thác bệnh sử |
| `làm htêm cậ lâm sàng` | làm thêm cận lâm sàng |
| `kẾết quả được gửi` | Kết quả được gửi |
| `theo lời kể của người n.hà` | theo lời kể của người nhà |
| `Vào vIện  ngày` | Vào viện ngày |

Đề thi thật **cũng có lỗi chính tả**, nhưng là lỗi tự nhiên của người gõ (dính chữ: `"bệnh dạithường"`, `"điên dạiở"`). Còn đây là **hoán vị ký tự ngẫu nhiên trong từ** — dạng nhiễu không tồn tại trong đề thi, học vào chỉ tổ nhiễu.

### Lỗi 3: Thực thể dính liền nhau, không có dấu cách

```
crovalimab189.0 ng/mL
Thoái hóa tủy răngdexmedetomidine 0.18 MG Sublingual Film
Xạ hình xương bằng NaF = 267.98ng/mLtrong quá trình  điều trị
```

Ranh giới thực thể trở nên vô nghĩa vì không có dấu phân cách tự nhiên.

### Lỗi 4: Nhãn loại sai

| Text | Gán nhãn | Đúng ra là |
|---|---|---|
| `Thoái hóa tủy răng` | `TRIỆU_CHỨNG` | **`CHẨN_ĐOÁN`** — đây là tên bệnh, có trong ICD |
| `Kiểm tra sức khoẻ không xác định` | `TRIỆU_CHỨNG` | **Không phải thực thể** — đây là mã Z của ICD (khám sức khoẻ), không phải triệu chứng |

Có vẻ loại được gán theo *"chuỗi này lấy từ file KB nào"* chứ không theo nghĩa thật, nên sai khi các KB trộn lẫn.

### Lỗi 5: Tài liệu quá ngắn

| | `data/dataset` | Đề thi thật |
|---|---|---|
| Độ dài trung bình | **382 ký tự** | 2.038 ký tự |

Ngắn hơn 5 lần. Model không học được cách xử lý văn bản dài, ngắt câu, nhiều đoạn.

### Lỗi 6: Không có khối bệnh án cấu trúc

`0/100` file có bullet. Đề thi có `90/100` file với tổng **1.277 bullet**. (Xem mục 1B lỗi 1.)

---

## 1B. Bộ `dataset2` — Dùng được, nhưng chưa đủ

### Điểm tốt (giữ nguyên cách làm này)

- ✅ **Văn bản thật, tự nhiên** — câu có ngữ pháp, có mạch hội thoại bác sĩ–bệnh nhân
- ✅ **Mật độ thực thể 8.2%** — đúng khoảng tự nhiên
- ✅ **0/490 lệch offset** — `position` khớp chính xác 100%, không phải sửa gì
- ✅ **Nhãn phần lớn hợp lý.** Ví dụ `cell_030` gán rất chuẩn:

```
Text: "Da mặt em hiện đang nổi mụn li ti, mụn mủ quanh mặt, cảm giác ngứa da
       rất nhiều và da nóng... Tình trạng này có thể là viêm da tiếp xúc"

nổi mụn li ti     -> TRIỆU_CHỨNG   ✓
mụn mủ            -> TRIỆU_CHỨNG   ✓
ngứa da           -> TRIỆU_CHỨNG   ✓
da nóng           -> TRIỆU_CHỨNG   ✓
viêm da tiếp xúc  -> CHẨN_ĐOÁN     ✓
```

### Lỗi 1 (quan trọng nhất): Thiếu hoàn toàn khối bệnh án cấu trúc

| | `dataset2` | Đề thi thật |
|---|---|---|
| File có bullet `- ...` | **0/100** | 90/100 (1.277 bullet) |
| File có mốc bệnh án (`2. Tiền sử bệnh hiện tại`) | **0/100** | 70/100 |
| Độ dài file | 817 ký tự | 2.038 ký tự |

`dataset2` chỉ có **phần hỏi–đáp văn xuôi**. Nhưng đề thi là **hỏi–đáp web + MỘT KHỐI BỆNH ÁN CẤU TRÚC chèn vào giữa**, và khối đó chiếm khoảng **55% tổng số thực thể**.

**Đây là dạng đang thiếu — trích nguyên văn từ đề thi (`input/3.txt`):**

```
2.  Tiền sử bệnh hiện tại
    Lý do nhập viện
    - yếu sức nửa người bên phải
    - tình trạng tri giác giảm sút
    - nhìn song thị
    Diễn biến bệnh
    - Được con trai phát hiện tại nhà lúc khoảng 11:00 sáng, nằm sải trên sàn.
    - Đã được chụp chụp ct sọ não kết quả âm tính.
    - Bị một cơn nhịp tim chậm nặng và hạ huyết áp ngay sau khi study.
    Triệu chứng khi nhập viện
    - yếu sức nửa người bên phải
    - mệt mỏi
    Đặc điểm triệu chứng
    - Vị trí: yếu chân phải
    - Mức độ nghiêm trọng: Không ghi rõ

3.  Đánh giá tại bệnh viện
    Dấu hiệu lâm sàng
    - nhịp tim chậm
    - hạ huyết áp, không đặc hiệu
    Kết quả xét nghiệm
    - chụp ct sọ não: âm tính
    Các thủ thuật đã thực hiện
    - chụp ct sọ não
    - chọc dò dịch não tủy
```

Model train trên `dataset2` sẽ giỏi phần văn xuôi nhưng **mù phần này** — mà đây lại là phần chứa hơn nửa số điểm.

### Lỗi 2: Bỏ sót nhiều thực thể (recall ~53%)

**Nguyên văn `cell_075.txt`** (phần in đậm là bị bỏ sót):

```
Em đi tiểu nhiều lần mà tiểu không hết, em cũng hay đau bụng dưới ở bên trái...
Có phải em bị viêm đường tiết niệu không?
Tình trạng của bạn TIỂU RẮT, TIỂU LẮT NHẮT nhiều lần, cảm giác như tiểu không
hết, ĐAU VÙNG HẠ VỊ. Đây là trường hợp bị nhiễm trùng đường tiểu, khả năng
viêm bàng quang.
Nguyên nhân của nhiễm trùng đường tiểu có nhiều, như: Sỏi bàng quang, U XƠ TIỀN
LIỆT, ĐÁI ĐƯỜNG, BÀNG QUANG THẦN KINH... chủ yếu dùng kháng sinh... gây VIÊM
THẬN BỂ THẬN
```

| Đã gán (8) | Bị bỏ sót (7) |
|---|---|
| tiểu nhiều lần, tiểu không hết, đau bụng dưới ở bên trái, viêm đường tiết niệu, nhiễm trùng đường tiểu, viêm bàng quang, Sỏi bàng quang, kháng sinh | **tiểu rắt**, **tiểu lắt nhắt**, **đau vùng hạ vị**, **u xơ tiền liệt**, **đái đường**, **bàng quang thần kinh**, **viêm thận bể thận** |

Bỏ sót gần một nửa. Quan sát: **phần bác sĩ trả lời hay bị bỏ qua**, chỉ gán kỹ phần bệnh nhân hỏi. Cần gán đều cả hai phần.

### Lỗi 3: Lệch loại rất nặng — 3/5 loại gần như không có

| Loại | Số lượng | Đánh giá |
|---|---|---|
| `TRIỆU_CHỨNG` | 223 | đủ |
| `CHẨN_ĐOÁN` | 193 | đủ |
| `THUỐC` | **32** | ❌ quá ít |
| `TÊN_XÉT_NGHIỆM` | **29** | ❌ quá ít |
| `KẾT_QUẢ_XÉT_NGHIỆM` | **13** | ❌ gần như không có |

Với 13 mẫu, model không thể học được `KẾT_QUẢ_XÉT_NGHIỆM`. Ba loại này cần **ít nhất 400–600 mẫu mỗi loại**.

### Lỗi 4: Nhãn sai và biên span dính hư từ

**`cell_069`:**

| Text được gán | Loại | Vấn đề |
|---|---|---|
| `không có tiền sử về bệnh` | `TRIỆU_CHỨNG` | ❌ **Sai.** Đây là câu phủ định tiền sử, không phải triệu chứng. Không nên gán nhãn. |
| `răng khôn hàm dưới cho mọc lệch` | `TRIỆU_CHỨNG` | ❌ **Biên sai** — dính chữ `"cho"` của câu gốc (`"nhổ 1 răng khôn hàm dưới cho mọc lệch"`). Đúng phải là `răng khôn hàm dưới mọc lệch`. |
| `mất 1 răng nhai` | `TRIỆU_CHỨNG` | ⚠️ Tranh cãi — nên thống nhất quy ước |

---

# PHẦN 2 — YÊU CẦU SINH DỮ LIỆU

## 2.1. Số lượng

| Hạng mục | Yêu cầu |
|---|---|
| **Tổng số thực thể** | **3.000–5.000** (hiện có 490 dùng được) |
| Số tài liệu | 400–700 file |
| Độ dài mỗi file | **1.500–4.000 ký tự** (hiện `dataset2` 817, `data/dataset` 382 — đều quá ngắn) |

## 2.2. Tỷ lệ bắt buộc

**Cơ cấu tài liệu** — mỗi file phải giống đề thi:

| Phần | Tỷ lệ | Mô tả |
|---|---|---|
| Hỏi–đáp văn xuôi | ~2/3 độ dài | Như `dataset2` đang làm (giữ nguyên) |
| **Khối bệnh án cấu trúc** | ~1/3 độ dài | **PHẦN ĐANG THIẾU HOÀN TOÀN** |

Nên có **60–70% số file chứa khối bệnh án cấu trúc** (đề thi: 70/100).

**Cân bằng loại** — tối thiểu mỗi loại:

| Loại | Tối thiểu | Hiện có |
|---|---|---|
| `TRIỆU_CHỨNG` | 1.000 | 223 |
| `CHẨN_ĐOÁN` | 800 | 193 |
| `THUỐC` | 500 | 32 |
| `TÊN_XÉT_NGHIỆM` | 500 | 29 |
| `KẾT_QUẢ_XÉT_NGHIỆM` | 400 | 13 |

## 2.3. Chỉ số kiểm soát chất lượng (BẮT BUỘC tự đo trước khi giao)

| Chỉ số | Ngưỡng chấp nhận | Ý nghĩa |
|---|---|---|
| **Tỷ lệ từ nằm trong thực thể** | **8% – 18%** | >25% = đã thành "KB dán liền", **loại bỏ** |
| Lệch offset (`text != raw[start:end]`) | **0%** | Bắt buộc tuyệt đối |
| Độ dài span trung bình | 2 – 5 từ | >6 = đang lấy cả câu |
| Span dài nhất | ≤ 10 từ | Dài hơn gần như chắc là lấy nhầm cả mệnh đề |
| Tỷ lệ file có bullet | 60% – 75% | Khớp đề thi |

Script tự kiểm (chạy trước khi giao):

```python
import json, io, glob, os
ew = tw = bad = 0
for jf in glob.glob('output_json/*.json'):
    fid = os.path.basename(jf)[:-5]
    txt = io.open(f'input/{fid}.txt', encoding='utf-8').read()
    tw += len(txt.split())
    for e in json.load(io.open(jf, encoding='utf-8')):
        s, en = e['position']
        ew += len(e['text'].split())
        if txt[s:en] != e['text']:
            bad += 1
            print('LỆCH OFFSET:', fid, repr(e['text']), '!=', repr(txt[s:en]))
print(f'Tỷ lệ từ trong thực thể: {ew/tw*100:.1f}%   (phải nằm trong 8-18%)')
print(f'Lệch offset: {bad}   (phải = 0)')
```

## 2.4. Format file

Giữ **đúng như `dataset2`** (đã chuẩn):

```
dataset/
├── input/
│   ├── doc_000.txt        # văn bản thuần, UTF-8
│   └── ...
└── output_json/
    ├── doc_000.json       # nhãn, cùng tên file
    └── ...
```

**`output_json/doc_000.json`** — là một **MẢNG PHẲNG**:

```json
[
  {
    "text": "đau bụng vùng hạ sườn phải",
    "type": "TRIỆU_CHỨNG",
    "position": [142, 168]
  },
  {
    "text": "viêm dạ dày",
    "type": "CHẨN_ĐOÁN",
    "position": [305, 316]
  }
]
```

**Quy tắc bắt buộc:**

| Trường | Yêu cầu |
|---|---|
| `text` | **Cắt nguyên văn** từ file `.txt`. Phải thoả `raw[position[0]:position[1]] == text` |
| `type` | Đúng 1 trong 5 chuỗi: `TRIỆU_CHỨNG` · `CHẨN_ĐOÁN` · `THUỐC` · `TÊN_XÉT_NGHIỆM` · `KẾT_QUẢ_XÉT_NGHIỆM` (có dấu, IN HOA, gạch dưới) |
| `position` | `[start, end]`, tính bằng **ký tự**, `end` là vị trí sau ký tự cuối |
| Sắp xếp | Theo `position[0]` tăng dần |
| Chồng lấn | **Không được** có 2 thực thể chồng lấn nhau |

Trường `candidates` / `assertions`: **không cần**, để trống hoặc bỏ hẳn.

## 2.5. Mẫu khối bệnh án cấu trúc cần sinh

Đây là **phần quan trọng nhất đang thiếu**. Sinh theo đúng dạng này:

```
2.  Tiền sử bệnh hiện tại
    Lý do nhập viện
    - đau ngực trái cấp tính
    - khó thở khi gắng sức
    Diễn biến bệnh
    - Bệnh nhân đau ngực từ sáng, lan ra sau lưng.
    - Đã dùng nitroglycerin ngậm dưới lưỡi, đỡ ít.
    Đặc điểm triệu chứng
    - Vị trí: sau xương ức
    - Mức độ nghiêm trọng: Không ghi rõ
    Các bệnh lý mạn tính
    - tăng huyết áp
    - đái tháo đường type 2

3.  Đánh giá tại bệnh viện
    Dấu hiệu lâm sàng
    - nhịp tim nhanh
    - huyết áp 150/90 mmHg
    Kết quả xét nghiệm
    - Troponin I: 2.5 ng/mL
    - điện tâm đồ: ST chênh lên V1-V4
    Các thủ thuật đã thực hiện
    - chụp động mạch vành
    - siêu âm tim
    Thuốc trước khi nhập viện
    - aspirin 81mg
    - atorvastatin 20mg
```

**Các heading nên dùng** (lấy từ thống kê đề thi thật, theo tần suất):

```
Đặc điểm triệu chứng          Triệu chứng hiện tại
Các sự kiện trước khi nhập viện   Diễn biến bệnh
Các bệnh lý mạn tính          Kết quả xét nghiệm
Các thủ thuật đã thực hiện    Tiền sử phẫu thuật / thủ thuật
Dấu hiệu lâm sàng             Thuốc trước khi nhập viện
Lý do nhập viện               Thời điểm khởi phát triệu chứng
Triệu chứng khi nhập viện     Kết quả chẩn đoán hình ảnh
Tình trạng ngay trước khi nhập viện
```

**Lưu ý:** giữ cả dòng placeholder `- Mức độ nghiêm trọng: Không ghi rõ` (đề thi có nhiều) — nhưng **KHÔNG gán nhãn** cho `Không ghi rõ`.

## 2.6. Quy tắc gán nhãn — chốt để nhất quán

| Tình huống | Cách làm | Ví dụ |
|---|---|---|
| Lấy **cụm ngắn nhất đủ nghĩa** | Bỏ hoàn cảnh, thời gian, nguyên nhân bao quanh | `"Cảm thấy mệt mỏi nhiều khi gắng sức trong tuần qua"` → gán `mệt mỏi` |
| **Không** dính hư từ ở biên | Bỏ `cho`, `và`, `bị`, `có`, `là`, `các` ở đầu/cuối | `"răng khôn hàm dưới cho mọc lệch"` → `răng khôn hàm dưới mọc lệch` |
| Gán **đều cả 2 phần** | Cả câu hỏi bệnh nhân **và** câu trả lời bác sĩ | xem lỗi `cell_075` ở trên |
| Câu phủ định tiền sử | **Không gán** | `"không có tiền sử về bệnh"` → bỏ qua |
| Liệt kê nhiều thực thể | Tách riêng từng cái | `"Công thức máu, CRP, máu lắng"` → **3** `TÊN_XÉT_NGHIỆM` |
| Tên xét nghiệm vs kết quả | Tên = thứ được đo; Kết quả = giá trị/kết luận | `"Xét nghiệm chức năng gan cho thấy men gan tăng"` → `Xét nghiệm chức năng gan` (TÊN) + `men gan tăng` (KẾT_QUẢ) |
| Thủ thuật/chẩn đoán hình ảnh | Tính là `TÊN_XÉT_NGHIỆM` | `siêu âm tim`, `nội soi dạ dày`, `chụp CT sọ não`, `sinh thiết` |
| Nhóm thuốc | Tính là `THUỐC` | `kháng sinh`, `thuốc giảm đau opioid`, `corticoid` |

---

## Tóm tắt việc cần làm

1. ❌ **Bỏ `data/dataset`** — không sửa được, phải sinh lại từ đầu bằng văn bản thật
2. ✅ **Giữ `dataset2`** làm mẫu chuẩn cho phần văn xuôi
3. 🔴 **Ưu tiên số 1:** sinh khối bệnh án cấu trúc (mục 2.5) — đây là lỗ hổng lớn nhất
4. 🔴 **Ưu tiên số 2:** bơm `THUỐC` / `TÊN_XÉT_NGHIỆM` / `KẾT_QUẢ_XÉT_NGHIỆM` lên 400–600 mẫu mỗi loại
5. 🔴 **Ưu tiên số 3:** gán kỹ hơn, đừng bỏ sót phần bác sĩ trả lời
6. ✅ Chạy script tự kiểm ở mục 2.3 trước khi giao — **tỷ lệ từ trong thực thể phải nằm trong 8–18%**
