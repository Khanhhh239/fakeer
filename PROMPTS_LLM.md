# 3 prompt LLM dùng trong pipeline sinh data (test bằng Ollama trước khi code)

Tương ứng §3 / §4.1 / §5.1+§6.1 trong `PLAN_SYNTHETIC_DATA_V2.md`. Test bằng "Bệnh dại" theo yêu cầu.

---

## Prompt 1 — Sinh kịch bản ca bệnh (§3, chạy mỗi ca)

**System:**
```
Bạn là bác sĩ Việt Nam. Nhiệm vụ: liệt kê các khái niệm y khoa THƯỜNG ĐI KÈM với một
chẩn đoán cho trước, để dùng làm dữ liệu huấn luyện.

Quy tắc:
- Viết đúng như bác sĩ Việt Nam viết trong bệnh án/tư vấn — ngắn gọn, không giải thích.
- KHÔNG bịa tên thuốc/xét nghiệm không có thật.
- Mỗi dòng một mục, đúng định dạng: MÃ|nội dung
    TC = triệu chứng thường gặp
    TH = thuốc điều trị hoặc dự phòng thường dùng
    TX = xét nghiệm/thủ thuật thường chỉ định
- Sinh 4-6 dòng TC, 2-3 dòng TH, 2-3 dòng TX.
- Không đánh số, không markdown, không giải thích thêm.
```

**User:**
```
Chẩn đoán: Bệnh dại
```

**Kỳ vọng đại khái:**
```
TC|sợ nước
TC|sợ gió
TC|co thắt hầu họng
TC|kích động, tăng động
TC|sốt
TH|vắc xin phòng dại
TH|huyết thanh kháng dại
TX|xét nghiệm kháng thể kháng dại
TX|xét nghiệm PCR phát hiện virus dại
```

**Chú ý khi đọc kết quả:** mọi dòng LLM trả về sẽ được đối chiếu KB (ICD/RxNorm/`xetnghiem_ten.txt`) trước khi dùng — không khớp thì loại, không tin thẳng. Ollama chỉ cần xem nó có bịa lung tung hay bám sát format `MÃ|nội dung` không.

---

## Prompt 2 — Sinh khung bệnh án (§4.1, chạy 1 lần, tạo ngân hàng ~100 khung)

**System:**
```
Bạn giúp tạo KHUNG (template) bệnh án tiếng Việt để dùng nhiều lần. KHUNG gồm các mục
có tiêu đề (heading) và các dòng gạch đầu dòng ĐỂ TRỐNG nội dung, đánh dấu bằng {SLOT}.

Quy tắc:
- Mỗi khung có 3-5 mục (heading), thứ tự có thể khác nhau giữa các khung.
- Heading nằm trong nhóm: triệu chứng hiện tại, bệnh lý mạn tính, kết quả xét nghiệm,
  thủ thuật đã thực hiện, thuốc đang dùng, chẩn đoán hình ảnh, diễn biến bệnh,
  tiền sử phẫu thuật, dấu hiệu lâm sàng.
- Mỗi mục có 2-4 dòng {SLOT}.
- Đa dạng: đổi ký hiệu gạch đầu dòng (-, •, *), đổi mức thụt lề, đổi cách đặt tên heading.
- TUYỆT ĐỐI không điền nội dung y khoa cụ thể nào vào chỗ {SLOT}.
- Xuất đúng 1 khung mỗi lần gọi.
```

**User:**
```
Sinh 1 khung bệnh án khác với khung trước, phong cách khoa nội.
```

**Kỳ vọng đại khái:**
```
2.  Tiền sử bệnh hiện tại
    Triệu chứng hiện tại
    - {SLOT}
    - {SLOT}
    - {SLOT}
    Các bệnh lý mạn tính
    - {SLOT}
    - {SLOT}

3.  Đánh giá tại bệnh viện
    Kết quả xét nghiệm
    • {SLOT}
    • {SLOT}
    Các thủ thuật đã thực hiện
    • {SLOT}
```

**Chú ý khi đọc kết quả:** kiểm 2 điều — (a) hoàn toàn không có chữ y khoa cụ thể nào lọt vào (chỉ có heading + `{SLOT}`), (b) có ≥3 heading và ≥4 `{SLOT}`. Trượt 1 trong 2 thì loại khung, gọi lại.

---

## Prompt 3 — Sinh văn xuôi hỏi-đáp (§5.1, kèm luôn ca âm §6.1)

**System:**
```
Bạn viết đoạn hỏi-đáp y tế tiếng Việt tự nhiên giữa bệnh nhân và bác sĩ, dùng để tạo
dữ liệu huấn luyện NER.

QUY TẮC BẮT BUỘC:
1. Dùng NGUYÊN VĂN, không sửa một chữ, đúng 1 lần, MỌI cụm trong danh sách "BẮT BUỘC DÙNG".
2. Nếu có danh sách "NHẮC TỚI NHƯNG KHÔNG PHẢI BỆNH/THUỐC/XÉT NGHIỆM": dùng nguyên văn
   các cụm đó làm bối cảnh (thói quen, khoa phòng, hành động khám...) — đây KHÔNG phải
   triệu chứng/chẩn đoán/thuốc/xét nghiệm, chỉ là câu chuyện xung quanh.
3. Không nhắc bất kỳ khái niệm y khoa nào khác ngoài 2 danh sách trên.
4. Văn phong: bệnh nhân hỏi (2-4 câu), bác sĩ trả lời (5-8 câu). Không gạch đầu dòng,
   không liệt kê.
5. Độ dài 180-260 từ.
6. Chỉ xuất đoạn văn, không giải thích, không tiêu đề.
```

**User:**
```
BẮT BUỘC DÙNG:
- sợ nước
- co thắt hầu họng
- Bệnh dại
- vắc xin phòng dại

NHẮC TỚI NHƯNG KHÔNG PHẢI BỆNH/THUỐC/XÉT NGHIỆM:
- bị chó cắn
- khoa truyền nhiễm
```

**Chú ý khi đọc kết quả — đây là chỗ dễ thấy Qwen dở nhất khi làm NER nhưng LẠI ổn khi chỉ VIẾT VĂN:**
- Đếm xem 4 cụm bắt buộc có xuất hiện **nguyên văn, đúng 1 lần** không (dò bằng `text.find()`, không đoán)
- Xem nó có **tự thêm** khái niệm y khoa ngoài danh sách không (ví dụ tự bịa thêm "sốt cao", "đau đầu") — đây chính là lý do cần bước quét từ điển ngược ở §5.3
- Xem `bị chó cắn` / `khoa truyền nhiễm` có vô tình bị viết như thể là triệu chứng/thủ thuật không

---

## Cách test nhanh bằng Ollama

```bash
ollama run qwen2.5:7b-instruct
```
Dán System bằng cách để trong dấu `"""` nếu dùng `ollama run model "system: ... user: ..."`, hoặc dùng API:
```bash
curl http://localhost:11434/api/chat -d '{
  "model": "qwen2.5:7b-instruct",
  "messages": [
    {"role": "system", "content": "<dán system prompt>"},
    {"role": "user", "content": "<dán user prompt>"}
  ],
  "stream": false
}'
```

**Điều cần soi khi đọc kết quả test**, theo đúng thứ tự ưu tiên của 3 tầng:
1. Prompt 1: có bịa thuốc/XN không tồn tại không, có bám định dạng `MÃ|nội dung` không
2. Prompt 2: có lọt chữ y khoa cụ thể vào khung không (phải sạch tuyệt đối)
3. Prompt 3: có bỏ sót cụm bắt buộc không, có tự thêm khái niệm ngoài danh sách không — **đây là chỉ số quan trọng nhất**, quyết định tỷ lệ mẫu bị loại ở cổng #4/#5 khi chạy thật
