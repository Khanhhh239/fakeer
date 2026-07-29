"""
Convert ViMQ dataset từ JSON format sang định dạng thống nhất.
Chỉ giữ nhãn SYMPTOM_AND_DISEASE -> SYM_DIS, còn lại -> O

CRITICAL: ViMQ span indices theo WORD INDEX và BAO GỒM CẢ HAI ĐẦU [i, j]
Phải verify điều này trước khi convert hàng loạt!
"""

import requests
import json
from typing import List


VIMQ_URLS = {
    'train': 'https://raw.githubusercontent.com/tadeephuy/ViMQ/master/data/train.json',
    'dev': 'https://raw.githubusercontent.com/tadeephuy/ViMQ/master/data/dev.json',
    'test': 'https://raw.githubusercontent.com/tadeephuy/ViMQ/master/data/test.json',
}


def download_vimq_file(url: str) -> List[dict]:
    """Download và parse JSON"""
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def verify_vimq_span_convention(examples: List[dict], n_samples: int = 5):
    """
    Verify rằng [i, j] trong ViMQ là BAO GỒM CẢ HAI ĐẦU.
    
    CRITICAL: Nếu hiểu sai convention này, TOÀN BỘ nhãn sẽ lệch 1 từ!
    """
    print("\n" + "="*60)
    print("VERIFYING ViMQ SPAN CONVENTION")
    print("="*60)
    
    for i, ex in enumerate(examples[:n_samples]):
        sentence = ex['sentence']
        tokens = sentence.split()
        
        print(f"\nExample {i+1}: {sentence}")
        
        for start_idx, end_idx, label in ex.get('seq_label', []):
            # Test 1: Inclusive both ends [i:j+1]
            span_inclusive = tokens[start_idx:end_idx+1]
            
            # Test 2: Exclusive end [i:j]
            span_exclusive = tokens[start_idx:end_idx]
            
            print(f"  Label: {label}")
            print(f"  Indices: [{start_idx}, {end_idx}]")
            print(f"  If INCLUSIVE: {' '.join(span_inclusive)}")
            print(f"  If EXCLUSIVE: {' '.join(span_exclusive)}")
        
        # Check for index out of bounds
        for start_idx, end_idx, label in ex.get('seq_label', []):
            if end_idx >= len(tokens):
                print(f"  ⚠ WARNING: end_idx={end_idx} >= len(tokens)={len(tokens)}")
                print(f"     This suggests EXCLUSIVE convention!")
                return False
    
    print("\n" + "="*60)
    print("✓ Convention appears to be INCLUSIVE [i, j]")
    print("  (No index out of bounds errors detected)")
    print("="*60 + "\n")
    
    return True


def convert_vimq_to_bio(example: dict) -> dict:
    """
    Convert một example ViMQ sang BIO format.
    
    Args:
        example: {sentence: str, seq_label: [[start, end, label], ...]}
    
    Returns:
        {tokens: [...], labels: [...], source: 'vimq'}
    """
    sentence = example['sentence']
    tokens = sentence.split()
    labels = ['O'] * len(tokens)
    
    # Process each span
    for start_idx, end_idx, label in example.get('seq_label', []):
        # Only keep SYMPTOM_AND_DISEASE
        if label != 'SYMPTOM_AND_DISEASE':
            continue
        
        # Validate indices
        if start_idx < 0 or end_idx >= len(tokens) or start_idx > end_idx:
            print(f"⚠ Invalid span: [{start_idx}, {end_idx}] for {len(tokens)} tokens")
            continue
        
        # INCLUSIVE convention: [i, j] includes both i and j
        labels[start_idx] = 'B-SYM_DIS'
        for idx in range(start_idx + 1, end_idx + 1):
            labels[idx] = 'I-SYM_DIS'
    
    return {
        'tokens': tokens,
        'labels': labels,
        'source': 'vimq'
    }


def convert_vimq_split(split: str, verify: bool = True) -> List[dict]:
    """
    Convert một split của ViMQ.
    
    Args:
        split: 'train', 'dev', or 'test'
        verify: Verify span convention trước khi convert
    
    Returns:
        List of examples: {tokens: [...], labels: [...]}
    """
    print(f"Downloading ViMQ {split}...")
    url = VIMQ_URLS[split]
    raw_examples = download_vimq_file(url)
    
    print(f"  ✓ Loaded {len(raw_examples)} examples")
    
    # Verify span convention
    if verify and split == 'train':
        is_valid = verify_vimq_span_convention(raw_examples, n_samples=5)
        if not is_valid:
            raise ValueError("⚠ Span convention verification FAILED! Manual check required.")
    
    # Convert to BIO
    print(f"Converting {split} to BIO format...")
    examples = []
    for ex in raw_examples:
        converted = convert_vimq_to_bio(ex)
        examples.append(converted)
    
    # Statistics
    total_entities = sum(1 for ex in examples for l in ex['labels'] if l.startswith('B-'))
    print(f"  ✓ {len(examples)} sentences, {total_entities} SYM_DIS entities")
    
    return examples


def convert_all_vimq():
    """Convert all ViMQ splits"""
    all_data = {}
    
    for split in ['train', 'dev', 'test']:
        all_data[split] = convert_vimq_split(split, verify=(split == 'train'))
    
    return all_data


if __name__ == "__main__":
    data = convert_all_vimq()
    
    # Save to file
    output_path = "data/processed/vimq_converted.json"
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Saved to {output_path}")
    print(f"  Train: {len(data['train'])} examples")
    print(f"  Dev: {len(data['dev'])} examples")
    print(f"  Test: {len(data['test'])} examples")
