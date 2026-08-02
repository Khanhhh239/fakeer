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
    Loc TH: loai ten thuoc bi a.
    - Giu: co trong thuoc_norm_set (RxNorm + nhom thuoc chung)
    - Giu: nhom thuoc chung tieu Viet (khang sinh, corticoid, ...)
    - Loai: ten bi a ro rang (dai > 6 tu, khong tim duoc trong KB)
    Khong loc qua chat -- LLM co the tra ve ten dung nhung khong trong KB.
    """
    _THUOC_CHUNG_NORM = {
        _norm(t) for t in [
            "khang sinh", "thuoc ha sot", "thuoc giam dau", "corticoid",
            "thuoc loi tieu", "thuoc ha ap", "vitamin", "dich truyen",
            "insulin", "thuoc chong dong", "paracetamol", "ibuprofen",
            "amoxicillin", "metformin", "omeprazole", "aspirin",
        ]
    }
    out = []
    for th in th_list:
        t = th.strip()
        if not t or len(t) < 2:
            continue
        norm = _norm(t)
        # Giu neu trong KB hoac nhom thuoc chung
        if norm in thuoc_norm_set or norm in _THUOC_CHUNG_NORM:
            out.append(t)
            continue
        # Giu neu ten ngan (<= 4 tu) -- co the la ten thuoc hop le chua trong KB
        if len(t.split()) <= 4:
            out.append(t)
            continue
        # Loai neu qua dai va khong trong KB
    return out or th_list  # fallback: neu loc het thi giu nguyen


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

Bạn là bác sĩ Việt Nam. Với chẩn đoán được cho, liệt kê các khái niệm y khoa thường đi kèm trong bệnh án.

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
   SAI:  TH|antirôsin, TH|thuốc đặc trị
3. TX phải là TÊN một xét nghiệm/thủ thuật cụ thể.
   ĐÚNG: TX|công thức máu, TX|siêu âm ổ bụng, TX|nội soi dạ dày
   SAI:  TX|Phương pháp chẩn đoán lâm sàng
4. TC phải là điều người bệnh CẢM THẤY hoặc bác sĩ THẤY.
   ĐÚNG: TC|sốt cao, TC|đau vùng thượng vị
   SAI:  TC|Sử dụng miệng lưỡi cắn
5. Mọi mục phải liên quan TRỰC TIẾP tới chẩn đoán.
6. Mỗi mục 1-5 từ, viết như bác sĩ ghi bệnh án.
7. KHÔNG chú thích tên nước ngoài trong ngoặc. SAI: TC|sợ nước (hydrophobia)
8. Viết xong 11 dòng thì DỪNG.

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

BÂY GIỜ LÀM VỚI CHẨN ĐOÁN: "{diagnosis}"

Nhắc lại: chỉ tiếng Việt có dấu. Không chữ Hán. Không tiếng Anh. Không chú thích trong ngoặc."""


def build_t1_prompts(sample_diag: List[Dict], qtok) -> List[str]:
    prompts = []
    for d in sample_diag:
        content = PROMPT_T1.format(diagnosis=d["term"])
        msgs = [{"role": "user", "content": content}]
        p = qtok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        if "/no_think" not in p:
            p += "/no_think\n"
        prompts.append(p)
    return prompts


def parse_t1_batch(outs, sample_diag: List[Dict],
                   thuoc_norm_set: Set[str]) -> List[Dict]:
    """
    Parse T1 outputs + retrieve-validate TH/TX.
    Returns list of {diagnosis: dict, scenario: {tc, th, tx}}.
    """
    scenarios = []
    for d, out in zip(sample_diag, outs):
        tc, th, tx = [], [], []
        for line in out.outputs[0].text.strip().split("\n"):
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
            elif code == "TX":
                tx.append(content)

        # Retrieve-validate
        th_clean = retrieve_validate_th(th[:3], thuoc_norm_set)
        tx_clean = retrieve_validate_tx(tx[:3])

        if len(tc) >= 3:
            scenarios.append({
                "diagnosis": d,
                "scenario": {
                    "tc": tc[:5],
                    "th": th_clean[:3],
                    "tx": tx_clean[:3],
                },
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
Tiêu đề là câu ngắn bình thường. Không dùng dấu ngoặc vuông. Không dùng gạch ngang mô tả lại.

CÁC CỤM SAU PHẢI XUẤT HIỆN NGUYÊN VĂN trong bài, không sửa một chữ:
{danh_sach_cum}

NGOÀI RA, 2 cụm sau CŨNG phải xuất hiện nguyên văn (đưa vào tự nhiên như mọi cụm khác):
{bait_thuoc}
{bait_xetnghiem}
Lưu ý: 2 cụm trên KHÔNG phải thuốc/xét nghiệm thật, chỉ nhắc qua, không dùng làm phần điều trị chính.

QUY TẮC:
- Tổng bài 500 đến 700 từ. Mỗi mục đủ 4 đến 6 câu hoàn chỉnh.
- Mỗi câu mang một thông tin y khoa mới. Cấm lặp ý đã nói.
- Cấm câu trấn an rỗng không kèm thông tin y khoa.
- Cấm viết dạng đối thoại qua lại. Người bệnh chỉ hỏi một lần ở đầu.
- Không dùng gạch đầu dòng trong phần trả lời, viết thành đoạn văn.

QUY TẮC NGÔN NGỮ:
- Tên thuốc quốc tế: omeprazole, amoxicillin, furosemid — GIỮ NGUYÊN tên La-tinh.
- Viết tắt xét nghiệm: CRP, AST, ALT, HbA1c, WBC — GIỮ NGUYÊN.
- Tên bệnh, triệu chứng: LUÔN viết tiếng Việt, KHÔNG chú thích tiếng Anh.
  ĐÚNG: "sốt cao", "viêm dạ dày"   SAI: "sốt cao (fever)", "viêm dạ dày (gastritis)"

Nhắc lại: tiếng Việt có dấu, thuốc/xét nghiệm giữ tên quốc tế, không chữ Hán, không ngoặc vuông."""


def build_t2b_inputs(scenarios: List[Dict], kb: Dict, qtok) -> List[Tuple]:
    """
    Xay dung list (prompt, required_ents, bait_t, bait_x) cho T2B.
    - KHONG them XN random ngoai T1 (S6)
    - Bait duoc loc tranh trung voi entities (S4)
    - 10-12 cum, khong qua 15 (tranh C2)
    """
    am_thuoc    = kb["am_thuoc"]
    am_xetnghiem = kb["am_xetnghiem"]

    inputs = []
    for sc in scenarios:
        s = sc["scenario"]
        diag = sc["diagnosis"]["term"]

        # Build entity list chi tu T1, khong them XN random
        ents = [(diag, "CHAN_DOAN")]
        for t in s["tc"]: ents.append((t, "TRIEU_CHUNG"))
        for t in s["th"]: ents.append((t, "THUOC"))
        for t in s["tx"]: ents.append((t, "TEN_XET_NGHIEM"))
        random.shuffle(ents)
        ents = ents[:12]  # toi da 12 cum, tranh C2

        # Chon bait khong trung voi entities (S4)
        ent_surfaces_lower = {e[0].lower() for e in ents}
        safe_am_t = [x for x in am_thuoc if x.lower() not in ent_surfaces_lower] or am_thuoc
        safe_am_x = [x for x in am_xetnghiem if x.lower() not in ent_surfaces_lower] or am_xetnghiem
        bt = random.choice(safe_am_t)
        bx = random.choice(safe_am_x)

        # Tieu de muc lay tu kịch ban
        tds_pool = [
            f"{diag} là bệnh gì",
            f"Triệu chứng của {diag}",
            f"Nguyên nhân gây {diag}",
            f"Điều trị {diag}",
            f"Phòng ngừa {diag}",
            "Khi nào cần gặp bác sĩ",
        ]
        tds = random.sample(tds_pool, 4)

        danh_sach = "\n".join(f"- {surface}" for surface, _ in ents)
        prompt_text = PROMPT_T2B.format(
            danh_sach_cum=danh_sach,
            bait_thuoc=bt,
            bait_xetnghiem=bx,
            tieu_de_1=tds[0], tieu_de_2=tds[1],
            tieu_de_3=tds[2], tieu_de_4=tds[3],
        )
        msgs = [{"role": "user", "content": prompt_text}]
        p = qtok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        if "/no_think" not in p:
            p += "/no_think\n"

        inputs.append((p, ents, bt, bx))
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
        save_pair(txt_dir, json_dir, saved_start + saved, text_noisy, ents)
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
) -> Tuple[int, Dict]:
    """
    Xu ly ket qua T2B bang BATCH retry -- khong goi LLM tung item.
    Sau moi round: collect tat ca fail, generate lai ca lot mot lan.
    max_retry=2 (tong 3 round: round 0 + 2 retry).
    Returns (n_saved, reject_log).
    """
    texts = [_clean_llm_output(o.outputs[0].text.strip()) for o in t2b_outs]
    total_saved = 0
    total_reject: Dict[str, int] = {}
    current_saved_start = saved_start

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

        # Batch retry: chi sinh lai cac item bi fail, nhiet do cao hon
        failed_inputs = [t2b_inputs[i] for i in failed_idx]
        failed_prompts = [inp[0] for inp in failed_inputs]
        temp = 0.8 + attempt * 0.1
        print(f"  Retry {attempt+1}: {len(failed_prompts)} bai, temp={temp:.1f} -- batch generate...")
        retry_outs = llm.generate(
            failed_prompts,
            SamplingParams(temperature=temp, max_tokens=1100)
        )
        texts = [_clean_llm_output(o.outputs[0].text.strip()) for o in retry_outs]
        t2b_inputs = failed_inputs  # chi xu ly cac fail

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
# Sample diagnoses theo phan tang co trong so (S1 + BANGIAO §10)
# ---------------------------------------------------------------------------

def sample_diagnoses(chandoan_pool: List[Dict], n_per_chapter: int = 5) -> List[Dict]:
    """
    Chon chan doan mau: moi chuong lay n_per_chapter,
    chuong quan trong lay nhieu hon theo _CHAPTER_QUOTA.
    Dam bao phan tang deu khi chay full 500 file.
    """
    from collections import defaultdict
    from synth_source import _CHAPTER_QUOTA
    by_ch = defaultdict(list)
    for d in chandoan_pool:
        by_ch[d["chapter"]].append(d)

    result = []
    for ch, items in by_ch.items():
        quota = _CHAPTER_QUOTA.get(ch, n_per_chapter)
        # Scale xuong khi test nhanh (n_per_chapter nho)
        n = max(1, int(quota * n_per_chapter / 5))
        result.extend(random.sample(items, min(n, len(items))))
    random.shuffle(result)
    return result

