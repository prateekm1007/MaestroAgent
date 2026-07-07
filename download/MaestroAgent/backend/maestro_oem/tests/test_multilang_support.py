"""Phase 18 - Multi-Language Support tests.

Tests language detection, translation suggestions, cultural context,
code-switching detection, and the accent-aware STT DEFERRED status.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


class TestMultiLanguageSupport:
    """Phase 18: MultiLanguageSupport."""

    def _make_engine(self):
        from maestro_oem.multilang_support import MultiLanguageSupport
        return MultiLanguageSupport()

    def test_english_detection(self):
        """English is detected from common English words."""
        engine = self._make_engine()
        detection = engine.detect_language("Hello, thank you for the meeting. How are you?")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.ENGLISH
        assert detection.confidence > 0

    def test_spanish_detection(self):
        """Spanish is detected from common Spanish words."""
        engine = self._make_engine()
        detection = engine.detect_language("Hola, gracias por la reunion. Como estas?")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.SPANISH

    def test_french_detection(self):
        """French is detected from common French words."""
        engine = self._make_engine()
        detection = engine.detect_language("Bonjour, merci pour la reunion. Comment allez vous?")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.FRENCH

    def test_japanese_detection(self):
        """Japanese is detected from hiragana/katakana characters."""
        engine = self._make_engine()
        detection = engine.detect_language("こんにちは、ありがとうございます")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.JAPANESE
        assert detection.confidence >= 0.9

    def test_chinese_detection(self):
        """Chinese is detected from hanzi characters (no hiragana/katakana)."""
        engine = self._make_engine()
        detection = engine.detect_language("你好，谢谢你的会议")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.CHINESE

    def test_arabic_detection(self):
        """Arabic is detected from Arabic script."""
        engine = self._make_engine()
        detection = engine.detect_language("مرحبا، شكرا لكم على الاجتماع")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.ARABIC

    def test_hindi_detection(self):
        """Hindi is detected from Devanagari script."""
        engine = self._make_engine()
        detection = engine.detect_language("नमस्ते, आपका धन्यवाद")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.HINDI

    def test_code_switching_detection(self):
        """Code-switching is detected when foreign words appear in English context."""
        engine = self._make_engine()
        detection = engine.detect_language("Let's do the jugaad approach, hello and thank you")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.ENGLISH
        assert detection.is_code_switching is True
        assert "hindi" in detection.detected_languages

    def test_translation_suggestion_spanish(self):
        """Translation is suggested for Spanish text."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        translation = engine.suggest_translation("Hola, gracias", DetectedLanguage.SPANISH)
        assert "hello" in translation.translated_text.lower()
        assert "thank" in translation.translated_text.lower()

    def test_translation_same_language(self):
        """Translation to same language returns original text."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        translation = engine.suggest_translation("Hello", DetectedLanguage.ENGLISH, DetectedLanguage.ENGLISH)
        assert translation.translated_text == "Hello"
        assert translation.confidence == 1.0

    def test_p25_confidence_has_denominator(self):
        """P25: translation confidence shows denominator."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        translation = engine.suggest_translation("Hola", DetectedLanguage.SPANISH)
        assert "insufficient" in translation.confidence_label
        assert translation.calibration_denominator == 0

        for _ in range(12):
            engine.record_translation_for_calibration()
        translation2 = engine.suggest_translation("Hola", DetectedLanguage.SPANISH)
        assert translation2.calibration_denominator == 12
        assert "12" in translation2.confidence_label

    def test_cultural_context_japanese(self):
        """Cultural context notes are provided for Japanese."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        notes = engine.get_cultural_context(DetectedLanguage.JAPANESE)
        assert len(notes) >= 1
        for note in notes:
            assert note.note  # non-empty
            assert note.category in ("business_etiquette", "communication_style", "decision_making")
            assert note.source  # has source (anti-Cluely)

    def test_cultural_context_arabic(self):
        """Cultural context notes are provided for Arabic."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        notes = engine.get_cultural_context(DetectedLanguage.ARABIC)
        assert len(notes) >= 1
        # Should mention "inshallah" (a key cultural note)
        all_notes = " ".join(n.note.lower() for n in notes)
        assert "inshallah" in all_notes

    def test_cultural_context_hindi(self):
        """Cultural context notes mention code-switching for Hindi."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        notes = engine.get_cultural_context(DetectedLanguage.HINDI)
        all_notes = " ".join(n.note.lower() for n in notes)
        assert "code-switching" in all_notes or "hinglish" in all_notes

    def test_accent_aware_stt_deferred(self):
        """Accent-aware STT is honestly marked as DEFERRED (reality check)."""
        engine = self._make_engine()
        assert engine.is_accent_aware_stt_available() is False
        status = engine.get_accent_aware_stt_status()
        assert "DEFERRED" in status
        assert "vaporware" in status.lower() or "deferred" in status.lower()
        assert "100+ hours" in status  # explains WHY it's deferred

    def test_empty_text_returns_unknown(self):
        """Empty text returns UNKNOWN language."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        detection = engine.detect_language("")
        assert detection.language == DetectedLanguage.UNKNOWN
        assert detection.confidence == 0.0

    def test_german_detection(self):
        """German is detected from common German words."""
        engine = self._make_engine()
        detection = engine.detect_language("Hallo, danke fur die Besprechung. Wie geht es?")
        from maestro_oem.multilang_support import DetectedLanguage
        assert detection.language == DetectedLanguage.GERMAN

    def test_detection_to_dict(self):
        """LanguageDetection serializes correctly."""
        engine = self._make_engine()
        detection = engine.detect_language("Hello, thank you")
        d = detection.to_dict()
        assert "language" in d
        assert "confidence" in d
        assert "is_code_switching" in d

    def test_translation_to_dict(self):
        """TranslationSuggestion serializes correctly."""
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        translation = engine.suggest_translation("Hola", DetectedLanguage.SPANISH)
        d = translation.to_dict()
        assert "original_text" in d
        assert "translated_text" in d
        assert "confidence_label" in d

    def test_auto_translation_to_other_party_requires_consent(self):
        """Ethical guard: auto-translation TO other party is NOT auto-done.

        The suggest_translation method is for the USER's understanding.
        It does NOT auto-send translations to the other party.
        The method returns a suggestion — the user must explicitly act on it.
        """
        engine = self._make_engine()
        from maestro_oem.multilang_support import DetectedLanguage
        translation = engine.suggest_translation("Hola, como estas?", DetectedLanguage.SPANISH)
        # The suggestion is returned to the user — NOT sent anywhere
        assert translation.original_text == "Hola, como estas?"
        assert translation.translated_text  # non-empty
        # No "send" or "broadcast" method exists on the engine
        assert not hasattr(engine, "send_translation")
        assert not hasattr(engine, "broadcast_translation")


class TestPhase18L0NoRegression:
    """Phase 18 must not regress the L0 substrate."""

    def test_situation_snapshot_27_fields(self):
        from maestro_oem.situation import Situation
        import dataclasses
        assert len(dataclasses.fields(Situation)) == 27

    def test_outcome_ledger_functional(self):
        from maestro_oem.governed_adaptation import OutcomeLedger
        ol = OutcomeLedger()
        assert hasattr(ol, "append") and hasattr(ol, "count")

    def test_classifier_new_types(self):
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Maybe we can ship SSO by Q4.") == "tentative"
