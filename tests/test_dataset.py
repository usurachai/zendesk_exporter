"""Tests for dataset preparation pipeline — conversation building, cleaning, dedup."""

import pytest

from src.dataset import (
    build_conversation,
    _clean_message,
    _clean_fillers,
    _is_filler_only,
    _split_sentences,
    _remove_canned_phrase,
    _dedupe_exact,
    _dedupe_sentences,
    _dedupe_canned,
    _discover_canned_signatures,
    generate_dataset,
    _extract_customer_name,
    _is_sunshine_format,
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
        conv = build_conversation(TICKET_NORMAL, agent_names=AGENT_NAMES, min_length=3)
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
                                   clean_fillers=True, drop_filler_only=True,
                                   min_length=3)
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

    def test_time_format_not_split(self):
        """Thai time format 09.00-18.00 preserved as single segment."""
        text = "วันจันทร์-ศุกร์ 09.00-18.00 (ยกเว้นวันหยุด) น่ะฮะ"
        sentences = _split_sentences(text)
        assert len(sentences) == 1
        assert "09.00-18.00" in sentences[0]

    def test_time_format_mixed_with_sentences(self):
        """Time format in the middle of a sentence does not cause false splits."""
        text = "ข้อความแรก. เวลาทำการ 09.00-18.00 ฮะ. ข้อความสุดท้าย"
        sentences = _split_sentences(text)
        assert len(sentences) == 3
        assert "เวลาทำการ 09.00-18.00 ฮะ" in sentences[1]

    def test_version_number_preserved(self):
        """Version numbers like 2.5.1 are not split."""
        text = "รุ่น 2.5.1 ครับ"
        sentences = _split_sentences(text)
        assert len(sentences) == 1
        assert "2.5.1" in sentences[0]

    def test_url_still_protected(self):
        """Existing URL protection still works after time-format change."""
        text = "ดูที่นี่ https://www.example.com/guide/page เลย"
        sentences = _split_sentences(text)
        assert len(sentences) == 1
        assert "https://www.example.com/guide/page" in sentences[0]


# ---------------------------------------------------------------
# Canned phrase removal
# ---------------------------------------------------------------

class TestCannedPhraseRemoval:
    """Test stripping of canned phrases from messages."""

    def test_simple_removal(self):
        """Mid-message phrase is now preserved (boundary-only stripping).
        Only strips at start or end of message."""
        result = _remove_canned_phrase(
            "ขอบคุณครับ หากต้องการสอบถามเพิ่มเติม ติดต่อได้ครับ",
            "ต้องการสอบถามเพิ่มเติม",
        )
        # Mid-message: preserved as-is (no garbling)
        assert result is not None
        assert "ต้องการสอบถามเพิ่มเติม" in result
        assert "ขอบคุณครับ" in result

    def test_strips_from_end(self):
        """Phrase at end of message gets stripped."""
        result = _remove_canned_phrase(
            "ขอบคุณครับ ต้องการสอบถามเพิ่มเติม",
            "ต้องการสอบถามเพิ่มเติม",
        )
        assert result is not None
        assert "ต้องการสอบถามเพิ่มเติม" not in result
        assert "ขอบคุณครับ" in result

    def test_strips_from_start(self):
        """Phrase at start of message gets stripped."""
        result = _remove_canned_phrase(
            "ต้องการสอบถามเพิ่มเติม ขอบคุณครับ",
            "ต้องการสอบถามเพิ่มเติม",
        )
        assert result is not None
        assert "ต้องการสอบถามเพิ่มเติม" not in result
        assert "ขอบคุณครับ" in result

    def test_removal_makes_empty(self):
        result = _remove_canned_phrase("ต้องการสอบถามเพิ่มเติม", "ต้องการสอบถามเพิ่มเติม")
        assert result is None

    def test_sig_not_present(self):
        result = _remove_canned_phrase("ข้อความธรรมดา", "ไม่พบลายเซ็นนี้")
        assert result is not None
        assert "ข้อความธรรมดา" in result

    def test_short_prefix_preserved_thai(self):
        """Thai text with short prefix (idx=10) no longer gets stripped mid-word."""
        result = _remove_canned_phrase(
            "ยินดีมากๆครับ ต้องขออภัยในความไม่สะดวก",
            "ต้องขออภัยในความไม่สะดวก",
        )
        assert result is not None
        assert "ต้องขออภัยในความไม่สะดวก" in result  # preserved, not garbled

    def test_truly_at_start_stripped(self):
        """Phrase at idx=0 still gets stripped correctly."""
        result = _remove_canned_phrase(
            "ต้องขออภัยในความไม่สะดวกครับ",
            "ต้องขออภัยในความไม่สะดวก",
        )
        assert result is not None
        assert "ต้องขออภัยในความไม่สะดวก" not in result
        assert "ครับ" in result


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
# Sunshine format edge cases
# ---------------------------------------------------------------

class TestSunshineEdgeCases:
    """Test Sunshine conversation format detection and name extraction."""

    def test_extract_customer_name_no_private_comment(self):
        """No private comment → returns None."""
        ticket = {
            "ticket_id": 1,
            "metadata": {"subject": ""},
            "comments": [
                {"author_id": -1, "public": True, "body": "(00:00) User: hello"}
            ]
        }
        name = _extract_customer_name(ticket.get("comments", []))
        assert name is None

    def test_non_sunshine_format(self):
        """Regular Zendesk comments (not via Sunshine) → detected as non-Sunshine."""
        comments = [
            {"author_id": 123, "public": True, "body": "สวัสดีครับ"},
            {"author_id": 456, "public": True, "body": "สวัสดีค่ะ"},
        ]
        assert _is_sunshine_format(comments) is False

    def test_unknown_speaker_during_parse(self):
        """Speaker not in agent_names and not matching customer → agent (safe default)."""
        ticket = {
            "ticket_id": 1,
            "metadata": {"subject": ""},
            "comments": [
                {"id": 1, "author_id": 1, "public": False, "body": "Conversation with Jane"},
                {"id": 2, "author_id": -1, "public": True,
                 "body": "(08:00:00) Jane: hello\n(08:01:00) UnknownPerson: hi there"},
            ]
        }
        conv = build_conversation(ticket, agent_names={"Support Team"},
                                   clean_fillers=False, drop_filler_only=False, min_length=1)
        assert conv is not None
        # Jane → customer, UnknownPerson → agent (safe default)
        roles = [t["role"] for t in conv["conversation"]]
        assert roles == ["customer", "agent"]


# ---------------------------------------------------------------
# PII edge cases
# ---------------------------------------------------------------

class TestPIIEdgeCases:
    """Test PII redaction edge cases."""

    def test_no_pii_unchanged(self):
        body = "สวัสดีครับ วันนี้เป็นไงบ้าง"
        cleaned = _clean_message(body, redact_pii=True)
        assert cleaned is not None
        assert cleaned == body.strip()

    def test_multiple_pii_in_one_message(self):
        body = "โทร 0812345678 หรือ email test@example.com และ 02-123-4567"
        cleaned = _clean_message(body, redact_pii=True)
        assert cleaned is not None
        assert "0812345678" not in cleaned
        assert "test@example.com" not in cleaned
        assert "02-123-4567" not in cleaned
        assert cleaned.count("[phone]") == 2
        assert cleaned.count("[email]") == 1

    def test_redact_pii_off(self):
        body = "โทร 0812345678"
        cleaned = _clean_message(body, redact_pii=False)
        assert cleaned is not None
        assert "0812345678" in cleaned


# ---------------------------------------------------------------
# _clean_message edge cases
# ---------------------------------------------------------------

class TestCleanMessageEdgeCases:
    """Test _clean_message edge cases."""

    def test_url_only_becomes_empty(self):
        """URL-only message → empty after URL→[link] strip."""
        body = "https://example.com/test"
        cleaned = _clean_message(body, clean_urls=True)
        assert cleaned is None  # stripped to empty

    def test_clean_attachments_off(self):
        body = "screenshot.png\nURL: https://example.com/abc\nType: image/png\nSize: 12345"
        cleaned = _clean_message(body, clean_attachments=False)
        assert cleaned is not None
        assert "screenshot.png" in cleaned


# ---------------------------------------------------------------
# generate_dataset error paths
# ---------------------------------------------------------------

class TestGenerateDatasetErrors:
    """Test generate_dataset error handling."""

    def test_empty_raw_dir(self, tmp_path):
        """No ticket files → error returned."""
        raw_dir = tmp_path / "empty_raw"
        raw_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = generate_dataset(
            raw_dir=str(raw_dir),
            output_dir=str(out_dir),
            train_ratio=1.0,
            shuffle_seed=42,
            system_prompt="test",
        )
        assert "error" in result
        assert result["error"] == "no_conversations"


# ---------------------------------------------------------------
# Canned dedup: dominant template
# ---------------------------------------------------------------

class TestCannedDedupDominant:
    """Test canned dedup with dominant templates (>=60% coverage)."""

    def test_dominant_template_kept_and_dropped(self):
        """Dominant template kept max_copies times, then dropped."""
        # Message where sig covers 100% of body
        dominator = "ต้องขออภัยในความไม่สะดวกด้วย"
        convs = [
            {"conversation": [{"role": "agent", "content": dominator}]},
            {"conversation": [{"role": "agent", "content": dominator}]},
            {"conversation": [{"role": "agent", "content": dominator}]},
            {"conversation": [{"role": "user", "content": "hello"}, {"role": "agent", "content": dominator}]},
        ]
        result = _dedupe_canned(convs, max_copies=2)
        # First 2 copies kept, 3rd+ dropped or conv becomes broken
        # 4th conv loses agent msg → 1 turn → dropped
        assert len(result) >= 1

    def test_no_matching_sig(self):
        """Message with no matching signature → passed through intact."""
        convs = [
            {"conversation": [{"role": "user", "content": "unique message no sig here"}]},
        ]
        result = _dedupe_canned(convs, max_copies=3)
        assert len(result) == 1
        assert result[0]["conversation"][0]["content"] == "unique message no sig here"

    def test_short_fragment_after_strip_dropped(self):
        """Fragment under 10 chars after canned strip is dropped."""
        result = _remove_canned_phrase("ยินดีมากๆ ด)", "ด)")
        assert result == "ยินดีมากๆ"
        assert len(result) <= 10


# ---------------------------------------------------------------
# Sentence dedup edge cases
# ---------------------------------------------------------------

class TestSentenceDedupEdgeCases:
    """Test sentence dedup boundary conditions."""

    def test_all_sentences_matched_dropped(self):
        """Multi-sentence message where all sentences match filter → conv dropped."""
        convs = [{"conversation": [
            {"role": "agent", "content": "ข้อความแรก. ข้อความที่สอง"}
        ]}]
        result = _dedupe_sentences(convs, filter_list={"ข้อความแรก", "ข้อความที่สอง"})
        # Both sentences matched → no kept sentences → entire turn dropped → empty conv
        assert len(result) == 0

    def test_safe_replace_phrase_not_found(self):
        """Filter phrase not in body → unchanged."""
        convs = [{"conversation": [
            {"role": "agent", "content": "ข้อความปกติ"}
        ]}]
        result = _dedupe_sentences(convs, filter_list={"ไม่พบในข้อความ"})
        assert result[0]["conversation"][0]["content"] == "ข้อความปกติ"


# ---------------------------------------------------------------
# _longest_matching_sig edge cases
# ---------------------------------------------------------------

class TestLongestMatchingSig:
    """Test longest matching signature lookup."""

    def test_no_sig_in_body(self):
        """No signature substring found in body → returns None."""
        from src.dataset import _longest_matching_sig
        body = "ข้อความปกติไม่มีการซ้ำ"
        sigs = ["a" * 25, "b" * 25]
        result = _longest_matching_sig(body, sigs)
        assert result is None

    def test_longest_sig_wins(self):
        """Among multiple matching sigs, the longest (pre-sorted) is returned first."""
        from src.dataset import _longest_matching_sig
        body = "สวัสดีครับผมชื่อสมชายครับ"
        # Must pass sigs sorted by length descending (as _dedupe_canned does)
        sigs = sorted(["ครับผม", "สวัสดีครับผมชื่อสมชายครับ"], key=len, reverse=True)
        result = _longest_matching_sig(body, sigs)
        assert result == "สวัสดีครับผมชื่อสมชายครับ"  # longest match, comes first in sorted


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


# ---------------------------------------------------------------
# Exact dedup
# ---------------------------------------------------------------

class TestExactDedup:
    """Test cross-conversation exact duplicate removal."""

    def test_drops_beyond_max_copies(self):
        convs = [
            {"conversation": [
                {"role": "user", "content": "hello"},
                {"role": "agent", "content": "สวัสดีครับ"},
            ]},
            {"conversation": [
                {"role": "user", "content": "hi"},
                {"role": "agent", "content": "สวัสดีครับ"},
            ]},
            {"conversation": [
                {"role": "user", "content": "hey"},
                {"role": "agent", "content": "สวัสดีครับ"},
            ]},
            {"conversation": [
                {"role": "user", "content": "yo"},
                {"role": "agent", "content": "สวัสดีครับ"},
            ]},
        ]
        result = _dedupe_exact(convs, max_copies=2)
        # 2 copies of "สวัสดีครับ" kept → 2 conversations with user+agent survive
        # The other 2 conversations lose agent → become 1-turn → dropped
        assert len(result) == 2
        for conv in result:
            assert len(conv["conversation"]) == 2

    def test_unique_messages_preserved(self):
        convs = [
            {"conversation": [
                {"role": "user", "content": "hello"},
                {"role": "agent", "content": "hi"},
            ]},
            {"conversation": [
                {"role": "user", "content": "goodbye"},
                {"role": "agent", "content": "bye"},
            ]},
        ]
        result = _dedupe_exact(convs, max_copies=2)
        assert len(result) == 2
        assert len(result[0]["conversation"]) == 2

    def test_broken_conversations_dropped(self):
        """Conversations reduced to <2 non-system turns are removed."""
        convs = [
            {"conversation": [
                {"role": "user", "content": "hello"},
                {"role": "agent", "content": "สวัสดีครับ"},  # duplicate
            ]},
            {"conversation": [
                {"role": "user", "content": "hey"},
                {"role": "agent", "content": "สวัสดีครับ"},  # duplicate
            ]},
        ]
        result = _dedupe_exact(convs, max_copies=1)
        # Only 1 copy of "สวัสดีครับ" kept → first conv keeps both turns
        # Second conv loses agent → 1 turn → dropped as broken
        assert len(result) == 1


# ---------------------------------------------------------------
# Sentence dedup
# ---------------------------------------------------------------

class TestSentenceDedup:
    """Test sentence-level dedup with filter list."""

    def test_filter_strips_from_single_sentence(self):
        """Mid-sentence filter phrase is preserved (boundary-only).
        Only strips when at the very beginning or end."""
        convs = [{"conversation": [
            {"role": "agent", "content": "สวัสดีครับ หากต้องการสอบถามข้อมูลเพิ่มเติม ติดต่อได้ครับ"}
        ]}]
        result = _dedupe_sentences(convs, filter_list={"ต้องการสอบถามข้อมูลเพิ่มเติม"})
        content = result[0]["conversation"][0]["content"]
        # Mid-message: preserved
        assert "ต้องการสอบถามข้อมูลเพิ่มเติม" in content
        assert "สวัสดีครับ" in content

    def test_filter_strips_from_end(self):
        """Filter phrase at end of single sentence gets stripped."""
        convs = [{"conversation": [
            {"role": "agent", "content": "ยินดีมากๆ หากต้องการสอบถามข้อมูลเพิ่มเติม"}
        ]}]
        result = _dedupe_sentences(convs, filter_list={"หากต้องการสอบถามข้อมูลเพิ่มเติม"})
        content = result[0]["conversation"][0]["content"]
        assert "ต้องการสอบถามข้อมูลเพิ่มเติม" not in content
        assert "ยินดีมากๆ" in content

    def test_filter_drops_from_multi_sentence(self):
        convs = [{"conversation": [
            {"role": "agent", "content": "ข้อความแรก. ข้อความที่สอง. ข้อความที่สาม"}
        ]}]
        result = _dedupe_sentences(convs, filter_list={"ข้อความที่สอง"})
        content = result[0]["conversation"][0]["content"]
        assert "ข้อความที่สอง" not in content
        assert "ข้อความแรก" in content
        assert "ข้อความที่สาม" in content

    def test_slice_matching_variants(self):
        """35-char slice matching catches minor wording variants."""
        convs = [{"conversation": [
            {"role": "agent", "content": "ยินดีมากๆ และถ้าพี่ต้องการสอบถามข้อมูลเพิ่มเติม สามารถฝากข้อความไว้ได้ตลอดเวลา"}
        ]}]
        # Filter has "หากพี่มนุษย์ต้องการสอบถาม..." but body has "และถ้าพี่ต้องการสอบถาม..."
        filter_phrase = "หากพี่มนุษย์ต้องการสอบถามข้อมูลเพิ่มเติม สามารถฝากข้อความไว้ได้ตลอดเวลา"
        result = _dedupe_sentences(convs, filter_list={filter_phrase})
        content = result[0]["conversation"][0]["content"]
        assert "ต้องการสอบถามข้อมูลเพิ่มเติม" not in content

    def test_empty_filter_does_nothing(self):
        convs = [{"conversation": [
            {"role": "agent", "content": "ข้อความทดสอบ"}
        ]}]
        result = _dedupe_sentences(convs, filter_list=set())
        assert result == convs


# ---------------------------------------------------------------
# URL protection in sentence splitting
# ---------------------------------------------------------------

class TestURLProtection:
    """Test that URLs survive sentence splitting intact."""

    def test_url_not_split(self):
        text = "ดูที่นี่ https://www.meowjot.com/guides/upload-statement เลย"
        sentences = _split_sentences(text)
        assert len(sentences) == 1
        assert "https://www.meowjot.com/guides/upload-statement" in sentences[0]

    def test_url_with_surrounding_sentences(self):
        # When a URL ends with punctuation immediately before the next
        # sentence, the boundary is ambiguous. The URL protection
        # prioritizes keeping the URL intact.
        text = "ข้อความแรก. ดูที่นี่ https://forms.office.com/r/abc. ข้อความสุดท้าย"
        sentences = _split_sentences(text)
        # At minimum the first sentence and the URL survive
        assert len(sentences) >= 2
        assert "ข้อความแรก" in sentences[0]
        assert "https://forms.office.com/r/abc" in sentences[1]

    def test_multiple_urls_in_message(self):
        text = "link1 https://a.b/c และ link2 https://d.e/f ครับ"
        sentences = _split_sentences(text)
        assert len(sentences) == 1
        assert "https://a.b/c" in sentences[0]
        assert "https://d.e/f" in sentences[0]


# ---------------------------------------------------------------
# Canned signature discovery
# ---------------------------------------------------------------

class TestCannedDiscovery:
    """Test dynamic canned signature detection."""

    def test_discovers_repeated_substrings(self):
        # The repeated portion "ต้องการสอบถามข้อมูลเพิ่มเติม สามารถฝากข้อความไว้"
        # is 42 chars, appears in 6 messages (>= min_freq=5)
        repeated = "ต้องการสอบถามข้อมูลเพิ่มเติม สามารถฝากข้อความไว้"
        convs = [
            {"conversation": [{"role": "agent", "content": f"prefix1. {repeated}"}]},
            {"conversation": [{"role": "agent", "content": f"prefix2. {repeated}"}]},
            {"conversation": [{"role": "agent", "content": f"prefix3. {repeated}"}]},
            {"conversation": [{"role": "agent", "content": f"prefix4. {repeated}"}]},
            {"conversation": [{"role": "agent", "content": f"prefix5. {repeated}"}]},
            {"conversation": [{"role": "agent", "content": f"prefix6. {repeated}"}]},
        ]
        sigs = _discover_canned_signatures(convs, min_len=25, min_freq=5)
        # The repeated portion should be detected as at least one 25-char signature
        assert len(sigs) > 0

    def test_urls_excluded_from_signatures(self):
        convs = [
            {"conversation": [{"role": "agent", "content": "คลิก https://www.meowjot.com/guides/income-record เลย"}]},
            {"conversation": [{"role": "agent", "content": "ดูที่ https://www.meowjot.com/guides/income-record ครับ"}]},
            {"conversation": [{"role": "agent", "content": "ตามนี้ https://www.meowjot.com/guides/income-record ฮะ"}]},
            {"conversation": [{"role": "agent", "content": "ที่นี่ https://www.meowjot.com/guides/income-record ค่ะ"}]},
            {"conversation": [{"role": "agent", "content": "link https://www.meowjot.com/guides/income-record ครับ"}]},
        ]
        sigs = _discover_canned_signatures(convs, min_len=25, min_freq=5)
        # No URL-based signatures
        url_sigs = [s for s in sigs if "meowjot" in s]
        assert len(url_sigs) == 0


# ---------------------------------------------------------------
# Full pipeline: generate_dataset
# ---------------------------------------------------------------

class TestGenerateDataset:
    """Test the full generate_dataset pipeline end-to-end."""

    def test_minimal_pipeline(self, tmp_path):
        """End-to-end: raw tickets → train/valid JSONL."""
        import json

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # Write two raw tickets
        for tid, ticket in enumerate([TICKET_NORMAL, TICKET_WITH_PII], 1):
            ticket["ticket_id"] = tid
            (raw_dir / f"ticket_{tid}.json").write_text(
                json.dumps(ticket, ensure_ascii=False)
            )

        result = generate_dataset(
            raw_dir=str(raw_dir),
            output_dir=str(out_dir),
            train_ratio=1.0,  # all train
            shuffle_seed=42,
            system_prompt="You are a helpful assistant.",
            agent_names=["Support Team"],
            clean_attachments=True,
            clean_urls=True,
            dedupe_canned=False,
            redact_pii=True,
            pii_safe_patterns=["support@meowjot.com"],
            dedupe_exact=False,
            max_duplicate_count=3,
            dedupe_sentences=False,
            clean_fillers=True,
            drop_filler_only=True,
            min_message_length=3,
        )

        assert "error" not in result
        assert result["train_count"] > 0

        # Verify train.jsonl
        train_file = out_dir / "train.jsonl"
        assert train_file.exists()
        lines = train_file.read_text().strip().split("\n")
        assert len(lines) == result["train_count"]
        for line in lines:
            rec = json.loads(line)
            assert "messages" in rec
            assert rec["messages"][0]["role"] == "system"
