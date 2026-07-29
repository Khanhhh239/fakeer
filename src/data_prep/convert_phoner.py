"""
Convert PhoNER_COVID19 dataset từ CoNLL format sang định dạng thống nhất.
Chỉ giữ nhãn SYMPTOM_AND_DISEASE -> SYM_DIS, còn lại -> O
"""

import requests
from typing import List, Tuple
import json


PHONER_URLS = {
    'train': 'https://raw.githubusercontent.com/VinAIResearch/PhoNER_COVID19/main/data/word/train_word.conll',
    'dev': 'https://raw.githubusercontent.com/VinAIResearch/PhoNER_COVID19/main/data/word/dev_word.conll',
    'test': 'https://raw.githubusercontent.com/VinAIResearch/PhoNER_COVID19/main/data/word/test_word.conll',
}


def download_phoner_file(url: str) -> str:
    """Download file từ URL"""
    response = requests.get(url)
    response.raise_for_status()
    return response.text


def parse_conll(content: str) -> List[Tuple[List[str], List[str]]]:
    """
    Parse CoNLL format.
    
    Returns:
        List of (tokens, labels) tuples
    """
    sentences = []
    current_tokens = []
    current_labels = []
    
    for line in content.strip().split('\n'):
        line = line.strip()
        
        if not line:  # Empty line = sentence boundary
            if current_tokens:
                sentences.append((current_tokens, current_labels))
                current_tokens = []
                current_labels = []
        else:
            parts = line.split('\t')
            if len(parts) >= 2:
                token = parts[0]
                label = parts[1]
                current_tokens.append(token)
                current_labels.append(label)
    
    # Don't forget last sentence
    if current_tokens:
        sentences.append((current_tokens, current_labels))
    
    return sentences


def convert_label(label: str) -> str:
    """
    Convert PhoNER label to unified format.
    
    Rules:
    - B-SYMPTOM_AND_DISEASE -> B-SYM_DIS
    - I-SYMPTOM_AND_DISEASE -> I-SYM_DIS
    - Everything else -> O
    """
    if label == 'B-SYMPTOM_AND_DISEASE':
        return 'B-SYM_DIS'
    elif label == 'I-SYMPTOM_AND_DISEASE':
        return 'I-SYM_DIS'
    else:
        return 'O'


def convert_phoner_split(split: str) -> List[dict]:
    """
    Convert một split của PhoNER.
    
    Returns:
        List of examples: {tokens: [...], labels: [...]}
    """
    print(f"Downloading PhoNER {split}...")
    url = PHONER_URLS[split]
    content = download_phoner_file(url)
    
    print(f"Parsing PhoNER {split}...")
    sentences = parse_conll(content)
    
    print(f"Converting labels for {split}...")
    examples = []
    for tokens, labels in sentences:
        converted_labels = [convert_label(l) for l in labels]
        examples.append({
            'tokens': tokens,
            'labels': converted_labels,
            'source': 'phoner'
        })
    
    # Statistics
    total_entities = sum(1 for ex in examples for l in ex['labels'] if l.startswith('B-'))
    print(f"  ✓ {len(examples)} sentences, {total_entities} SYM_DIS entities")
    
    return examples


def convert_all_phoner():
    """Convert all PhoNER splits"""
    all_data = {}
    
    for split in ['train', 'dev', 'test']:
        all_data[split] = convert_phoner_split(split)
    
    return all_data


if __name__ == "__main__":
    data = convert_all_phoner()
    
    # Save to file
    output_path = "data/processed/phoner_converted.json"
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Saved to {output_path}")
    print(f"  Train: {len(data['train'])} examples")
    print(f"  Dev: {len(data['dev'])} examples")
    print(f"  Test: {len(data['test'])} examples")
