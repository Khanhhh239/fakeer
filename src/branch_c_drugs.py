"""
NHÁNH C - Trích xuất THUỐC bằng khớp từ điển RxNorm
Chạy trên văn bản gốc, không cần model.
"""

import re
import unicodedata
from typing import List, Dict, Set
import pandas as pd


# Hàm lượng thuốc.
# Hai điều kiện, cả hai đều đã sai trong bản trước:
#  1. '%' phải để NGOÀI nhóm có \b — '%' và khoảng trắng đều là ký tự không
#     phải chữ nên \b giữa chúng KHÔNG BAO GIỜ khớp -> "Glucose 5%" bị trượt.
#  2. (?!\s*/) — đơn vị KHÔNG được theo sau bởi '/'. Hàm lượng thuốc là khối
#     lượng đứng một mình ("40 mg x 1 viên"), còn "52 g/l", "103 g/l" là NỒNG ĐỘ
#     xét nghiệm. Thiếu lookahead này thì "Protein 52 g/l" bị bắt thành thuốc.
STRENGTH = re.compile(
    r'^\s*\d+(?:[.,]\d+)?\s*(?:(?:mg|g|mcg|µg|ml|l|ui|iu)\b(?!\s*/)|%)',
    re.IGNORECASE | re.UNICODE
)

# Từ đứng ngay trước hàm lượng phải trông như TÊN THUỐC: bắt đầu bằng chữ,
# không phải từ chức năng hay từ chỉ bối cảnh dùng thuốc.
_NOT_DRUG_WORD = {
    'uống', 'tiêm', 'truyền', 'ngày', 'lần', 'viên', 'ống', 'gói', 'lọ', 'chai',
    'liều', 'sáng', 'chiều', 'tối', 'trưa', 'giờ', 'x', 'và', 'với', 'sau',
    'trước', 'mỗi', 'cho', 'của', 'là', 'có', 'không', 'còn', 'thêm', 'dùng',
    'truyen', 'tinh', 'mach', 'nong', 'do', 'ml', 'mg', 'kg',
}

# Chất vừa là THUỐC vừa là CHỈ SỐ XÉT NGHIỆM. Với các tên này, chỉ nhận là
# thuốc khi có hàm lượng ngay sau (xem extract_drugs). Tên đã chuẩn hoá:
# bỏ dấu + viết thường.
DUAL_USE = {
    'glucose', 'creatinine', 'creatinin', 'prothrombin', 'lactate', 'albumin',
    'urea', 'ure', 'bilirubin', 'cholesterol', 'triglyceride', 'triglycerid',
    'protein', 'hemoglobin', 'ferritin', 'insulin', 'calcium', 'magnesium',
    'potassium', 'sodium', 'phosphate', 'chloride', 'bicarbonate', 'ammonia',
    'lactose', 'fibrinogen', 'transferrin', 'troponin', 'amylase', 'lipase',
}


def normalize_drug_name(name: str) -> str:
    """
    Chuẩn hóa tên thuốc: bỏ dấu, lowercase, bỏ khoảng trắng thừa.
    """
    # Remove accents
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    # Lowercase and strip
    name = name.lower().strip()
    # Normalize whitespace
    name = ' '.join(name.split())
    return name


class DrugMatcher:
    """Khớp tên thuốc từ từ điển RxNorm"""
    
    def __init__(self, rxnorm_path: str = None, inn_usan_path: str = None):
        """
        Args:
            rxnorm_path: Path to rxnorm_merged.csv
            inn_usan_path: Path to inn_usan.csv
        """
        self.drug_names: Set[str] = set()
        self.max_ngram = 5
        
        if rxnorm_path:
            self.load_rxnorm(rxnorm_path)
        if inn_usan_path:
            self.load_inn_usan(inn_usan_path)
    
    # Cột THẬT của rxnorm_merged.csv là 'code','term' (xem kb/README.md).
    # Bản trước đọc df['name'] -> KeyError -> bị `except` nuốt -> từ điển tụt
    # từ 129.690 xuống 68 tên hardcode mà vẫn báo chạy bình thường.
    RXNORM_TERM_COLS = ('term', 'name', 'str', 'STR')

    # Tên quá ngắn hoặc là từ tiếng Anh thông dụng sẽ khớp bừa vào văn bản Việt
    # sau khi bỏ dấu (vd 'co' <- 'có'). Chặn ở đây.
    MIN_NAME_LEN = 4
    _NOT_DRUG_WORD_N = {normalize_drug_name(w) for w in _NOT_DRUG_WORD}
    STOP_NAMES = {
        'water', 'oxygen', 'air', 'oral', 'tablet', 'capsule', 'solution',
        'injection', 'cream', 'gel', 'kit', 'pack', 'unit', 'nam', 'can',
        'chi', 'ban', 'cam', 'tam', 'chan', 'bao', 'chat', 'sinh', 'hoa',
    }

    def _add_name(self, raw: str) -> bool:
        n = normalize_drug_name(str(raw))
        if len(n) < self.MIN_NAME_LEN or n in self.STOP_NAMES:
            return False
        self.drug_names.add(n)
        # Biến thể chính tả Việt/châu Âu: tiếng Việt rụng '-e' cuối.
        #   RxNorm 'furosemide' -> bệnh án viết 'Furosemid'
        #   RxNorm 'amlodipine'  -> 'Amlodipin'
        # Không có dòng này thì thiếu gần hết hoạt chất viết theo kiểu Việt.
        if n.endswith('e') and len(n) - 1 >= self.MIN_NAME_LEN:
            self.drug_names.add(n[:-1])
        return True

    def load_rxnorm(self, path: str):
        """
        Nạp từ điển RxNorm.

        KHÔNG nuốt lỗi: nạp KB thất bại thì dừng hẳn. Chạy tiếp với từ điển
        rỗng nghĩa là nhánh C âm thầm bỏ sót gần hết thuốc mà không ai biết.
        """
        df = pd.read_csv(path)
        col = next((c for c in self.RXNORM_TERM_COLS if c in df.columns), None)
        if col is None:
            raise KeyError(
                f"{path}: không tìm thấy cột tên thuốc. "
                f"Có {list(df.columns)}, cần một trong {self.RXNORM_TERM_COLS}"
            )
        before = len(self.drug_names)
        for name in df[col].dropna():
            self._add_name(name)
        added = len(self.drug_names) - before
        if added < 1000:
            raise RuntimeError(
                f"{path}: chỉ nạp được {added} tên từ cột {col!r} — quá ít, "
                f"gần như chắc chắn sai file hoặc sai cột. Dừng."
            )
        print(f"✓ RxNorm: {added:,} tên (cột {col!r}) / {len(df):,} dòng")

    def load_inn_usan(self, path: str):
        """Nạp cầu nối INN <-> USAN (paracetamol <-> acetaminophen)."""
        df = pd.read_csv(path)
        before = len(self.drug_names)
        for col in df.columns:
            for name in df[col].dropna():
                self._add_name(name)
        print(f"✓ INN-USAN: thêm {len(self.drug_names) - before} tên / {len(df)} cặp")
    
    def add_custom_drugs(self, drug_list: List[str]):
        """
        Thêm thuốc ngoài RxNorm (biệt dược Việt Nam).
        Đi qua _add_name để cũng sinh biến thể rụng '-e' như khi nạp RxNorm.
        """
        for name in drug_list:
            self._add_name(name)
    
    def extract_drugs(self, text: str) -> List[Dict]:
        """
        Trích xuất thuốc từ văn bản.
        
        Strategy:
        1. Scan all n-grams (1-5 words)
        2. Match against dictionary (longest match wins)
        3. Extend with dosage/strength if present
        
        Returns:
            List of entity dicts
        """
        entities = []
        words = []
        word_spans = []
        
        # Tokenize by whitespace, keeping track of positions
        for match in re.finditer(r'\S+', text):
            words.append(match.group())
            word_spans.append((match.start(), match.end()))
        
        if not words:
            return entities
        
        # Track used positions to avoid overlaps
        used_positions = set()
        
        # Scan n-grams from longest to shortest
        for n in range(min(self.max_ngram, len(words)), 0, -1):
            for i in range(len(words) - n + 1):
                # Check if already used
                if any(j in used_positions for j in range(i, i + n)):
                    continue
                
                # Extract n-gram
                ngram_words = words[i:i+n]
                ngram_text = ' '.join(ngram_words)
                ngram_normalized = normalize_drug_name(ngram_text)
                
                # Check if in dictionary
                if ngram_normalized in self.drug_names:
                    start = word_spans[i][0]
                    end = word_spans[i + n - 1][1]

                    tail = text[end:]

                    # Chất VỪA là thuốc VỪA là chỉ số xét nghiệm.
                    # Đã đo trên 100 bệnh án, cùng một từ có cả hai vai:
                    #   "Glucose 5% x 1000ml truyền tĩnh mạch"  -> THUỐC
                    #   "Glucose máu: 13,2 mmol/l"              -> xét nghiệm
                    #   "creatinine 5.7", "Creatinine tăng"     -> xét nghiệm
                    # Nên KHÔNG được chặn cứng bằng danh sách đen. Phân biệt
                    # bằng dấu hiệu duy nhất đáng tin: THUỐC thì có HÀM LƯỢNG
                    # ngay sau tên. Không có hàm lượng thì trả về cho nhánh B /
                    # LLM quyết, còn hơn gán sai type (đề phạt x2).
                    if ngram_normalized in DUAL_USE and not STRENGTH.match(tail):
                        continue

                    # Try to extend with strength/dosage
                    if i + n < len(words):
                        remaining_text = text[end:]
                        strength_match = STRENGTH.match(remaining_text)
                        if strength_match:
                            # Extend span to include strength
                            end = end + strength_match.end()

                    entities.append({
                        'text': text[start:end],
                        'type': 'THUỐC',
                        'start': start,
                        'end': end,
                        'score': 1.0,
                        'source': 'dict'
                    })
                    
                    # Mark as used
                    for j in range(i, i + n):
                        used_positions.add(j)
        
        # --- Thuốc KHÔNG có trong RxNorm (biệt dược Việt Nam / Ấn Độ) ---
        entities += self._find_unknown_drugs(text, words, word_spans, used_positions)

        # Sort by position
        entities.sort(key=lambda x: x['start'])
        return entities

    def _find_unknown_drugs(self, text, words, word_spans, used_positions) -> List[Dict]:
        """
        Bắt thuốc mà từ điển RxNorm không có, bằng CẤU TRÚC thay vì từ điển.

        Vì sao cần: RxNorm là từ điển Mỹ, thiếu biệt dược lưu hành ở Việt Nam.
        Ví dụ đo được trên bệnh án mẫu: 'Omez 20mg' (biệt dược omeprazole của
        Ấn Độ) không có trong 129.690 tên, nên khớp từ điển bỏ sót.

        Dấu hiệu cấu trúc: một từ trông như tên riêng đứng NGAY TRƯỚC hàm lượng.
        Đây là luật tất định, không gọi model, không có nguy cơ bịa.

        Điều kiện chặt để không bắt bừa:
          - từ chưa bị khớp từ điển chiếm
          - ngay sau nó là hàm lượng THẬT (số + khối lượng, không phải nồng độ
            '/l' — nếu không thì 'Protein 52 g/l' sẽ bị bắt thành thuốc)
          - từ bắt đầu bằng chữ cái, không nằm trong danh sách từ chức năng
          - từ không phải chỉ số xét nghiệm quen thuộc (DUAL_USE)
        """
        out = []
        for i, w in enumerate(words):
            if i in used_positions:
                continue
            end = word_spans[i][1]
            if not STRENGTH.match(text[end:]):
                continue

            core = w.strip('.,;:()[]')
            if not core or not core[0].isalpha() or len(core) < 3:
                continue
            n = normalize_drug_name(core)
            if n in self._NOT_DRUG_WORD_N or n in DUAL_USE or n in self.STOP_NAMES:
                continue

            m = STRENGTH.match(text[end:])
            start = word_spans[i][0] + (len(w) - len(w.lstrip('.,;:()[]')))
            out.append({
                'text': text[start:end + m.end()],
                'type': 'THUỐC',
                'start': start,
                'end': end + m.end(),
                'score': 0.7,        # thấp hơn khớp từ điển (1.0)
                'source': 'rule_strength',
            })
            used_positions.add(i)
        return out


def test_branch_c_rules():
    """
    Test luật của nhánh C, KHÔNG cần từ điển thật.
    Mỗi ca nêu rõ kết quả mong đợi nên không thể 'pass rỗng' như bản trước.
    """
    m = DrugMatcher()
    m.add_custom_drugs(['Medrol', 'Furosemide', 'Zestril', 'Glucose', 'Omez'])

    cases = [
        # (văn bản, danh sách span THUỐC mong đợi)
        ("Medrol 16mg x 3 viên, uống 8h sáng sau ăn no", ['Medrol 16mg']),
        ("Furosemid 40 mg x 1 viên, uống sáng", ['Furosemid 40 mg']),  # rụng '-e'
        ("Zestril 10mg x 1 viên", ['Zestril 10mg']),
        # dual-use CÓ hàm lượng -> là thuốc (dấu '%' từng làm regex trượt)
        ("Glucose 5% x 1000ml truyền tĩnh mạch", ['Glucose 5%']),
        # dual-use KHÔNG hàm lượng -> KHÔNG phải thuốc
        ("Glucose máu: 13,2 mmol/l", []),
        ("creatinine 5.7", []),
        ("Thời gian Prothrombin (PT / TQ)", []),
        # thuốc KHÔNG có trong từ điển -> bắt bằng cấu trúc "tên + hàm lượng"
        ("2.        Omez 20mg x 1 viên, uống 8h sáng.", ['Omez 20mg']),
        ("Rocephin 1g tiêm tĩnh mạch", ['Rocephin 1g']),
        # nồng độ xét nghiệm KHÔNG được coi là hàm lượng thuốc
        ("Protein: 52 g/l", []),
        ("Albumin: 20 g/l", []),
        # từ chức năng đứng trước số -> không phải thuốc
        ("uống 500 ml nước mỗi ngày", []),
    ]

    failed = 0
    for text, expect in cases:
        got = [e['text'] for e in m.extract_drugs(text)]
        bad = got != expect
        for e in m.extract_drugs(text):
            if text[e['start']:e['end']] != e['text']:
                bad = True
        print(f"  {'✗' if bad else '✓'} {text[:46]!r:48s} -> {got}"
              + (f"   MONG {expect}" if bad else ""))
        failed += bad

    if failed:
        raise AssertionError(f"Branch C: {failed}/{len(cases)} ca THẤT BẠI")
    print(f"✓ Branch C: {len(cases)}/{len(cases)} ca PASS")


def test_branch_c():
    """Test nhánh C với từ điển giả"""
    # Create mock matcher
    matcher = DrugMatcher()
    
    # Add some common Vietnamese drugs
    common_drugs = [
        "Medrol", "Furosemid", "Paracetamol", "Aspirin",
        "Zestril", "Amoxicillin", "Omeprazole", "Metformin"
    ]
    matcher.add_custom_drugs(common_drugs)
    
    test_cases = [
        "Medrol 16mg x 3 viên, uống 8h sáng",
        "Furosemid 40 mg ngày 1 lần",
        "Paracetamol 500mg khi sốt",
        "Aspirin liều thấp",
    ]
    
    for text in test_cases:
        print(f"\n{'='*60}")
        print(f"Text: {text}")
        entities = matcher.extract_drugs(text)
        
        for ent in entities:
            print(f"  [THUỐC] '{ent['text']}' at ({ent['start']}, {ent['end']})")
            # Verify
            assert text[ent['start']:ent['end']] == ent['text'], \
                f"Offset mismatch: {text[ent['start']:ent['end']]} != {ent['text']}"
    
    print(f"\n{'='*60}")
    print("✓ All Branch C tests passed!")


if __name__ == "__main__":
    test_branch_c()
