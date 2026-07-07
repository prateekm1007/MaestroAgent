"""
Multi-Language Support - language detection, translation suggestions,
cultural context.

Phase 18 of the Ambient Intelligence roadmap (Days 124-133, 40 hours).

REALITY CHECK CAVEAT: Build multi-language YES, defer accent-aware STT.
  - Multi-language: Whisper supports 99 languages, 85% accuracy. ACHIEVABLE.
  - Accent-aware: requires 100+ hours per accent. VAPORWARE. DEFERRED.

What it does:
  1. Language detection - detects the spoken language from transcript text
  2. Translation suggestions - suggests translations for the user's
     understanding (NOT auto-translated TO the other party without consent)
  3. Cultural context - surfaces cultural notes ("In Japanese business
     culture, direct 'no' is rare")
  4. Code-switching detection - detects when speakers mix languages

What it does NOT do (killed per reality check):
  - Accent-aware STT (vaporware without massive training data)
  - Auto-translation TO the other party without explicit consent

Ethical guard: translation is for the user's understanding, not for
deceptive fluency. The system never auto-translates the user's speech TO
the other party without consent.

DEEPER dimension: multi-layer intelligence (language + culture + context).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DetectedLanguage(str, Enum):
    """Languages Maestro can detect."""
    ENGLISH = "english"
    SPANISH = "spanish"
    FRENCH = "french"
    GERMAN = "german"
    JAPANESE = "japanese"
    CHINESE = "chinese"
    HINDI = "hindi"
    ARABIC = "arabic"
    PORTUGUESE = "portuguese"
    UNKNOWN = "unknown"


@dataclass
class LanguageDetection:
    """Result of language detection."""
    language: DetectedLanguage
    confidence: float  # 0.0-1.0
    alternative: Optional[DetectedLanguage] = None
    is_code_switching: bool = False
    detected_languages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "language": self.language.value,
            "confidence": round(self.confidence, 2),
            "alternative": self.alternative.value if self.alternative else None,
            "is_code_switching": self.is_code_switching,
            "detected_languages": self.detected_languages,
        }


@dataclass
class TranslationSuggestion:
    """A translation suggestion for the user's understanding."""
    original_text: str
    translated_text: str
    source_language: DetectedLanguage
    target_language: DetectedLanguage
    confidence: float = 0.0
    # P25: denominator = number of translations in calibration set
    calibration_denominator: int = 0

    @property
    def confidence_label(self) -> str:
        """P25: confidence display gate."""
        if self.calibration_denominator < 10:
            return "insufficient calibration history"
        return f"{self.confidence:.0%} ({self.calibration_denominator} samples)"

    def to_dict(self) -> dict:
        return {
            "original_text": self.original_text[:200],
            "translated_text": self.translated_text[:200],
            "source_language": self.source_language.value,
            "target_language": self.target_language.value,
            "confidence": round(self.confidence, 2),
            "confidence_label": self.confidence_label,
            "calibration_denominator": self.calibration_denominator,
        }


@dataclass
class CulturalContextNote:
    """A cultural context note for the user."""
    language: DetectedLanguage
    note: str
    category: str  # "business_etiquette", "communication_style", "decision_making"
    source: str = "cultural_context_database"

    def to_dict(self) -> dict:
        return {
            "language": self.language.value,
            "note": self.note,
            "category": self.category,
            "source": self.source,
        }


class MultiLanguageSupport:
    """
    Multi-language support engine.

    REALITY CHECK: multi-language YES, accent-aware NO.
    Uses simple keyword/character-set detection (no Whisper model needed
    for the detection layer; Whisper handles the actual STT in Phase 2).

    Usage:
        engine = MultiLanguageSupport()
        detection = engine.detect_language("Konnichiwa, we should discuss the pricing")
        print(f"Language: {detection.language.value}, code-switching: {detection.is_code_switching}")

        translation = engine.suggest_translation("Hola, como estas?", DetectedLanguage.SPANISH)
        print(f"Translation: {translation.translated_text}")

        notes = engine.get_cultural_context(DetectedLanguage.JAPANESE)
    """

    # Language detection patterns
    # Character set detection (CJK, Arabic, Devanagari)
    CJK_PATTERN = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")  # Japanese + Chinese
    HIRAGANA_PATTERN = re.compile(r"[\u3040-\u309f]")  # Japanese hiragana
    KATAKANA_PATTERN = re.compile(r"[\u30a0-\u30ff]")  # Japanese katakana
    CHINESE_ONLY_PATTERN = re.compile(r"[\u4e00-\u9fff]")
    ARABIC_PATTERN = re.compile(r"[\u0600-\u06ff]")
    DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097f]")  # Hindi

    # Latin-script language keywords (for languages using Latin alphabet)
    LANGUAGE_KEYWORDS = {
        DetectedLanguage.SPANISH: ["hola", "gracias", "por favor", "buenos", "si", "no", "que", "como", "donde", "cuando", "porque", "para", "con", "sin"],
        DetectedLanguage.FRENCH: ["bonjour", "merci", "sil vous plat", "oui", "non", "que", "comment", "o", "quand", "pourquoi", "pour", "avec", "sans", "cest"],
        DetectedLanguage.GERMAN: ["hallo", "danke", "bitte", "ja", "nein", "was", "wie", "wo", "wann", "warum", "fr", "mit", "ohne", "nicht", "ist"],
        DetectedLanguage.PORTUGUESE: ["ol", "obrigado", "por favor", "sim", "no", "que", "como", "onde", "quando", "porque", "para", "com", "sem"],
        DetectedLanguage.ENGLISH: ["hello", "thank", "please", "yes", "no", "what", "how", "where", "when", "why", "for", "with", "without", "the", "is"],
    }

    # Common code-switching patterns (non-English words in English context)
    CODE_SWITCH_MARKERS = {
        "hindi": ["jugaad", "achha", "thik", "namaste", "theek"],
        "spanish": ["amigo", "fiesta", "si", "gracias", "bueno"],
        "japanese": ["san", "sensei", "konnichiwa", "arigatou", "sayonara"],
        "french": ["bonjour", "merci", "cest", "voil", "entre"],
    }

    # Cultural context database
    CULTURAL_NOTES = {
        DetectedLanguage.JAPANESE: [
            CulturalContextNote(
                language=DetectedLanguage.JAPANESE,
                note="In Japanese business culture, a direct 'no' is rare. Listen for 'chotto' (a little) or 'kento shimasu' (we'll consider it) as soft declines.",
                category="communication_style",
            ),
            CulturalContextNote(
                language=DetectedLanguage.JAPANESE,
                note="Business cards (meishi) are exchanged with both hands and a slight bow. Treat received cards with respect.",
                category="business_etiquette",
            ),
            CulturalContextNote(
                language=DetectedLanguage.JAPANESE,
                note="Decisions are often made by consensus (nemawashi) before the formal meeting. The meeting confirms, not decides.",
                category="decision_making",
            ),
        ],
        DetectedLanguage.CHINESE: [
            CulturalContextNote(
                language=DetectedLanguage.CHINESE,
                note="In Chinese business culture, building relationship (guanxi) comes before business. Expect social conversation first.",
                category="business_etiquette",
            ),
            CulturalContextNote(
                language=DetectedLanguage.CHINESE,
                note="Indirect communication is preferred. 'We'll study this' may mean 'no' without saying it directly.",
                category="communication_style",
            ),
        ],
        DetectedLanguage.HINDI: [
            CulturalContextNote(
                language=DetectedLanguage.HINDI,
                note="Code-switching between Hindi and English (Hinglish) is common in Indian business settings. This is normal, not impolite.",
                category="communication_style",
            ),
            CulturalContextNote(
                language=DetectedLanguage.HINDI,
                note="Head nodding (the 'Indian head bob') can mean yes, no, or maybe depending on context. Don't assume it means agreement.",
                category="communication_style",
            ),
        ],
        DetectedLanguage.ARABIC: [
            CulturalContextNote(
                language=DetectedLanguage.ARABIC,
                note="In Arabic business culture, personal relationships and trust (wasta) are critical. Expect multiple meetings before decisions.",
                category="business_etiquette",
            ),
            CulturalContextNote(
                language=DetectedLanguage.ARABIC,
                note="Inshallah (God willing) is used for future commitments. It doesn't always mean a firm commitment — confirm timelines explicitly.",
                category="decision_making",
            ),
        ],
        DetectedLanguage.FRENCH: [
            CulturalContextNote(
                language=DetectedLanguage.FRENCH,
                note="In French business culture, direct debate and intellectual challenge are expected. Disagreement is not disrespect.",
                category="communication_style",
            ),
        ],
        DetectedLanguage.GERMAN: [
            CulturalContextNote(
                language=DetectedLanguage.GERMAN,
                note="In German business culture, punctuality and directness are valued. Be on time and state your position clearly.",
                category="business_etiquette",
            ),
        ],
        DetectedLanguage.SPANISH: [
            CulturalContextNote(
                language=DetectedLanguage.SPANISH,
                note="In many Spanish-speaking cultures, personal relationships are valued before business. Expect social conversation before getting to business.",
                category="business_etiquette",
            ),
        ],
    }

    # Simple translation dictionary (for demo; production uses Whisper/DeepL/Google Translate)
    TRANSLATION_DICT = {
        DetectedLanguage.SPANISH: {
            "hola": "hello",
            "gracias": "thank you",
            "por favor": "please",
            "si": "yes",
            "no": "no",
            "buenos dias": "good morning",
            "como estas": "how are you",
            "precio": "price",
            "contrato": "contract",
            "reunion": "meeting",
        },
        DetectedLanguage.FRENCH: {
            "bonjour": "hello",
            "merci": "thank you",
            "oui": "yes",
            "non": "no",
            "prix": "price",
            "contrat": "contract",
            "runion": "meeting",
        },
        DetectedLanguage.GERMAN: {
            "hallo": "hello",
            "danke": "thank you",
            "ja": "yes",
            "nein": "no",
            "preis": "price",
            "vertrag": "contract",
            "besprechung": "meeting",
        },
        DetectedLanguage.JAPANESE: {
            "konnichiwa": "hello",
            "arigatou": "thank you",
            "hai": "yes",
            "iie": "no",
            "nedan": "price",
            "keiyaku": "contract",
            "kaigi": "meeting",
        },
        DetectedLanguage.HINDI: {
            "namaste": "hello",
            "dhanyavad": "thank you",
            "haan": "yes",
            "nahi": "no",
            "daam": "price",
            "anubandh": "contract",
            "baithak": "meeting",
        },
    }

    # Accent-aware STT status (reality check: DEFERRED)
    ACCENT_AWARE_STT_AVAILABLE = False

    def __init__(self):
        self._calibration_count: int = 0

    def record_translation_for_calibration(self) -> None:
        """Record a translation for calibration (P25 denominator)."""
        self._calibration_count += 1

    def detect_language(self, text: str) -> LanguageDetection:
        """Detect the language of the given text.

        Uses character-set detection for non-Latin scripts and keyword
        matching for Latin-script languages. Also detects code-switching.
        """
        if not text or not text.strip():
            return LanguageDetection(
                language=DetectedLanguage.UNKNOWN,
                confidence=0.0,
            )

        text_lower = text.lower()

        # 1. Check non-Latin character sets (high confidence)
        if self.CJK_PATTERN.search(text):
            # Distinguish Japanese (has hiragana/katakana) from Chinese (only hanzi)
            if self.HIRAGANA_PATTERN.search(text) or self.KATAKANA_PATTERN.search(text):
                return LanguageDetection(
                    language=DetectedLanguage.JAPANESE,
                    confidence=0.95,
                )
            else:
                return LanguageDetection(
                    language=DetectedLanguage.CHINESE,
                    confidence=0.90,
                )

        if self.ARABIC_PATTERN.search(text):
            return LanguageDetection(
                language=DetectedLanguage.ARABIC,
                confidence=0.95,
            )

        if self.DEVANAGARI_PATTERN.search(text):
            return LanguageDetection(
                language=DetectedLanguage.HINDI,
                confidence=0.95,
            )

        # 2. Check Latin-script languages via keyword matching
        scores: dict[DetectedLanguage, int] = {}
        for lang, keywords in self.LANGUAGE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[lang] = score

        if not scores:
            return LanguageDetection(
                language=DetectedLanguage.UNKNOWN,
                confidence=0.0,
            )

        # Sort by score
        sorted_langs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_lang = sorted_langs[0][0]
        best_score = sorted_langs[0][1]
        total_score = sum(s for _, s in sorted_langs)

        confidence = min(0.9, best_score / 10 + 0.3)  # scale to 0-0.9
        alternative = sorted_langs[1][0] if len(sorted_langs) > 1 else None

        # 3. Check for code-switching (non-English markers in English context)
        is_code_switching = False
        detected_languages = [best_lang.value]

        if best_lang == DetectedLanguage.ENGLISH:
            for foreign_lang, markers in self.CODE_SWITCH_MARKERS.items():
                if any(m in text_lower for m in markers):
                    is_code_switching = True
                    if foreign_lang not in detected_languages:
                        detected_languages.append(foreign_lang)

        return LanguageDetection(
            language=best_lang,
            confidence=confidence,
            alternative=alternative,
            is_code_switching=is_code_switching,
            detected_languages=detected_languages,
        )

    def suggest_translation(
        self,
        text: str,
        source_language: DetectedLanguage,
        target_language: DetectedLanguage = DetectedLanguage.ENGLISH,
    ) -> TranslationSuggestion:
        """Suggest a translation for the user's understanding.

        Ethical guard: translation is for the USER's understanding, NOT
        for auto-translating TO the other party without consent.
        """
        if source_language == target_language:
            return TranslationSuggestion(
                original_text=text,
                translated_text=text,
                source_language=source_language,
                target_language=target_language,
                confidence=1.0,
                calibration_denominator=self._calibration_count,
            )

        # Use the simple dictionary for common words/phrases
        trans_dict = self.TRANSLATION_DICT.get(source_language, {})
        text_lower = text.lower()

        # Word-by-word translation (simplified; production uses Whisper/DeepL)
        words = text_lower.split()
        translated_words = []
        for word in words:
            # Clean punctuation
            clean_word = re.sub(r"[^\w\s]", "", word)
            translated = trans_dict.get(clean_word)
            if translated:
                translated_words.append(translated)
            else:
                translated_words.append(word)  # keep original if no translation

        translated_text = " ".join(translated_words)

        # Confidence: higher if more words were translated
        total_words = len(words)
        translated_count = sum(1 for w in words if re.sub(r"[^\w\s]", "", w.lower()) in trans_dict)
        confidence = translated_count / total_words if total_words > 0 else 0.0

        return TranslationSuggestion(
            original_text=text,
            translated_text=translated_text,
            source_language=source_language,
            target_language=target_language,
            confidence=confidence,
            calibration_denominator=self._calibration_count,
        )

    def get_cultural_context(self, language: DetectedLanguage) -> list[CulturalContextNote]:
        """Get cultural context notes for the detected language.

        Surfaces notes like: "In Japanese business culture, direct 'no'
        is rare. Listen for 'chotto' as a soft decline."
        """
        return self.CULTURAL_NOTES.get(language, [])

    def is_accent_aware_stt_available(self) -> bool:
        """Check if accent-aware STT is available.

        REALITY CHECK: Always returns False. Accent-aware STT is DEFERRED
        (requires 100+ hours per accent — vaporware without massive data).
        """
        return self.ACCENT_AWARE_STT_AVAILABLE

    def get_accent_aware_stt_status(self) -> str:
        """Get the status of accent-aware STT (for honest disclosure).

        Returns a clear message explaining WHY accent-aware STT is deferred.
        """
        return (
            "Accent-aware STT is DEFERRED. It requires 100+ hours of training "
            "data per accent (Indian English, British English, Nigerian English, "
            "etc.). This data is not available. Multi-language STT (Whisper, 99 "
            "languages, 85% accuracy) IS available and built. Accent-aware is "
            "vaporware without massive data collection. Per the reality check: "
            "build multi-language, defer accent-aware."
        )
