"""Test fixtures: sample Zendesk tickets for dataset preparation testing."""

# Ticket with normal conversation
TICKET_NORMAL = {
    "ticket_id": 10001,
    "metadata": {"id": 10001, "subject": "Test ticket", "status": "open",
                  "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
                  "requester_id": 1, "submitter_id": 1, "assignee_id": 2,
                  "group_id": 1, "tags": []},
    "channel": "facebook_messenger",
    "comments": [
        {"id": 1, "author_id": 100, "created_at": "2026-01-01T00:00:00Z",
         "public": False, "body": "Conversation with John Customer", "attachments": []},
        {"id": 2, "author_id": -1, "created_at": "2026-01-01T00:01:00Z",
         "public": True,
         "body": "(08:00:00) John Customer: สวัสดีครับ มีปัญหาเรื่องการใช้งาน\n(08:01:00) Support Team: สวัสดีครับ มีอะไรให้ช่วยครับ",
         "attachments": []},
        {"id": 3, "author_id": -1, "created_at": "2026-01-01T00:02:00Z",
         "public": True,
         "body": "(08:02:00) John Customer: ขอบคุณครับ",
         "attachments": []},
    ],
}

# Ticket with PII
TICKET_WITH_PII = {
    "ticket_id": 10002,
    "metadata": {"id": 10002, "subject": "PII ticket", "status": "open",
                  "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
                  "requester_id": 1, "submitter_id": 1, "assignee_id": 2,
                  "group_id": 1, "tags": []},
    "channel": "facebook_messenger",
    "comments": [
        {"id": 1, "author_id": 100, "created_at": "2026-01-01T00:00:00Z",
         "public": False, "body": "Conversation with Jane", "attachments": []},
        {"id": 2, "author_id": -1, "created_at": "2026-01-01T00:01:00Z",
         "public": True,
         "body": "(09:00:00) Jane: เบอร์โทร 0812345678 และ email test@example.com ครับ",
         "attachments": []},
    ],
}

# Ticket with attachment
TICKET_WITH_ATTACHMENT = {
    "ticket_id": 10003,
    "metadata": {"id": 10003, "subject": "Attachment ticket", "status": "open",
                  "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
                  "requester_id": 1, "submitter_id": 1, "assignee_id": 2,
                  "group_id": 1, "tags": []},
    "channel": "facebook_messenger",
    "comments": [
        {"id": 1, "author_id": 100, "created_at": "2026-01-01T00:00:00Z",
         "public": False, "body": "Conversation with Bob", "attachments": []},
        {"id": 2, "author_id": -1, "created_at": "2026-01-01T00:01:00Z",
         "public": True,
         "body": "(10:00:00) Bob: ดูรูปนี้\nscreenshot.png\nURL: https://example.com/abc\nType: image/png\nSize: 12345",
         "attachments": []},
    ],
}

# Ticket with filler words
TICKET_WITH_FILLERS = {
    "ticket_id": 10004,
    "metadata": {"id": 10004, "subject": "Filler ticket", "status": "open",
                  "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
                  "requester_id": 1, "submitter_id": 1, "assignee_id": 2,
                  "group_id": 1, "tags": []},
    "channel": "facebook_messenger",
    "comments": [
        {"id": 1, "author_id": 100, "created_at": "2026-01-01T00:00:00Z",
         "public": False, "body": "Conversation with Alice", "attachments": []},
        {"id": 2, "author_id": -1, "created_at": "2026-01-01T00:01:00Z",
         "public": True,
         "body": "(11:00:00) Alice: สวัสดีครับ\n(11:01:00) Support Team: ครับ",
         "attachments": []},
    ],
}

# Ticket with canned/closing message
TICKET_WITH_CANNED = {
    "ticket_id": 10005,
    "metadata": {"id": 10005, "subject": "Canned ticket", "status": "closed",
                  "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
                  "requester_id": 1, "submitter_id": 1, "assignee_id": 2,
                  "group_id": 1, "tags": []},
    "channel": "facebook_messenger",
    "comments": [
        {"id": 1, "author_id": 100, "created_at": "2026-01-01T00:00:00Z",
         "public": False, "body": "Conversation with Charlie", "attachments": []},
        {"id": 2, "author_id": -1, "created_at": "2026-01-01T00:01:00Z",
         "public": True,
         "body": "(12:00:00) Charlie: มีปัญหา\n(12:01:00) Support Team: แก้ไขให้แล้วนะฮะ หากพี่มนุษย์ต้องการสอบถามข้อมูลเพิ่มเติม สามารถฝากข้อความไว้ได้ตลอดเวลาและทางทีมงานจะเร่งติดต่อกลับในเวลาทำการ จันทร์-ศุกร์ 9:00-18:00น.",
         "attachments": []},
    ],
}
