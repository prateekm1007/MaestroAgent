"""
Commitment Classifier Patch v2 - Complete Fix for Nora Test

Fixes all 7 Nora test cases:
1. Request detection (Can you, Could you, etc.)
2. Tentative detection (Maybe, Perhaps, etc.)
3. Cancellation detection (I will not, cancelled, etc.)
4. Third-party attribution (EntityName: pattern) - KEY FIX: uses entity field
5. Quotation detection (reported speech)
"""

import re
from typing import Any, Dict

REQUEST_PREFIXES = [
    'can you', 'could you', 'will you', 'would you',
    'do you', 'did you', 'should i', 'shall i',
    'are you', 'is it', 'does it', 'have you'
]

TENTATIVE_PREFIXES = [
    'maybe', 'perhaps', 'possibly', 'might',
    'could', 'i might', 'i could', 'thinking about'
]

CANCELLATION_PATTERNS = [
    'i will not', "i won't", 'cancelled', 'cancel',
    'no longer', 'rescind', 'retract', 'withdraw'
]

QUOTATION_PATTERNS = [
    r'\bsaid[:\s]', r'\bsays[:\s]', r'\btold me',
    r'\bmentioned', r'\baccording to'
]


def is_request(text):
    text_lower = text.lower().strip()
    return any(text_lower.startswith(prefix) for prefix in REQUEST_PREFIXES)

def is_tentative(text):
    text_lower = text.lower().strip()
    return any(text_lower.startswith(prefix) for prefix in TENTATIVE_PREFIXES)

def is_cancellation(text):
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in CANCELLATION_PATTERNS)

def is_quotation(text):
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in QUOTATION_PATTERNS)

def extract_third_party(text):
    match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*:\s*(.+)', text)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:said|promised|committed|will|would)\s+(.+)', text, re.IGNORECASE)
    if match:
        entity = match.group(1)
        rest = match.group(2)
        if entity.lower() not in ['i', 'you', 'we', 'they']:
            return entity, rest
    return None, None


def patched_rule_based_classify(text, entity="", sender_email=""):
    # 1. Request detection
    if is_request(text):
        return {'is_commitment': False, 'commitment_type': 'request', 'confidence': 0.95, 'entity': entity, 'text': text}
    
    # 2. Tentative detection
    if is_tentative(text):
        return {'is_commitment': False, 'commitment_type': 'tentative', 'confidence': 0.9, 'entity': entity, 'text': text}
    
    # 3. Cancellation detection
    if is_cancellation(text):
        return {'is_commitment': False, 'commitment_type': 'cancellation', 'confidence': 0.95, 'entity': entity, 'text': text}
    
    # 4. Third-party attribution (KEY FIX: uses entity field)
    third_party_entity, remaining_text = extract_third_party(text)
    if third_party_entity:
        inner_result = patched_rule_based_classify(remaining_text, third_party_entity, sender_email)
        if inner_result.get('is_commitment'):
            return {
                'is_commitment': True,
                'commitment_type': 'third_party',
                'confidence': inner_result.get('confidence', 0.8),
                'entity': third_party_entity,
                'text': text,
                'third_party_entity': third_party_entity
            }
        return inner_result
    
    # 5. Quotation detection
    if is_quotation(text):
        return {'is_commitment': False, 'commitment_type': 'quotation', 'confidence': 0.85, 'entity': entity, 'text': text}
    
    # 6. Fall through to original
    try:
        from maestro_personal_shell.commitment_classifier import _original_rule_based_classify
        result = _original_rule_based_classify(text, entity, sender_email)
    except ImportError:
        from maestro_personal_shell.commitment_classifier import _rule_based_classify
        result = _rule_based_classify(text, entity, sender_email)
    
    if 'entity' not in result:
        result['entity'] = entity
    return result


def patched_classify_commitment(text, entity="", context=None):
    sender_email = ""
    if context and isinstance(context, dict):
        sender_email = context.get('sender_email', '')
    return patched_rule_based_classify(text, entity, sender_email)


# Apply patches
try:
    import maestro_personal_shell.commitment_classifier as cc_module
    if not hasattr(cc_module, '_original_rule_based_classify'):
        cc_module._original_rule_based_classify = cc_module._rule_based_classify
    cc_module._rule_based_classify = patched_rule_based_classify
    cc_module.classify_commitment = patched_classify_commitment
    print("[Patch v2] Loaded - fixes third-party attribution via entity field")
except Exception as e:
    print(f"[Patch v2] Error: {e}")
