"""
Voice profile analyzer.

Analyzes user's past emails to build a voice profile for draft generation.
Extracts style, common phrases, formality level, and signature patterns.
"""

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import List
import logging

from maestro_personal_shell.email_models import VoiceProfile, EmailMessage
from maestro_personal_shell.gmail_client import get_gmail_service

logger = logging.getLogger(__name__)


async def get_user_voice_profile(user_email: str) -> VoiceProfile:
    """
    Get or build user's voice profile.
    
    Checks cache first, then analyzes recent sent emails if needed.
    
    Args:
        user_email: User's email address
        
    Returns:
        VoiceProfile with style analysis
    """
    # TODO: Add caching layer (Redis or database)
    # For now, always analyze fresh
    
    try:
        # Get last 100 sent emails from Gmail
        gmail_service = await get_gmail_service(user_email)
        
        # Query for sent emails in last 90 days
        query = "in:sent newer_than:90d"
        results = gmail_service.users().messages().list(
            userId="me",
            q=query,
            maxResults=100
        ).execute()
        
        messages = results.get("messages", [])
        
        if not messages:
            logger.warning(f"No sent emails found for {user_email}")
            return _default_voice_profile(user_email)
        
        # Fetch full message data
        sent_emails = []
        for msg_meta in messages:
            msg = gmail_service.users().messages().get(
                userId="me",
                id=msg_meta["id"],
                format="full"
            ).execute()
            
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            
            # Extract body
            body = ""
            if "parts" in msg["payload"]:
                for part in msg["payload"]["parts"]:
                    if part["mimeType"] == "text/plain":
                        import base64
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode()
                        break
            elif "body" in msg["payload"] and "data" in msg["payload"]["body"]:
                import base64
                body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode()
            
            if body:
                sent_emails.append(body)
        
        if not sent_emails:
            return _default_voice_profile(user_email)
        
        # Analyze the emails
        return _analyze_emails(user_email, sent_emails)
        
    except Exception as e:
        logger.error(f"Error building voice profile for {user_email}: {e}")
        return _default_voice_profile(user_email)


def _analyze_emails(user_email: str, emails: List[str]) -> VoiceProfile:
    """
    Analyze a list of email bodies to build voice profile.
    
    Args:
        user_email: User's email
        emails: List of email body texts
        
    Returns:
        VoiceProfile with analysis results
    """
    # Combine all emails
    all_text = " ".join(emails)
    
    # 1. Analyze sentence length
    sentences = re.split(r'[.!?]+', all_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if sentences:
        word_counts = [len(s.split()) for s in sentences]
        avg_sentence_length = sum(word_counts) / len(word_counts)
    else:
        avg_sentence_length = 12.0
    
    # 2. Extract common phrases (2-3 word phrases)
    words = all_text.lower().split()
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    trigrams = [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words)-2)]
    
    bigram_counts = Counter(bigrams)
    trigram_counts = Counter(trigrams)
    
    # Get top 10 most common phrases (excluding very common words)
    stop_phrases = {"i am", "it is", "this is", "that is", "we are", "you are"}
    common_phrases = []
    
    for phrase, count in bigram_counts.most_common(20):
        if phrase not in stop_phrases and count >= 3:
            common_phrases.append(phrase)
        if len(common_phrases) >= 5:
            break
    
    for phrase, count in trigram_counts.most_common(20):
        if phrase not in stop_phrases and count >= 2:
            common_phrases.append(phrase)
        if len(common_phrases) >= 10:
            break
    
    # 3. Detect signature pattern
    signature = _detect_signature(emails)
    
    # 4. Score formality (0.0 = very casual, 1.0 = very formal)
    formality = _score_formality(all_text)
    
    # 5. Classify style
    style = _classify_style(formality, avg_sentence_length, common_phrases)
    
    return VoiceProfile(
        user_email=user_email,
        style=style,
        common_phrases=common_phrases[:10],
        signature=signature,
        avg_sentence_length=round(avg_sentence_length, 1),
        formality=round(formality, 2),
        samples_analyzed=len(emails),
        last_updated=datetime.utcnow()
    )


def _detect_signature(emails: List[str]) -> str:
    """
    Detect common signature pattern from emails.
    
    Looks for repeated endings across emails.
    """
    # Get last 3 lines of each email
    endings = []
    for email in emails:
        lines = email.strip().split("\n")
        if len(lines) >= 3:
            endings.append("\n".join(lines[-3:]))
    
    if not endings:
        return ""
    
    # Find most common ending
    ending_counts = Counter(endings)
    most_common = ending_counts.most_common(1)
    
    if most_common and most_common[0][1] >= 3:
        return most_common[0][0]
    
    return ""


def _score_formality(text: str) -> float:
    """
    Score text formality from 0.0 (casual) to 1.0 (formal).
    
    Based on:
    - Formal words (therefore, however, furthermore)
    - Casual words (gonna, wanna, lol, hey)
    - Contractions (I'm, you're, don't)
    - Sentence structure
    """
    text_lower = text.lower()
    
    formal_indicators = [
        "therefore", "however", "furthermore", "consequently",
        "regarding", "concerning", "pertaining", "sincerely",
        "respectfully", "cordially", "best regards"
    ]
    
    casual_indicators = [
        "gonna", "wanna", "gotta", "lol", "hey", "hi",
        "thanks", "cheers", "btw", "fyi", "asap"
    ]
    
    formal_count = sum(1 for word in formal_indicators if word in text_lower)
    casual_count = sum(1 for word in casual_indicators if word in text_lower)
    
    # Count contractions
    contractions = len(re.findall(r"\b\w+'\w+\b", text))
    
    # Calculate score
    total_words = len(text.split())
    if total_words == 0:
        return 0.5
    
    formal_score = formal_count / total_words * 100
    casual_score = (casual_count + contractions / 10) / total_words * 100
    
    # Normalize to 0.0-1.0
    score = 0.5 + (formal_score - casual_score) / 10
    return max(0.0, min(1.0, score))


def _classify_style(formality: float, avg_length: float, phrases: List[str]) -> str:
    """
    Classify overall writing style.
    
    Returns: "professional", "casual", "formal", or "technical"
    """
    # Check for technical indicators
    technical_phrases = ["api", "endpoint", "function", "class", "method", "parameter"]
    if any(phrase in " ".join(phrases).lower() for phrase in technical_phrases):
        return "technical"
    
    # Use formality score
    if formality >= 0.7:
        return "formal"
    elif formality <= 0.3:
        return "casual"
    else:
        return "professional"


def _default_voice_profile(user_email: str) -> VoiceProfile:
    """
    Return default voice profile when no data available.
    """
    return VoiceProfile(
        user_email=user_email,
        style="professional",
        common_phrases=["sounds good", "let me know", "best regards"],
        signature="Best regards,",
        avg_sentence_length=12.0,
        formality=0.5,
        samples_analyzed=0,
        last_updated=datetime.utcnow()
    )
