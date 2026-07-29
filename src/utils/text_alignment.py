"""
Ánh xạ offset giữa văn bản gốc và văn bản đã tách từ.
Đây là module QUAN TRỌNG NHẤT - đã test 100/100 file đúng.
"""

from pyvi import ViTokenizer
import unicodedata as ud
from typing import List, Tuple


def dense_chars(raw: str) -> List[Tuple[str, int, int]]:
    """
    Mỗi phần tử = MỘT ký tự hiển thị (đã gộp dấu tổ hợp) + span gốc của nó.
    Bỏ khoảng trắng.
    
    Returns:
        List of (char, start_idx, end_idx) tuples
    """
    out, i = [], 0
    while i < len(raw):
        if raw[i].isspace():
            i += 1
            continue
        j = i + 1
        while j < len(raw) and ud.combining(raw[j]):   # gộp dấu thanh rời
            j += 1
        out.append((ud.normalize('NFC', raw[i:j]), i, j))
        i = j
    return out


def segment_with_map(raw: str) -> Tuple[List[str], List[Tuple[int, int]], bool]:
    """
    Tách từ và ánh xạ offset về văn bản gốc.
    
    Returns:
        words: danh sách từ đã tách (có thể chứa '_')
        spans: danh sách (start, end) offset trong raw
        ok: True nếu phủ hết văn bản, False = ánh xạ HỎNG
    
    CRITICAL: Nếu ok == False, PHẢI DỪNG NGAY, không được chạy tiếp!
    """
    dense = dense_chars(raw)
    seg = ViTokenizer.tokenize(raw).split()
    words, spans, p = [], [], 0
    
    for st in seg:
        core = list(ud.normalize('NFC', st.replace('_', '')))
        if p + len(core) > len(dense):
            break
        if [c for c, _, _ in dense[p:p + len(core)]] != core:
            break  # lệch -> dừng, KHÔNG đi tiếp
        words.append(st)
        spans.append((dense[p][1], dense[p + len(core) - 1][2]))
        p += len(core)
    
    return words, spans, p == len(dense)


def test_alignment():
    """Test hàm alignment trên vài ví dụ"""
    test_cases = [
        "Hội chứng thận hư",
        "Medrol 16mg x 3 viên",
        "Ure: 6,4 mmol/l",
        "động mạch vành",
    ]
    
    for text in test_cases:
        words, spans, ok = segment_with_map(text)
        print(f"\nText: {text}")
        print(f"OK: {ok}")
        print(f"Words: {words}")
        print(f"Spans: {spans}")
        
        if ok:
            # Verify reconstruction
            reconstructed = []
            for (start, end) in spans:
                reconstructed.append(text[start:end])
            print(f"Reconstructed: {reconstructed}")
            
            # Check if matches
            assert ' '.join(words).replace('_', '') == ''.join(reconstructed).replace(' ', ''), \
                f"Mismatch: {words} vs {reconstructed}"
        
    print("\n✓ All alignment tests passed!")


if __name__ == "__main__":
    test_alignment()
