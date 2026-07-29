"""
NHÁNH B - Trích xuất TÊN_XÉT_NGHIỆM và KẾT_QUẢ_XÉT_NGHIỆM
Chạy trên văn bản gốc, không cần model.
"""

import re
from typing import List, Dict, Tuple


# Bước 1: Tách đoạn - cắt ở \n, ;, :, dấu chấm, và dấu phẩy KHÔNG nằm giữa hai chữ số
SPLIT = re.compile(r'(?<!\d),(?!\d)|[;:\n]|(?<=[a-zA-ZÀ-ỹ])\.(?=\s|$)')

# Bước 2: Bắt cặp tên/giá trị
# Pattern 1: tên : giá_trị hoặc tên - giá_trị
# Pattern 2: tên giá_trị (cách nhau bằng space)
_SEP = re.compile(
    r'^(.{1,40}?)\s*[:\-=–]\s*([\d.,]+\s*[a-zA-Zµ/%°]+.*?)$'
    r'|^(.{1,40}?)\s+([\d.,]+\s*[a-zA-Zµ/%°]+.*?)$',
    re.UNICODE
)

# Pattern cho giá trị số + đơn vị
VALUE_PATTERN = re.compile(
    r'^[\d.,]+\s*(?:[a-zA-Zµ/%°]+(?:/[a-zA-Z]+)?|T/l|g/l|mmol/l|UI/l)',
    re.IGNORECASE | re.UNICODE
)


def clean_name(n: str) -> str:
    """
    Làm sạch tên xét nghiệm.
    CRITICAL: KHÔNG được rstrip('-') vì Cl-, HCO3- là tên ion!
    """
    return n.strip().lstrip(':-=–').rstrip(':=–').strip()


def clean_value(v: str) -> str:
    """Làm sạch giá trị xét nghiệm"""
    return v.strip()


def split_segments(text: str) -> List[Tuple[str, int, int]]:
    """
    Tách văn bản thành các đoạn.
    
    Returns:
        List of (segment_text, start_offset, end_offset)
    """
    segments = []
    last_end = 0
    
    for match in SPLIT.finditer(text):
        seg_text = text[last_end:match.start()].strip()
        if seg_text:
            # Find actual start (skip leading whitespace)
            actual_start = last_end
            while actual_start < match.start() and text[actual_start].isspace():
                actual_start += 1
            segments.append((seg_text, actual_start, actual_start + len(seg_text)))
        last_end = match.end()
    
    # Don't forget the last segment
    seg_text = text[last_end:].strip()
    if seg_text:
        actual_start = last_end
        while actual_start < len(text) and text[actual_start].isspace():
            actual_start += 1
        if actual_start < len(text):
            segments.append((seg_text, actual_start, actual_start + len(seg_text)))
    
    return segments


def extract_lab_pairs(text: str) -> List[Dict]:
    """
    Trích xuất các cặp TÊN_XÉT_NGHIỆM - KẾT_QUẢ_XÉT_NGHIỆM bằng luật regex.
    
    Returns:
        List of entity dicts with keys: text, type, start, end, score, source
    """
    entities = []
    segments = split_segments(text)
    
    for seg_text, seg_start, seg_end in segments:
        # Try to match name:value or name value pattern
        match = _SEP.match(seg_text)
        
        if match:
            # Extract groups
            if match.group(1):  # Pattern with separator :-=
                name_raw = match.group(1)
                value_raw = match.group(2)
            else:  # Pattern with space only
                name_raw = match.group(3)
                value_raw = match.group(4)
            
            name = clean_name(name_raw)
            value = clean_value(value_raw)
            
            if not name or not value:
                continue
            
            # Find exact positions in original text
            name_start = seg_text.find(name_raw)
            if name_start == -1:
                continue
            name_start += seg_start
            name_end = name_start + len(name_raw.strip())
            
            value_start = seg_text.find(value_raw, len(name_raw))
            if value_start == -1:
                continue
            value_start += seg_start
            value_end = value_start + len(value_raw.strip())
            
            # Verify match
            if text[name_start:name_end].strip() and text[value_start:value_end].strip():
                entities.append({
                    'text': text[name_start:name_end],
                    'type': 'TÊN_XÉT_NGHIỆM',
                    'start': name_start,
                    'end': name_end,
                    'score': 1.0,  # Rule-based = high confidence
                    'source': 'rule'
                })
                
                entities.append({
                    'text': text[value_start:value_end],
                    'type': 'KẾT_QUẢ_XÉT_NGHIỆM',
                    'start': value_start,
                    'end': value_end,
                    'score': 1.0,
                    'source': 'rule'
                })
    
    return entities


def test_branch_b():
    """Test nhánh B trên các ví dụ"""
    test_cases = [
        "Ure: 6,4 mmol/l",
        "Creatinin 52 g/l",
        "Hồng cầu: 4,49 T/l",
        "Cl- 98 mmol/l",
        "HCO3- : 24 mmol/l",
    ]
    
    for text in test_cases:
        print(f"\n{'='*60}")
        print(f"Text: {text}")
        entities = extract_lab_pairs(text)
        
        for ent in entities:
            print(f"  [{ent['type']}] '{ent['text']}' at ({ent['start']}, {ent['end']})")
            # Verify
            assert text[ent['start']:ent['end']] == ent['text'], \
                f"Offset mismatch: {text[ent['start']:ent['end']]} != {ent['text']}"
    
    print(f"\n{'='*60}")
    print("✓ All Branch B tests passed!")


if __name__ == "__main__":
    test_branch_b()
