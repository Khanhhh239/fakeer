"""
synth_pipeline.py -- Logic trung tam cho sinh data NER tong hop (BANGIAO §3-§6).

Notebook chi goi cac ham nay, khong chua logic.

Ham chinh:
  build_kb(kb_dir)                      -> dict chua cac pool KB
  build_t1_prompts(scenarios, qtok)     -> list[str]
  parse_t1_batch(outs)                  -> list[dict]
  build_t2b_inputs(scenarios, kb, qtok) -> list[(prompt, req, bt, bx)]
  apply_noise(text, entities)           -> (text_noisy, entities_unchanged)
  save_pair(txt_dir, json_dir, idx, text, entities) -> None
  zip_output(out_dir, zip_path)         -> None
  retrieve_validate_tx(tx_list, xn_set) -> list[str]  loc TX khong hop le
  retrieve_validate_th(th_list, thuoc_set) -> list[str]
"""

import os, re, json, random, unicodedata, zipfile
from typing import List, Dict, Tuple, Optional, Set

# ---------------------------------------------------------------------------
# Retrieve-validate sets (build once, reuse)
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normalize: bo dau, lowercase, strip."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


# Tu T1 sinh TX (ten xet nghiem), LLM hay tra ve cac cum khong phai XN:
# "noi soi", "sieu am", "chup X-quang" -- day la thu thuat/chan doan hinh anh,
# khong phai xet nghiem. Nhung theo BANGIAO §1.3: NER khong can khop KB,
# "noi soi", "sieu am" van la thuc the DUNG. Nen KHONG loai chung o day.
# Chi loai cac cum ro rang la MO TA HANH DONG, khong phai ten:
_TX_BLACKLIST_RE = re.compile(
    r"^(phuong phap|quan sat|theo doi|danh gia lam sang|"
    r"kham lam sang|thuc hien|tien hanh|lay mau|ghi nhan)",
    re.IGNORECASE,
)

def retrieve_validate_tx(tx_list: List[str]) -> List[str]:
    """
    Loc TX: giu lai cac ten XN/thu thuat hop le.
    - Loai: mo ta hanh dong (khong phai ten)
    - Giu: "noi soi", "sieu am", "cong thuc mau", bat ky ten cu the
    """
    out = []
    for tx in tx_list:
        t = tx.strip()
        if not t or len(t) < 3:
            continue
        norm = _norm(t)
        if _TX_BLACKLIST_RE.match(norm):
            continue
        # Loai neu qua dai (>8 tu) va khong co ten cu the -- thuong la mo ta
        words = t.split()
        if len(words) > 8:
            continue
        out.append(t)
    return out


def retrieve_validate_th(th_list: List[str], thuoc_norm_set: Set[str]) -> List[str]:
    """
    Loc TH: loai thuoc chung chung va thuoc khong khop RxNorm.
    - Loai: nhom thuoc mo ho ("thuoc dac tri", "thuoc uong", ten > 4 tu khong khop KB)
    - Giu: khop RxNorm fuzzy >= 0.72 HOAC la ten hoat chat ngan <= 3 tu
    """
    from difflib import SequenceMatcher

    # Nhom thuoc CHUNG CHUNG -> loai (model se bija ra nhung tu nay)
    _LOAI_CHUNG = {
        "thuoc dac tri", "thuoc uong", "thuoc tiem", "thuoc bo",
        "thuoc nam", "thuoc dong y", "thuoc ha sot", "thuoc giam dau",
        "thuoc khang viem", "thuoc tang cuong", "thuoc boi ngoai da",
        "thuoc dat", "thuoc nho mat", "thuoc nho tai",
        "antibiotic",  # tieng Anh -> loai
        "nhu tuong codein",  # bịa
    }

    # Nhom hop le du khong trong RxNorm (linkable=False theo bàn giao)
    _THUOC_CHUNG_OK = {
        _norm(t) for t in [
            "kháng sinh", "corticoid", "vitamin", "dịch truyền", "insulin",
            "paracetamol", "ibuprofen", "aspirin", "amoxicillin", "metformin",
            "omeprazole", "furosemid", "furosemide", "atorvastatin",
            "thuốc lợi tiểu", "thuốc hạ áp", "thuốc chống đông",
            "thuốc an thần", "thuốc chống nôn", "thuốc đái tháo đường",
            "thuốc giãn phế quản", "thuốc trị nấm", "thuốc chống dị ứng",
            "kháng histamin", "thuốc ức chế bơm proton", "thuốc kháng acid",
            "thuốc ho", "thuốc long đờm", "statin", "thuốc chống lao",
            "thuốc kháng virus", "thuốc sốt rét", "thuốc chống động kinh",
            "thuốc chống trầm cảm", "thuốc chống loạn thần",
        ]
    }

    out = []
    for th in th_list:
        t = th.strip()
        if not t or len(t) < 2:
            continue
        n = _norm(t)

        # Loai nhom chung chung
        if n in _LOAI_CHUNG:
            continue
        if len(t.split()) > 5:
            continue  # ten qua dai, thuong la mo ta

        # Giu neu trong nhom ok
        if n in _THUOC_CHUNG_OK:
            out.append(t)
            continue

        # Giu neu khop RxNorm fuzzy >= 0.72
        if n in thuoc_norm_set:
            out.append(t)
            continue
        # Fuzzy check (chi check neu <= 3 tu de nhanh)
        if len(t.split()) <= 3:
            best = max(
                (SequenceMatcher(None, n, c).ratio() for c in thuoc_norm_set
                 if abs(len(n) - len(c)) < 4),
                default=0.0
            )
            if best >= 0.72:
                out.append(t)
                continue

        # Ten ngan (<= 2 tu) chua xac dinh -> giu (tranh loai nham)
        if len(t.split()) <= 2:
            out.append(t)

    return out or th_list[:2]  # fallback neu loc het


# ---------------------------------------------------------------------------
# KB loader
# ---------------------------------------------------------------------------

def build_kb(kb_dir: str) -> Dict:
    """
    Nap toan bo KB can dung trong pipeline.
    Tra ve dict de notebook co the in kich thuoc kiem tra.
    """
    def _txt(name):
        with open(os.path.join(kb_dir, name), encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]

    import sys, csv
    from synth_source import load_chandoan, load_trieuchung, load_thuoc

    chandoan_pool  = load_chandoan()
    trieuchung_pool = load_trieuchung()
    thuoc_pool     = load_thuoc()
    xn_names       = _txt("xetnghiem_ten.txt")
    am_thuoc       = _txt("am_thuoc_gia.txt")
    am_xetnghiem   = _txt("am_xetnghiem_gia.txt")
    heading_ls     = _txt("heading_lamsang.txt")
    heading_hd     = _txt("heading_hoidap.txt")

    # Build normalize sets for retrieve-validate
    thuoc_norm_set = {_norm(t["term"]) for t in thuoc_pool}
    am_thuoc_set   = {s.lower() for s in am_thuoc}
    am_xn_set      = {s.lower() for s in am_xetnghiem}

    return dict(
        chandoan_pool=chandoan_pool,
        trieuchung_pool=trieuchung_pool,
        thuoc_pool=thuoc_pool,
        xn_names=xn_names,
        am_thuoc=am_thuoc,
        am_xetnghiem=am_xetnghiem,
        heading_ls=heading_ls,
        heading_hd=heading_hd,
        thuoc_norm_set=thuoc_norm_set,
        am_thuoc_set=am_thuoc_set,
        am_xn_set=am_xn_set,
    )


# ---------------------------------------------------------------------------
# T1 prompts (dung prompt tieng Viet co dau, co vi du day du - BANGIAO §3.2)
# ---------------------------------------------------------------------------

PROMPT_T1 = """CHỈ TRẢ LỜI BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc, tiếng Anh.

Bạn là bác sĩ Việt Nam. Với chẩn đoán được cho, liệt kê các khái niệm y khoa thường đi kèm.

ĐỊNH DẠNG: mỗi dòng một mục, đúng dạng MÃ|nội dung
  TC = triệu chứng người bệnh cảm nhận hoặc bác sĩ quan sát được
  TH = tên thuốc điều trị (tên hoạt chất hoặc nhóm thuốc)

SỐ LƯỢNG: 5 dòng TC, 5 dòng TH. Tổng đúng 10 dòng.

QUY TẮC:
1. Chỉ ghi TÊN, không ghi động từ đi kèm.
   ĐÚNG: TH|amoxicillin        SAI: TH|Tiêm amoxicillin
2. TH phải là tên thuốc CÓ THẬT. Không bịa. Ưu tiên tên hoạt chất quốc tế.
   ĐÚNG: TH|paracetamol, TH|kháng sinh, TH|corticoid, TH|omeprazole, TH|metformin
   SAI:  TH|antirôsin, TH|thuốc đặc trị
3. TC phải là điều người bệnh CẢM THẤY hoặc bác sĩ THẤY.
   ĐÚNG: TC|sốt cao, TC|đau vùng thượng vị, TC|mệt mỏi
   SAI:  TC|Sử dụng miệng lưỡi cắn
4. Mọi mục phải liên quan TRỰC TIẾP tới chẩn đoán.
5. Mỗi mục 1-5 từ, viết như bác sĩ ghi bệnh án.
6. KHÔNG chú thích tên nước ngoài trong ngoặc.
7. Viết xong 10 dòng thì DỪNG.

VÍ DỤ — chẩn đoán "Viêm dạ dày":
TC|đau vùng thượng vị
TC|ợ chua
TC|buồn nôn
TC|đầy bụng sau ăn
TC|chán ăn
TH|omeprazole
TH|thuốc trung hoà acid
TH|amoxicillin
TH|kháng sinh
TH|thuốc giảm đau

BÂY GIỜ LÀM VỚI CHẨN ĐOÁN: "{diagnosis}"

Nhắc lại: chỉ tiếng Việt có dấu. Không chữ Hán. Không tiếng Anh. Không ngoặc."""


def build_t1_prompts(sample_diag: List[Dict], qtok=None) -> List[str]:
    """qtok=None khi dung Ollama (khong can tokenizer)."""
    prompts = []
    for d in sample_diag:
        content = PROMPT_T1.format(diagnosis=d["term"])
        if qtok is not None:
            msgs = [{"role": "user", "content": content}]
            p = qtok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            if "/no_think" not in p:
                p += "/no_think\n"
        else:
            p = content  # Ollama nhan raw prompt
        prompts.append(p)
    return prompts


def parse_t1_batch(outs, sample_diag: List[Dict],
                   thuoc_norm_set: Set[str]) -> List[Dict]:
    """Parse T1 outputs -- chi lay TC + TH, khong lay TX."""
    scenarios = []
    for d, out in zip(sample_diag, outs):
        # Ho tro ca vllm output object lan string (Ollama)
        text = out.outputs[0].text.strip() if hasattr(out, "outputs") else str(out).strip()
        tc, th = [], []
        for line in text.split("\n"):
            line = line.strip()
            if "|" not in line:
                continue
            code, _, content = line.partition("|")
            code = code.strip().upper()
            content = content.strip()
            if not content or len(content) < 2:
                continue
            if code == "TC":
                tc.append(content)
            elif code == "TH":
                th.append(content)

        th_clean = retrieve_validate_th(th[:5], thuoc_norm_set)
        if len(tc) >= 3:
            scenarios.append({
                "diagnosis": d,
                "scenario": {"tc": tc[:5], "th": th_clean[:5]},
            })
    return scenarios


# ---------------------------------------------------------------------------
# T2B prompt (day du theo BANGIAO §3.4)
# ---------------------------------------------------------------------------

PROMPT_T2B = """CHỈ VIẾT BẰNG TIẾNG VIỆT. Không dùng chữ Hán, chữ Trung Quốc. Được phép dùng thuật ngữ y khoa chuẩn viết bằng chữ La-tinh (tên thuốc quốc tế, viết tắt xét nghiệm như CRP, HbA1c).

Bạn là biên tập viên chuyên mục tư vấn sức khoẻ của một trang web y tế Việt Nam.
Viết MỘT BÀI tư vấn hoàn chỉnh.

Bài gồm đúng các phần sau, viết liền mạch:

Câu hỏi từ người dùng:
(4 đến 6 câu, người bệnh tự kể: hoàn cảnh, khó chịu ra sao, lo lắng gì, rồi hỏi)

Câu trả lời của bác sĩ:
Chào bạn,
1. {tieu_de_1}
(4 đến 6 câu văn xuôi liên tục, không dùng gạch đầu dòng)
2. {tieu_de_2}
(4 đến 6 câu)
3. {tieu_de_3}
(4 đến 6 câu)
4. {tieu_de_4}
(4 đến 6 câu)
Trân trọng!

CÁCH VIẾT TIÊU ĐỀ MỤC:
ĐÚNG: 1. Bệnh dại là bệnh gì
SAI:  1. [Bệnh này là gì] — giải thích:
Tiêu đề là câu ngắn bình thường. Không dùng dấu ngoặc vuông.

CÁC CỤM SAU PHẢI XUẤT HIỆN NGUYÊN VĂN trong bài, không sửa một chữ:
{danh_sach_cum}

YÊU CẦU NỘI DUNG BẮT BUỘC — đưa tự nhiên vào bài, không đánh dấu:
{context_am}

QUY TẮC:
- Tổng bài 500 đến 700 từ. Mỗi mục đủ 4 đến 6 câu hoàn chỉnh.
- Mỗi câu mang một thông tin y khoa mới. Cấm lặp ý đã nói.
- Cấm câu trấn an rỗng không kèm thông tin y khoa.
- Cấm viết dạng đối thoại qua lại. Người bệnh chỉ hỏi một lần ở đầu.
- Không dùng gạch đầu dòng trong phần trả lời, viết thành đoạn văn.
- Mô phỏng lỗi gõ bệnh án thật: dính liền {n_glue} chỗ (bỏ dấu cách), chèn *** {n_mask} chỗ.
  Chỉ áp dụng ở phần văn xuôi, KHÔNG đụng vào các cụm bắt buộc ở trên.

QUY TẮC NGÔN NGỮ:
- Tên thuốc quốc tế: omeprazole, amoxicillin, furosemid — GIỮ NGUYÊN tên La-tinh.
- Viết tắt xét nghiệm: CRP, AST, ALT, HbA1c, WBC — GIỮ NGUYÊN.
- Tên bệnh, triệu chứng: LUÔN viết tiếng Việt, KHÔNG chú thích tiếng Anh.

Nhắc lại: tiếng Việt có dấu, thuốc/xét nghiệm giữ tên quốc tế, không chữ Hán, không ngoặc vuông."""


def build_t2b_inputs(scenarios: List[Dict], kb: Dict, qtok=None) -> List[Tuple]:
    """
    Xay dung inputs cho T2B.
    - TC + TH (da validate) lay tu T1
    - TEN_XET_NGHIEM: random 0-5 tu xetnghiem_ten.txt (KB chinh xac) -> vao required
    - Thuoc am + XN am: xuat hien trong van ban nhung KHONG vao required (ca am)
    - context_am: yeu cau sinh ca phu dinh / tien su gia dinh / tien su ca nhan
    - n_glue / n_mask: nhieu dua vao prompt
    """
    xn_names  = kb["xn_names"]
    am_thuoc  = kb["am_thuoc"]
    am_xn     = kb["am_xetnghiem"]

    # Context am pools
    _PHU_DINH = [
        "Người bệnh phủ nhận không bị {tc}.",
        "Không ghi nhận {tc} tại thời điểm khám.",
        "Tiền sử không có {tc}.",
    ]
    _GIA_DINH = [
        "Gia đình có người thân mắc bệnh tương tự.",
        "Bố/mẹ có tiền sử bệnh lý tim mạch.",
        "Có yếu tố di truyền trong gia đình.",
        "Anh chị em ruột không có bệnh lý tương tự.",
    ]
    _TIEN_SU = [
        "Bệnh nhân có tiền sử dị ứng thuốc.",
        "Tiền sử phẫu thuật không có gì đặc biệt.",
        "Không có tiền sử bệnh mãn tính.",
        "Đã từng điều trị bệnh lý khác trước đây.",
    ]

    inputs = []
    for sc in scenarios:
        s   = sc["scenario"]
        diag = sc["diagnosis"]["term"]

        # required entities
        ents = [(diag, "CHAN_DOAN")]
        for t in s["tc"]: ents.append((t, "TRIEU_CHUNG"))
        for t in s["th"]: ents.append((t, "THUOC"))

        # Inject 0-5 XN chinh xac tu KB
        n_xn = random.randint(0, 5)
        if n_xn > 0:
            for xn in random.sample(xn_names, min(n_xn, len(xn_names))):
                ents.append((xn, "TEN_XET_NGHIEM"))

        random.shuffle(ents)
        ents = ents[:14]

        # Thuoc am + XN am -> chi them vao danh sach cum (van ban), KHONG vao required
        n_am_t = random.randint(1, 2)
        n_am_x = random.randint(1, 2)
        am_t_chosen = random.sample(am_thuoc, min(n_am_t, len(am_thuoc)))
        am_x_chosen = random.sample(am_xn, min(n_am_x, len(am_xn)))

        # Danh sach cum = required + am (am chi xuat hien trong van ban, khong gan nhan)
        cum_lines = [f"- {surface}" for surface, _ in ents]
        cum_lines += [f"- {x}  (nhắc qua, không phải thuốc/xét nghiệm chính)" for x in am_t_chosen]
        cum_lines += [f"- {x}  (nhắc qua, không phải thuốc/xét nghiệm chính)" for x in am_x_chosen]
        danh_sach = "\n".join(cum_lines)

        # Context am: random chon 1-3 loai
        ctx_parts = []
        if random.random() < 0.6 and s["tc"]:
            tc_sample = random.choice(s["tc"])
            ctx_parts.append(random.choice(_PHU_DINH).format(tc=tc_sample))
        if random.random() < 0.5:
            ctx_parts.append(random.choice(_GIA_DINH))
        if random.random() < 0.5:
            ctx_parts.append(random.choice(_TIEN_SU))
        context_am = ("Trong bài cần đề cập tự nhiên:\n" +
                      "\n".join(f"- {c}" for c in ctx_parts)) if ctx_parts else ""

        n_glue = random.randint(1, 4)
        n_mask = random.randint(0, 2)

        tds_pool = [
            f"{diag} là bệnh gì",
            f"Triệu chứng của {diag}",
            f"Nguyên nhân gây {diag}",
            f"Điều trị {diag}",
            f"Phòng ngừa {diag}",
            "Khi nào cần gặp bác sĩ",
            f"Tiên lượng của {diag}",
        ]
        tds = random.sample(tds_pool, 4)

        prompt_text = PROMPT_T2B.format(
            danh_sach_cum=danh_sach,
            context_am=context_am,
            n_glue=n_glue, n_mask=n_mask,
            tieu_de_1=tds[0], tieu_de_2=tds[1],
            tieu_de_3=tds[2], tieu_de_4=tds[3],
        )

        if qtok is not None:
            msgs = [{"role": "user", "content": prompt_text}]
            p = qtok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            if "/no_think" not in p:
                p += "/no_think\n"
        else:
            p = prompt_text

        inputs.append((p, ents, "", ""))
    return inputs


# ---------------------------------------------------------------------------
# Noise injection bằng CODE (S7 - BANGIAO §3.4/§8.1)
# Noise duoc ap dung SAU khi LLM tra ve, KHONG lam hong entities da neo
# ---------------------------------------------------------------------------

def apply_noise(text: str, entities: List[Dict]) -> str:
    """
    Ap dung noise: glue (bo dau cach) va mask (thay bang ***).
    CHI ap dung vao vung van ban NGOAI cac entity span.
    Entity spans khong bi cham den.

    Returns: text da them noise (entities giu nguyen vi offset van dung sau noise
    chi ap dung o vung ngoai entity).

    Luu y: vi glue co the lam lech offset, ham nay CHI su dung o dang DISPLAY
    hoac khi luu text file. Entities da co offset tu truoc khi noise.
    De giu invariant offset, apply_noise chi duoc goi SAU khi anchor_all da chay.
    """
    if not text:
        return text

    # Xay dung mask: danh dau vi tri thuoc entity
    in_entity = bytearray(len(text))
    for e in entities:
        s, en = e["position"][0], e["position"][1]
        for i in range(s, min(en, len(text))):
            in_entity[i] = 1

    # Tim cac vi tri dau cach NGOAI entity co the glue
    # Them dieu kien: ca 2 ky tu xung quanh phai la chu, khong phai dau cach khac
    # Va phai cach entity it nhat 5 ky tu de tranh lech offset gay loi neo
    entity_ranges = [(e["position"][0], e["position"][1]) for e in entities]

    def _near_entity(pos, margin=5):
        for s, en in entity_ranges:
            if s - margin <= pos <= en + margin:
                return True
        return False

    space_positions = [
        i for i, c in enumerate(text)
        if c == " "
        and not in_entity[i]
        and i > 0 and text[i-1].isalpha()
        and i < len(text)-1 and text[i+1].isalpha()
        and not _near_entity(i)
    ]

    # Noise: chi ap dung sau entity cuoi cung de khong lech offset entity nao
    # (text truoc entity dau tien va giua cac entity bi glue se lech offset)
    # Giai phap don gian nhat: chi glue/mask PHAN VAN BAN SAU entity cuoi cung
    last_end = max((e["position"][1] for e in entities), default=0) if entities else 0
    safe_space_positions = [p for p in space_positions if p > last_end]

    n_glue = random.randint(1, min(3, max(1, len(safe_space_positions))))
    glue_positions = set(random.sample(safe_space_positions, min(n_glue, len(safe_space_positions)))) if safe_space_positions else set()

    chars = list(text)
    for pos in glue_positions:
        chars[pos] = ""
    text_noisy = "".join(chars)

    # Mask: chi ap dung sau last_end trong text_noisy
    n_mask = random.randint(0, 2)
    if n_mask > 0:
        # Tim offset last_end trong text_noisy (co the lech nhe do glue)
        # Don gian: tim trong phan text sau last_end
        suffix_start = last_end  # xap xi, co the lech 1-2 ky tu do glue
        suffix = text_noisy[suffix_start:]
        word_matches = list(re.finditer(r'[A-Za-zÀ-ỹ]{5,}', suffix))
        if word_matches:
            to_mask = random.sample(word_matches, min(n_mask, len(word_matches)))
            for m in sorted(to_mask, key=lambda x: -x.start()):
                abs_start = suffix_start + m.start()
                abs_end   = suffix_start + m.end()
                text_noisy = text_noisy[:abs_start] + "***" + text_noisy[abs_end:]

    return text_noisy


# ---------------------------------------------------------------------------
# Save + zip
# ---------------------------------------------------------------------------

def save_pair(txt_dir: str, json_dir: str, idx: int,
              text: str, entities: List[Dict]) -> None:
    """Luu text va label vao file rieng, danh so 4 chu so."""
    fname = f"{idx:04d}"
    with open(os.path.join(txt_dir, f"{fname}.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    out_ents = [{"text": e["text"], "type": e["type"],
                 "position": e["position"]} for e in entities]
    with open(os.path.join(json_dir, f"{fname}.json"), "w", encoding="utf-8") as f:
        json.dump(out_ents, f, ensure_ascii=False, indent=2)


def zip_output(base_dir: str, zip_path: str) -> None:
    """
    Nen toan bo base_dir (chua input/ va label/) thanh zip.
    base_dir/
      input/0001.txt ...
      label/0001.json ...
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_dir):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                arcname = os.path.relpath(full, os.path.dirname(base_dir))
                zf.write(full, arcname)
    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"ZIP: {zip_path} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Process T2B outputs: anchor + validate + BATCH retry (khong retry tung item)
# ---------------------------------------------------------------------------

def _clean_llm_output(text: str) -> str:
    """
    Lam sach output LLM truoc khi anchor:
    1. Strip <think>...</think> tags (Qwen3 thinking tokens ro ra)
    2. Strip markdown bold **...** -> giu noi dung
    3. Strip markdown heading ## -> giu text
    """
    import re
    # Boc think block (co the nhieu dong)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Strip ** bold (giu noi dung)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # Strip ## headings
    text = re.sub(r'^#{1,4}\s+', '', text, flags=re.MULTILINE)
    return text.strip()


def _try_save_batch(texts: List[str], t2b_inputs: List[Tuple],
                    kb: Dict, txt_dir: str, json_dir: str,
                    saved_start: int) -> Tuple[int, Dict, List[int]]:
    """
    Thu anchor+validate cho 1 lot texts.
    Returns (n_saved, reject_counts, failed_indices).
    failed_indices: cac index can retry.
    """
    from synth_anchor import anchor_all, validate_document

    am_thuoc     = kb["am_thuoc"]
    am_xetnghiem = kb["am_xetnghiem"]

    saved = 0
    reject_counts: Dict[str, int] = {}
    failed_idx: List[int] = []

    for i, (text, (_, req, bait_t, bait_x)) in enumerate(zip(texts, t2b_inputs)):
        text = _clean_llm_output(text)
        if not text:
            reject_counts["empty"] = reject_counts.get("empty", 0) + 1
            failed_idx.append(i)
            continue

        ents = anchor_all(text, req, bait=[bait_t, bait_x])
        if ents is None:
            reject_counts["anchor<60%"] = reject_counts.get("anchor<60%", 0) + 1
            failed_idx.append(i)
            continue

        ok, reason = validate_document(
            text, ents,
            bait_thuoc=bait_t, bait_xetnghiem=bait_x,
            am_thuoc=am_thuoc, am_xetnghiem=am_xetnghiem,
        )
        if not ok:
            gate = reason.split("]")[0].lstrip("[")
            reject_counts[gate] = reject_counts.get(gate, 0) + 1
            failed_idx.append(i)
            continue

        text_noisy = apply_noise(text, ents)
        # Fuzzy filter: loai entity khong khop KB
        ents_filtered = fuzzy_filter_entities(
            ents, kb["thuoc_pool"], kb["xn_names"]
        )
        save_pair(txt_dir, json_dir, saved_start + saved, text_noisy, ents_filtered)
        saved += 1

    return saved, reject_counts, failed_idx


def process_t2b_outputs(
    t2b_outs,
    t2b_inputs: List[Tuple],
    kb: Dict,
    llm,
    qtok,
    SamplingParams,
    txt_dir: str,
    json_dir: str,
    saved_start: int = 1,
    max_retry: int = 2,
    target: int = 0,          # neu > 0: tiep tuc sinh them cho den khi du
) -> Tuple[int, Dict]:
    """
    Xu ly ket qua T2B bang BATCH retry.
    Neu target > 0: sau khi het retry, neu van chua du target thi
    sinh them bang cach resample tu scenarios, lap lai cho den du.
    """
    texts = [_clean_llm_output(o.outputs[0].text.strip()) for o in t2b_outs]
    total_saved = 0
    total_reject: Dict[str, int] = {}
    current_saved_start = saved_start
    # Giu lai inputs goc de co the resample
    original_inputs = list(t2b_inputs)

    for attempt in range(max_retry + 1):
        saved, reject_counts, failed_idx = _try_save_batch(
            texts, t2b_inputs, kb, txt_dir, json_dir, current_saved_start
        )
        total_saved += saved
        current_saved_start += saved
        for k, v in reject_counts.items():
            total_reject[k] = total_reject.get(k, 0) + v

        print(f"  Round {attempt}: luu {saved}, fail {len(failed_idx)}: {reject_counts}")

        if not failed_idx or attempt == max_retry:
            break

        failed_inputs = [t2b_inputs[i] for i in failed_idx]
        failed_prompts = [inp[0] for inp in failed_inputs]
        temp = 0.8 + attempt * 0.1
        print(f"  Retry {attempt+1}: {len(failed_prompts)} bai, temp={temp:.1f}...")
        retry_outs = llm.generate(
            failed_prompts,
            SamplingParams(temperature=temp, max_tokens=1100)
        )
        texts = [_clean_llm_output(o.outputs[0].text.strip()) for o in retry_outs]
        t2b_inputs = failed_inputs

    # Neu van chua du target: bao cao thieu, khong resample (tranh trung lap benh)
    if target > 0 and total_saved < target:
        print(f"  WARNING: chi luu duoc {total_saved}/{target} file T2B.")
        print(f"  Tang N_TARGET hoac giam reject rate bang cach chinh prompt.")

    return total_saved, total_reject


# ---------------------------------------------------------------------------
# T2A save (struct blocks)
# ---------------------------------------------------------------------------

def process_t2a_blocks(blocks, txt_dir: str, json_dir: str,
                        saved_start: int = 1) -> int:
    saved = 0
    for text, ents in blocks:
        ok = all(text[e["position"][0]:e["position"][1]] == e["text"]
                 for e in ents)
        if not ok:
            continue
        save_pair(txt_dir, json_dir, saved_start + saved, text, ents)
        saved += 1
    return saved


# ---------------------------------------------------------------------------
# Merge T2B + T2A thanh 1 file (60% file theo yeu cau)
# Van ban: T2B truoc, xuong dong, T2A sau.
# Offset T2A duoc cong them len(t2b_text) + separator.
# ---------------------------------------------------------------------------

def merge_and_save(
    t2b_text: str, t2b_ents: List[Dict],
    t2a_text: str, t2a_ents: List[Dict],
    txt_dir: str, json_dir: str, idx: int,
) -> bool:
    """
    Noi t2b_text + separator + t2a_text.
    Shift offset cua t2a_ents theo do dai phan dau.
    Kiem bat bien truoc khi luu.
    Returns True neu luu thanh cong.
    """
    sep = "\n\n"
    merged_text = t2b_text + sep + t2a_text
    offset = len(t2b_text) + len(sep)

    merged_ents = list(t2b_ents)
    for e in t2a_ents:
        new_e = {
            "text": e["text"],
            "type": e["type"],
            "position": [e["position"][0] + offset, e["position"][1] + offset],
        }
        merged_ents.append(new_e)

    # Kiem bat bien
    for e in merged_ents:
        s, en = e["position"][0], e["position"][1]
        if merged_text[s:en] != e["text"]:
            return False

    # Kiem khong chong lan
    merged_ents.sort(key=lambda x: x["position"][0])
    for a, b in zip(merged_ents, merged_ents[1:]):
        if a["position"][1] > b["position"][0]:
            return False

    # Kich thuoc hop le: 1500-6000 ky tu (merge nen cho phep lon hon T2B don)
    if not (1500 <= len(merged_text) <= 6000):
        return False

    save_pair(txt_dir, json_dir, idx, merged_text, merged_ents)
    return True


def process_mixed_blocks(
    t2b_saved_texts: List[str],  # text T2B da qua anchor+validate
    t2b_saved_ents: List[List[Dict]],
    blocks: List[Tuple],          # T2A blocks tu build_blocks
    txt_dir: str,
    json_dir: str,
    saved_start: int,
    merge_ratio: float = 0.6,
) -> Tuple[int, int]:
    """
    Xu ly T2A blocks:
    - merge_ratio (60%): merge voi T2B tuong ung -> 1 file lon
    - phan con lai (40%): luu T2A rieng le

    Tra ve (n_merged, n_standalone).
    """
    n_t2b = len(t2b_saved_texts)
    n_blocks = len(blocks)
    n_merge = int(n_blocks * merge_ratio)

    # Xao tron blocks de phan phoi deu
    indices = list(range(n_blocks))
    random.shuffle(indices)
    merge_idx  = set(indices[:n_merge])
    alone_idx  = set(indices[n_merge:])

    current_idx = saved_start
    n_merged = 0
    n_standalone = 0

    # Pool T2B texts de merge (xoay vong neu it hon blocks)
    t2b_pool = list(zip(t2b_saved_texts, t2b_saved_ents))

    for i, (t2a_text, t2a_ents) in enumerate(blocks):
        # Kiem bat bien T2A
        ok = all(t2a_text[e["position"][0]:e["position"][1]] == e["text"]
                 for e in t2a_ents)
        if not ok:
            continue

        if i in merge_idx and t2b_pool:
            # Lay T2B tuong ung (mod de khong out of range)
            t2b_text, t2b_ents = t2b_pool[n_merged % len(t2b_pool)]
            if merge_and_save(t2b_text, t2b_ents, t2a_text, t2a_ents,
                              txt_dir, json_dir, current_idx):
                current_idx += 1
                n_merged += 1
            else:
                # Fallback: luu T2A rieng neu merge that bai
                save_pair(txt_dir, json_dir, current_idx, t2a_text, t2a_ents)
                current_idx += 1
                n_standalone += 1
        else:
            save_pair(txt_dir, json_dir, current_idx, t2a_text, t2a_ents)
            current_idx += 1
            n_standalone += 1

    return n_merged, n_standalone

# ---------------------------------------------------------------------------
# Sample diagnoses theo phan tang co trong so (S1 + BANGIAO §10)
# ---------------------------------------------------------------------------

def sample_diagnoses(chandoan_pool: List[Dict], n_needed: int) -> List[Dict]:
    """
    Chon n_needed chan doan KHONG LAP tu pool, dam bao moi chuong co dai dien.
    Neu n_needed > len(pool) thi lay het pool (khong the co nhieu hon).
    Phan tang theo trong so chuong truoc, lay them ngau nhien neu chua du.
    """
    from collections import defaultdict
    from synth_source import _CHAPTER_QUOTA

    by_ch = defaultdict(list)
    for d in chandoan_pool:
        by_ch[d["chapter"]].append(d)

    # Buoc 1: lay theo quota co trong so de dam bao dai dien
    selected = []
    selected_set = set()
    total_quota = sum(_CHAPTER_QUOTA.get(ch, 30) for ch in by_ch)

    for ch, items in by_ch.items():
        quota = _CHAPTER_QUOTA.get(ch, 30)
        # Scale theo ti le: chuong co trong so cao lay nhieu hon
        n = max(1, int(n_needed * quota / total_quota))
        take = random.sample(items, min(n, len(items)))
        for d in take:
            key = d["code"]
            if key not in selected_set:
                selected.append(d)
                selected_set.add(key)

    # Buoc 2: neu chua du, lay them tu phan con lai (ngau nhien, khong lap)
    if len(selected) < n_needed:
        remaining = [d for d in chandoan_pool if d["code"] not in selected_set]
        random.shuffle(remaining)
        for d in remaining:
            if len(selected) >= n_needed:
                break
            selected.append(d)
            selected_set.add(d["code"])

    random.shuffle(selected)
    n_actual = min(len(selected), n_needed)
    return selected[:n_actual]


# ---------------------------------------------------------------------------
# Fuzzy filter: loai entity khong khop KB
# ---------------------------------------------------------------------------

def _fuzzy_best(text: str, candidates: List[str], threshold: float = 0.70) -> float:
    """Tra ve ratio cao nhat khi so text voi tat ca candidates."""
    from difflib import SequenceMatcher
    n = _norm(text)
    best = 0.0
    for c in candidates:
        r = SequenceMatcher(None, n, _norm(c)).ratio()
        if r > best:
            best = r
        if best >= threshold:
            break
    return best


def fuzzy_filter_entities(
    entities: List[Dict],
    thuoc_pool: List[Dict],
    xn_names: List[str],
    thuoc_threshold: float = 0.72,
    xn_threshold: float = 0.75,
) -> List[Dict]:
    """
    Loai THUOC khong khop rxnorm va loai TEN_XET_NGHIEM khong khop xetnghiem_ten.txt.
    TRIEU_CHUNG va CHAN_DOAN giu nguyen (khong can khop KB theo BANGIAO §1.3).
    KET_QUA_XET_NGHIEM giu nguyen (sinh bang luat, luon dung).
    """
    thuoc_terms = [t["term"] for t in thuoc_pool]
    # Them nhom thuoc chung (linkable=False) -- luon giu
    _CHUNG_NORM = {
        _norm(t) for t in [
            "kháng sinh", "corticoid", "thuốc hạ sốt", "thuốc giảm đau",
            "paracetamol", "ibuprofen", "vitamin", "dịch truyền",
            "insulin", "metformin", "omeprazole", "aspirin", "amoxicillin",
        ]
    }

    kept = []
    for e in entities:
        etype = e["type"]

        if etype in ("TRIEU_CHUNG", "CHAN_DOAN", "KET_QUA_XET_NGHIEM"):
            kept.append(e)
            continue

        if etype == "THUOC":
            # Giu neu la nhom thuoc chung
            if _norm(e["text"]) in _CHUNG_NORM:
                kept.append(e)
                continue
            score = _fuzzy_best(e["text"], thuoc_terms, thuoc_threshold)
            if score >= thuoc_threshold:
                kept.append(e)
            # else: loai

        elif etype == "TEN_XET_NGHIEM":
            score = _fuzzy_best(e["text"], xn_names, xn_threshold)
            if score >= xn_threshold:
                kept.append(e)
            # else: loai

        else:
            kept.append(e)  # loai la khac -> giu

    return kept


# ---------------------------------------------------------------------------
# Ollama support -- test local voi qwen2.5:8b
# ---------------------------------------------------------------------------

def ollama_generate_batch(prompts: List[str], model: str = "qwen2.5:8b",
                          temperature: float = 0.7, max_tokens: int = 1100) -> List[str]:
    """
    Goi Ollama API (localhost:11434) theo batch tuan tu.
    Tra ve list[str] text output tuong ung.
    """
    import urllib.request
    import json as _json

    url = "http://localhost:11434/api/generate"
    results = []
    for i, prompt in enumerate(prompts):
        payload = _json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = _json.loads(resp.read())
                results.append(data.get("response", ""))
        except Exception as ex:
            print(f"  Ollama error prompt {i}: {ex}")
            results.append("")
        if (i + 1) % 10 == 0:
            print(f"  Ollama: {i+1}/{len(prompts)} done")
    return results


class _OllamaOut:
    """Wrapper de compatible voi vllm output object."""
    def __init__(self, text):
        self.outputs = [type("o", (), {"text": text})()]


def ollama_generate(prompts: List[str], model: str = "qwen2.5:8b",
                    temperature: float = 0.7, max_tokens: int = 1100):
    """Tra ve list gia lap vllm output de dung chung ham process_t2b_outputs."""
    texts = ollama_generate_batch(prompts, model, temperature, max_tokens)
    return [_OllamaOut(t) for t in texts]
