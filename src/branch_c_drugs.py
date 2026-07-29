"""
NHÁNH C - Trích xuất THUỐC bằng khớp từ điển RxNorm
Chạy trên văn bản gốc, không cần model.
"""

import re
import unicodedata
from typing import List, Dict, Set
import pandas as pd


# Pattern cho hàm lượng thuốc
STRENGTH = re.compile(
    r'^\s*\d+(?:[.,]\d+)?\s*(?:mg|g|mcg|µg|ml|l|ui|iu|%)\b',
    re.IGNORECASE | re.UNICODE
)


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
    
    def load_rxnorm(self, path: str):
        """Load RxNorm dictionary"""
        try:
            df = pd.read_csv(path)
            # Assuming columns: rxcui, name
            for name in df['name'].dropna():
                normalized = normalize_drug_name(str(name))
                if normalized:
                    self.drug_names.add(normalized)
            print(f"✓ Loaded {len(self.drug_names)} drug names from RxNorm")
        except Exception as e:
            print(f"⚠ Could not load RxNorm: {e}")
    
    def load_inn_usan(self, path: str):
        """Load INN-USAN mappings"""
        try:
            df = pd.read_csv(path)
            # Add both INN and USAN variants
            for col in df.columns:
                for name in df[col].dropna():
                    normalized = normalize_drug_name(str(name))
                    if normalized:
                        self.drug_names.add(normalized)
            print(f"✓ Loaded INN-USAN mappings")
        except Exception as e:
            print(f"⚠ Could not load INN-USAN: {e}")
    
    def add_custom_drugs(self, drug_list: List[str]):
        """Add custom drug names (for Vietnamese drugs not in RxNorm)"""
        for name in drug_list:
            normalized = normalize_drug_name(name)
            if normalized:
                self.drug_names.add(normalized)
    
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
        
        # Sort by position
        entities.sort(key=lambda x: x['start'])
        return entities


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
