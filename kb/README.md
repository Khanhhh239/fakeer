# KB — ICD-10 và RxNorm

Bốn file dưới đây là cơ sở dữ liệu đã dựng sẵn, dùng cho **Nhánh A bậc 1–2** (tách triệu chứng/bệnh)
và **Nhánh C** (khớp tên thuốc) trong `KEHOACH_NER.md`.

Mọi file đều là CSV UTF-8, có dòng tiêu đề.

| file | dòng | khoá duy nhất | cột | dùng ở đâu |
|---|---|---|---|---|
| `icd10_vi_full.csv` | 14.627 | 14.627 mã ICD | `code,term` | Mục 4.3 — thác tách `SYM_DIS` |
| `icd10_en.csv` | 71.704 | 71.704 | `code,term` | Mục 4.3 — **tuỳ chọn**, bí danh tiếng Anh |
| `rxnorm_merged.csv` | 129.690 | **83.320 RxCUI** | `code,term` | Mục 4.5 — từ điển thuốc |
| `inn_usan.csv` | 36 | 36 | `form,usan` | Mục 4.5 — cầu nối INN↔USAN |

## Từng file

### `icd10_vi_full.csv` — ICD-10 tiếng Việt
```
code,term
A00,Bệnh tả
```
Crawl từ `icd.kcb.vn` (Bộ Y tế, TT06/2026). **14.627 mã**: 1.971 mã 3 ký tự + 12.656 mã 4 ký tự.

Crawler dùng duyệt **đệ quy theo tầng**, không phải duyệt phẳng 4 mức. Bản đầu duyệt phẳng đã
**sót nguyên chương C (u bướu)** — chỉ ra 4 mã C, thiếu cả `C50` (ung thư vú) — vì chương u bướu
và chương nguyên nhân ngoại sinh lồng sâu hơn 4 tầng.

**Chương R = "Triệu chứng, dấu hiệu"** — đây là tín hiệu để tách triệu chứng khỏi bệnh (Mục 4.3).
Nhưng chương R **chỉ có 495 tên trên tổng 17.094**, nên nó chỉ dùng được ở vùng nó chắc chắn,
không dùng để phán cho mọi span. Chi tiết và số đo ở Mục 4.3.

### `icd10_en.csv` — bí danh tiếng Anh
```
code,term
A00.0,Cholera due to Vibrio cholerae 01, biovar cholerae
```
Khi trộn vào KB tiếng Việt, hàm `load_icd10(with_en=True)` **không bao giờ tạo mã mới** — bí danh
tiếng Anh chỉ được gắn vào mã đã tồn tại trong bản tiếng Việt, nếu không thì lùi về mã 3 ký tự,
vẫn không có thì bỏ. Giữ nguyên nguyên tắc này nếu viết lại.

### `rxnorm_merged.csv` — từ điển thuốc
```
code,term
1000000,Amlodipine 5 MG / HCTZ 12.5 MG / Olmesartan medoxomil 40 MG Oral Tablet [Tribenzor]
```
**83.320 RxCUI / 129.690 tên.** Hợp nhất từ hai nguồn:
- RxNorm **Prescribable** (bản RRF không cần giấy phép): 60.489 RxCUI / 106.859 tên
- bổ sung từ RxNav

Một RxCUI có nhiều tên (trung bình 1,56) — tên thương mại, tên hoạt chất, dạng bào chế.

### `inn_usan.csv` — cầu nối tên quốc tế ↔ tên Mỹ
```
form,usan
adrenaline,epinephrine
```
36 cặp đã kiểm chứng thủ công. Cần vì RxNorm dùng **USAN** (tên Mỹ) còn tài liệu Việt Nam
thường dùng **INN/BAN** (tên quốc tế): `paracetamol` ↔ `acetaminophen`, `adrenaline` ↔ `epinephrine`.
Không có bảng này thì tra `paracetamol` trong RxNorm sẽ trượt.

## File CỐ Ý không chép sang

| file | lý do |
|---|---|
| `rxnorm_prescribe.csv` | tập con của `rxnorm_merged.csv`, đã gộp rồi |
| `icd10_vi.csv`, `icd10_seed.csv`, `icd10_alias_vi.csv` | bản cũ, đã bị `icd10_vi_full.csv` thay thế |
| `rxnorm_api.csv`, `rxnorm_seed.csv` | bản thử nghiệm ban đầu |
| `data/synth/icd_synth_*.csv` | **bí danh ICD sinh bằng LLM 14B — vi phạm ràng buộc ≤9B tham số.** Muốn dùng phải sinh lại bằng model ≤9B |

## Lưu ý khi dùng RxNav API

Có script gọi API RxNav trong repo gốc. API đó **chỉ được dùng để ĐO/đối chiếu khi phát triển**,
**tuyệt đối không được gọi trong bài nộp** — đề cấm gọi API ngoài lúc chấm.
Mọi thứ cần thiết đã nằm sẵn trong `rxnorm_merged.csv` này.
