from backend.orchestrator.supervisor import Supervisor, classify_request


def test_supervisor_routes_policy_requests_through_the_graph() -> None:
    result = Supervisor().handle("session-1", "What is the policy for this request?")

    assert "document agent" not in result
    assert "policy guidance" in result


def test_supervisor_routes_email_requests_to_the_email_agent() -> None:
    result = Supervisor().handle("session-2", "Draft an Outlook email to the customer")

    assert "email agent" not in result
    assert "MailMate could not access the mailbox" in result


def test_supervisor_routes_mailmate_and_latest_mail_requests_to_email() -> None:
    assert classify_request({"message": "MailMate: show the latest one"})["route"] == "email"
    assert classify_request({"message": "Read my latest mail"})["route"] == "email"


def test_supervisor_keeps_assistant_responses_user_facing() -> None:
    result = Supervisor().handle("session-3", "what are policies for home loan")

    assert "assistant agent responded" not in result
    assert "Approved knowledge used" not in result
    assert "policy" in result.lower()


def test_supervisor_includes_retrieved_approved_guidance() -> None:
    result = Supervisor().handle("session-4", "What are the identity checks for customer verification?")

    assert "Approved policy guidance" in result
    assert "two approved identity checks" in result
    assert "one-time passcode" in result
