from backend.agents.email_agent import EmailAgent, _outlook_sender_email
from backend.core.models import AgentContext


def test_email_agent_reads_local_outlook_mail(monkeypatch) -> None:
    def fake_read_outlook_mailbox() -> list[dict[str, str]]:
        return [
            {
                "subject": "Payment issue",
                "sender": "Sam Lee",
                "received_at": "2026-09-14 09:00",
                "body": "Please review the approval delay.",
            }
        ]

    monkeypatch.setattr(
        "backend.agents.email_agent._read_outlook_mailbox",
        fake_read_outlook_mailbox,
        raising=False,
    )

    result = EmailAgent().run(AgentContext(session_id="session-4", message="Read my Outlook mail"))

    assert "1 unread email" in result
    assert "Payment issue" in result
    assert "Sam Lee" in result


def test_outlook_sender_email_resolves_exchange_sender() -> None:
    class ExchangeUser:
        PrimarySmtpAddress = "sam@example.com"

    sender = type(
        "Sender",
        (),
        {"GetExchangeUser": lambda self: ExchangeUser()},
    )()

    class Message:
        SenderEmailAddress = "/o=EXORG/ou=Exchange/cn=Recipients/cn=sam"
        SenderEmailType = "EX"
        Sender = sender

    assert _outlook_sender_email(Message()) == "sam@example.com"


def test_email_agent_extracts_action_items(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.email_agent._read_outlook_mailbox",
        lambda: [{"subject": "Report", "sender": "Sam Lee", "body": "Please review the approval delay."}],
    )

    result = EmailAgent().run(AgentContext(session_id="session-5", message="Show action items"))

    assert "Action items" in result
    assert "review the approval delay" in result


def test_email_agent_drafts_reply_for_matching_sender(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.email_agent._read_outlook_mailbox",
        lambda unread_only=True: [{"subject": "Payment issue", "sender": "Sam Lee", "body": "Please review this."}],
    )

    result = EmailAgent().run(AgentContext(session_id="session-6", message="Draft a reply to Sam Lee"))

    assert "Draft reply for Sam Lee" in result
    assert "Regards" in result


def test_email_agent_drafts_new_email_from_instructions(monkeypatch) -> None:
    monkeypatch.setattr("backend.agents.email_agent._read_outlook_mailbox", lambda unread_only=True: [])
    monkeypatch.setattr(
        "backend.agents.email_agent._ai_new_draft",
        lambda instruction: "Subject: Account review\n\nHello,\n\nPlease review the account.\n\nRegards,\nSampath",
    )

    result = EmailAgent().run(
        AgentContext(session_id="session-new-draft", message="Draft a new email: ask the team to review the account")
    )

    assert result.startswith("New email draft:")
    assert "Subject: Account review" in result
    assert "Please review the account" in result


def test_email_agent_uses_openai_draft_when_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.email_agent._read_outlook_mailbox",
        lambda unread_only=True: [{"subject": "Payment issue", "sender": "Sam Lee", "body": "Please review the approval delay."}],
    )
    monkeypatch.setattr(
        "backend.agents.email_agent._ai_draft",
        lambda email: "Hi Sam,\n\nI reviewed the approval delay and will confirm the next step shortly.\n\nRegards,\nSampath",
    )

    result = EmailAgent().run(AgentContext(session_id="session-6-ai", message="Draft a reply to Sam Lee"))

    assert "I reviewed the approval delay" in result
    assert "Thanks for your email" not in result


def test_email_agent_drafts_reply_for_read_email(monkeypatch) -> None:
    def fake_read_outlook_mailbox(*, unread_only: bool = True) -> list[dict[str, str]]:
        assert unread_only is False
        return [{"subject": "Read update", "sender": "Sam Lee", "body": "Please review this update.", "is_read": "true"}]

    monkeypatch.setattr("backend.agents.email_agent._read_outlook_mailbox", fake_read_outlook_mailbox)

    result = EmailAgent().run(AgentContext(session_id="session-read-draft", message="Draft a reply to Sam Lee"))

    assert "Draft reply for Sam Lee" in result


def test_email_agent_combines_summary_actions_and_draft_for_selected_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.email_agent._read_outlook_mailbox",
        lambda unread_only=True: [
            {
                "subject": "Consignment 11",
                "sender": "Ravi Kumar Bhadram",
                "body": "Please discuss consignment 11 invoice generation. Prepare the invoice as per our terms.",
            }
        ],
    )

    result = EmailAgent().run(
        AgentContext(
            session_id="session-combined-email",
            message="Select the email from Ravi Kumar Bhadram regarding Consignment 11 to summarize it, show action items, and draft a response.",
        )
    )

    assert "Email summary:" in result
    assert "Action items:" in result
    assert "Draft reply for Ravi Kumar Bhadram" in result
    assert "discuss consignment 11 invoice generation" in result


def test_email_agent_extracts_actions_for_selected_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.email_agent._read_outlook_mailbox",
        lambda: [
            {"subject": "Invoice 11", "sender": "Kumar", "body": "Please review invoice 11."},
            {"subject": "Account alert", "sender": "Security", "body": "Please review recent activity."},
        ],
    )

    result = EmailAgent().run(AgentContext(session_id="session-selected", message="Show action items for Invoice 11"))

    assert "Invoice 11: review invoice 11" in result
    assert "Account alert" not in result


def test_email_agent_filters_high_priority_messages(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.email_agent._read_outlook_mailbox",
        lambda: [
            {"subject": "Urgent payment issue", "sender": "Sam Lee", "body": "Action required today."},
            {"subject": "Newsletter", "sender": "Bank", "body": "Monthly updates."},
        ],
    )

    result = EmailAgent().run(AgentContext(session_id="session-7", message="Only show high priority messages"))

    assert "Urgent payment issue" in result
    assert "Newsletter" not in result


def test_email_agent_uses_concise_empty_inbox_response(monkeypatch) -> None:
    monkeypatch.setattr("backend.agents.email_agent._read_outlook_mailbox", lambda: [])

    result = EmailAgent().run(AgentContext(session_id="session-8", message="Show action items"))

    assert result == "No unread emails or action items were found."


def test_email_agent_reads_the_latest_message_even_when_already_read(monkeypatch) -> None:
    def fake_read_mailbox(*, unread_only: bool) -> list[dict[str, str]]:
        assert unread_only is False
        return [
            {
                "subject": "Your verification code",
                "sender": "Security team",
                "received_at": "2026-09-16 10:15",
                "body": "Your verification code is 123456.",
                "is_read": "true",
            }
        ]

    monkeypatch.setattr("backend.agents.email_agent._read_mailbox", fake_read_mailbox)

    result = EmailAgent().run(AgentContext(session_id="session-9", message="Read my latest email"))

    assert "Latest email" in result
    assert "Your verification code" in result
    assert "123456" in result
    assert "Triage: read" in result


def test_email_agent_reads_requested_count_from_read_and_unread_mail(monkeypatch) -> None:
    def fake_read_mailbox(*, unread_only: bool) -> list[dict[str, str]]:
        assert unread_only is False
        return [
            {"subject": f"Message {index}", "sender": "Team", "body": f"Update {index}."}
            for index in range(1, 8)
        ]

    monkeypatch.setattr("backend.agents.email_agent._read_mailbox", fake_read_mailbox)

    result = EmailAgent().run(AgentContext(session_id="session-10", message="Read 5 emails, read or unread"))

    assert "Found 5 emails" in result
    assert "Message 1" in result
    assert "Message 5" in result
    assert "Message 6" not in result
