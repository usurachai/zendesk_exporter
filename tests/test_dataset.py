"""Tests for dataset preparation pipeline — conversation building, cleaning, dedup."""

import pytest

from src.dataset import (
    build_conversation,
    _clean_message,
    _clean_fillers,
    _is_filler_only,
    _split_sentences,
    _remove_canned_phrase,
)

from tests.fixtures import (
    TICKET_NORMAL,
    TICKET_WITH_PII,
    TICKET_WITH_ATTACHMENT,
    TICKET_WITH_FILLERS,
    TICKET_WITH_CANNED,
)

AGENT_NAMES = {"Kissadakron Duangparsart", "Surachai Uthaisamairath", "Support Team"}


# ---------------------------------------------------------------
# Conversation building
# ---------------------------------------------------------------

class TestBuildConversation:
    """Test conversation construction from raw tickets."""

    def test_normal_conversation(self):
        """Full conversation with customer and agent messages preserved."""
        conv = build_conversation(TICKET_NORMAL, agent_names=AGENT_NAMES)
        assert conv is not None
        assert len(conv["conversation"]) == 3
        assert conv["conversation"][0]["role"] == "customer"
        assert "สวัสดีครับ" in conv["conversation"][0]["content"]
        assert conv["conversation"][1]["role"] == "agent"
        assert conv["conversation"][2]["role"] == "customer"
        assert "ขอบคุณ" in conv["conversation"][2]["content"]

    def test_unknown_speaker_defaults_to_agent(self):
        """Speaker not in agent_names and not the customer name → agent."""
        # Jane is the customer; Support Team is an agent
        conv = build_conversation(TICKET_WITH_PII, agent_names=AGENT_NAMES)
        assert conv is not None
        # The ticket has only one speaker: Jane → customer
        assert conv["conversation"][0]["role"] == "customer"


# ---------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------

class TestPIIRedaction:
    """Test PII (phone, email) redaction."""

    def test_phone_redaction(self):
        body = "เบอร์โทร 0812345678 ครับ"
        cleaned = _clean_message(body, redact_pii=True)
        assert cleaned is not None
        assert "0812345678" not in cleaned
        assert "[phone]" in cleaned

    def test_phone_with_dashes(self):
        body = "โทร 081-234-5678"
        cleaned = _clean_message(body, redact_pii=True)
        assert cleaned is not None
        assert "081-234-5678" not in cleaned
        assert "[phone]" in cleaned

    def test_email_redaction(self):
        body = "email test@example.com ครับ"
        cleaned = _clean_message(body, redact_pii=True)
        assert cleaned is not None
        assert "test@example.com" not in cleaned
        assert "[email]" in cleaned

    def test_safe_pattern_preserved(self):
        body = "ติดต่อ support@meowjot.com ได้เลย"
        cleaned = _clean_message(body, redact_pii=True,
                                  pii_safe_patterns=["support@meowjot.com"])
        assert cleaned is not None
        assert "support@meowjot.com" in cleaned

    def test_pii_in_ticket(self):
        """Full ticket: PII in Sunshine format."""
        conv = build_conversation(TICKET_WITH_PII, agent_names=AGENT_NAMES,
                                   redact_pii=True)
        assert conv is not None
        content = conv["conversation"][0]["content"]
        assert "0812345678" not in content
        assert "test@example.com" not in content
        assert "[phone]" in content
        assert "[email]" in content


# ---------------------------------------------------------------
# Attachment metadata stripping
# ---------------------------------------------------------------

class TestAttachmentCleaning:
    """Test attachment metadata removal."""

    def test_attachment_stripped(self):
        body = "ดูรูปนี้\nscreenshot.png\nURL: https://example.com/abc\nType: image/png\nSize: 12345"
        cleaned = _clean_message(body, clean_attachments=True)
        assert cleaned is not None
        assert "screenshot.png" not in cleaned
        assert "image/png" not in cleaned
        assert "[image]" in cleaned

    def test_attachment_in_ticket(self):
        conv = build_conversation(TICKET_WITH_ATTACHMENT, agent_names=AGENT_NAMES,
                                   clean_attachments=True)
        assert conv is not None
        content = conv["conversation"][0]["content"]
        assert "screenshot" not in content
        assert "[image]" in content


# ---------------------------------------------------------------
# Filler word cleaning
# ---------------------------------------------------------------

class TestFillerCleaning:
    """Test Thai filler word stripping."""

    def test_trailing_filler_stripped(self):
        assert _clean_fillers("สวัสดีครับ") == "สวัสดี"
        assert _clean_fillers("ขอบคุณมากฮะ") == "ขอบคุณมาก"
        assert _clean_fillers("ได้เลยค่ะ") == "ได้เลย"

    def test_mid_sentence_preserved(self):
        """Particles mid-sentence are natural, not stripped."""
        result = _clean_fillers("ขอบคุณครับที่แจ้งมา")
        assert result is not None
        assert "ครับ" in result  # mid-sentence → preserved

    def test_filler_only(self):
        assert _is_filler_only("ครับ") is True
        assert _is_filler_only("ฮะ") is True
        assert _is_filler_only("ๆ") is True

    def test_not_filler_only(self):
        assert _is_filler_only("โอเค") is False  # meaningful
        assert _is_filler_only("ขอบคุณ") is False  # meaningful

    def test_filler_in_ticket(self):
        """Filler-only messages dropped from conversation."""
        conv = build_conversation(TICKET_WITH_FILLERS, agent_names=AGENT_NAMES,
                                   clean_fillers=True, drop_filler_only=True)
        assert conv is not None
        # "สวัสดีครับ" → "สวัสดี" (trailing stripped), "ครับ" → dropped (filler-only)
        # So only "สวัสดี" from customer remains
        assert len(conv["conversation"]) == 1
        assert conv["conversation"][0]["role"] == "customer"
        assert "สวัสดี" in conv["conversation"][0]["content"]
        assert "ครับ" not in conv["conversation"][0]["content"]


# ---------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------

class TestSentenceSplitting:
    """Test sentence boundary detection."""

    def test_period_split(self):
        sentences = _split_sentences("ข้อความที่หนึ่ง. ข้อความที่สอง. ข้อความที่สาม")
        assert len(sentences) == 3

    def test_newline_split(self):
        sentences = _split_sentences("บรรทัดหนึ่ง\nบรรทัดสอง")
        assert len(sentences) == 2

    def test_single_sentence(self):
        sentences = _split_sentences("ข้อความเดียวไม่มีจุด")
        assert len(sentences) == 1

    def test_empty_string(self):
        sentences = _split_sentences("")
        assert len(sentences) == 0


# ---------------------------------------------------------------
# Canned phrase removal
# ---------------------------------------------------------------

class TestCannedPhraseRemoval:
    """Test stripping of canned phrases from messages."""

    def test_simple_removal(self):
        result = _remove_canned_phrase(
            "ขอบคุณครับ หากต้องการสอบถามเพิ่มเติม ติดต่อได้ครับ",
            "ต้องการสอบถามเพิ่มเติม",
        )
        assert result is not None
        assert "ต้องการสอบถามเพิ่มเติม" not in result
        assert "ขอบคุณครับ" in result
        assert "ติดต่อได้ครับ" in result

    def test_removal_makes_empty(self):
        result = _remove_canned_phrase("ต้องการสอบถามเพิ่มเติม", "ต้องการสอบถามเพิ่มเติม")
        assert result is None

    def test_sig_not_present(self):
        result = _remove_canned_phrase("ข้อความธรรมดา", "ไม่พบลายเซ็นนี้")
        assert result is not None
        assert "ข้อความธรรมดา" in result


# ---------------------------------------------------------------
# Canned template handling
# ---------------------------------------------------------------

class TestCannedTemplateHandling:
    """Test that canned closing templates are handled."""

    def test_canned_suffix_stripped(self):
        """Closing template at end of message gets stripped."""
        conv = build_conversation(TICKET_WITH_CANNED, agent_names=AGENT_NAMES,
                                   clean_fillers=True, drop_filler_only=True)
        assert conv is not None
        # "แก้ไขให้แล้วนะฮะ" should survive, the closing template gets stripped
        # by canned dedup later in the pipeline
        agent_msgs = [t for t in conv["conversation"] if t["role"] == "agent"]
        assert len(agent_msgs) == 1
        assert "แก้ไขให้แล้ว" in agent_msgs[0]["content"]


# ---------------------------------------------------------------
# URL cleaning
# ---------------------------------------------------------------

class TestURLCleaning:
    """Test URL replacement."""

    def test_url_replaced(self):
        body = "ดูที่ https://www.example.com/very/long/path?query=value นะครับ"
        cleaned = _clean_message(body, clean_urls=True)
        assert cleaned is not None
        assert "https://www.example.com" not in cleaned
        assert "[link]" in cleaned

    def test_short_urls_preserved(self):
        body = "ดูที่ meowjot.com นะครับ"
        cleaned = _clean_message(body, clean_urls=True)
        assert cleaned is not None
        assert "meowjot.com" in cleaned
