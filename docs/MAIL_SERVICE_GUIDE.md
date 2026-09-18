# MailMate / Outlook Mail Service Guide

## Overview

This workspace includes a privacy-first mail workflow for the `MailMate` email agent. Classic Outlook desktop COM is the default integration; Microsoft Graph is an optional provider.

## Current mail architecture

### 1. Frontend (`frontend/`)
- The UI is built with Next.js and presents the `MailMate` agent.
- The user enters a message such as: `Read my Outlook mail`, `Draft an Outlook email`, or `Show my unread emails`.
- The frontend sends the request to the backend API at `/api/v1/chat/sessions/{session_id}/messages`.

### 2. Backend API (`backend/app/`)
- FastAPI exposes the chat route.
- The request is forwarded to the supervisor orchestration layer.
- The backend has no hardcoded mail credentials or external mail provider secrets in the current implementation.

### 3. Supervisor (`backend/orchestrator/supervisor.py`)
- The supervisor classifies the message.
- If the request contains `email`, `outlook`, `send`, `reply`, or `draft`, it routes the request to the `EmailAgent`.
- This keeps the email logic isolated from the main chat flow.

### 4. Email agent (`backend/agents/email_agent.py`)
- The `EmailAgent` calls the local Outlook mailbox reader helper.
- It reads unread messages from the current Windows user's default Outlook mailbox.
- It returns a summary including subject, sender, received time, and a short snippet of the message body.

### 5. Outlook access (`win32com.client` / Microsoft Outlook COM)
- The code uses the Windows COM API to connect to the locally installed Outlook desktop application.
- This means the service uses the credentials already available to the current Windows user session and their existing Outlook profile.
- No separate third-party key is required for this local desktop mode.

## Credentials and authentication model

### Recommended for your requirement: local Outlook desktop authentication

This is the best fit for a confidential, personal mailbox.

- Uses: the local Windows account and the user's existing Outlook sign-in
- Does not require: a vendor API key, app secret, OAuth client secret, or external service account
- Does require: Outlook desktop installed on the same Windows machine, and the user already signed in to Outlook

### Important security note

Because this reads a personal mailbox, the safest pattern is:

- keep the service local to the user's machine
- do not expose the full message body to remote systems
- do not store raw mail content in a shared database
- do not log confidential message content in production logs
- keep the mailbox read operation within the local user session only

## End-to-end request flow

1. User opens the frontend UI.
2. User asks something like: `Read my Outlook mail`.
3. Frontend posts the message to the backend chat API.
4. Supervisor routes the request to `EmailAgent`.
5. `EmailAgent` invokes `_read_outlook_mailbox()`.
6. `_read_outlook_mailbox()` connects to the local Outlook desktop app using `pywin32` (`win32com.client`).
7. Outlook returns unread messages from the default Inbox.
8. The agent builds a summary response.
9. The backend returns the summary to the frontend.
10. The frontend displays the mail summary in the `MailMate` workspace.

## Current code paths

- Frontend chat request: `frontend/src/components/ChatWorkspace.tsx`
- Backend route: `backend/app/api/routes/chat.py`
- Supervisor routing: `backend/orchestrator/supervisor.py`
- Mail agent: `backend/agents/email_agent.py`

## Dependency status

The backend currently declares:

- `pywin32`

This is the package needed for Windows Outlook COM integration.

## What the code does today

The current implementation:

- reads unread mail or the latest mail through classic Outlook desktop by default
- supports Graph search, attachment metadata, send, reply, forward, move, and categorize operations through `GraphMailClient`
- returns subject, sender, received time, a body preview, and triage for unread/read, relevance, important sender, attachments, and action needed
- can use Microsoft Graph when `MAIL_PROVIDER=graph` is configured

## What the code does not do today

The current implementation requires a Microsoft Entra public-client registration, delegated consent, and the user's device sign-in. It does not embed a mailbox password or client secret.

## Privacy and compliance guidance

Because this service handles personal and confidential email data, use the following controls:

1. Run only on the employee's desktop or a tightly controlled workstation.
2. Keep all mail processing inside the local machine boundary.
3. Avoid storing full email bodies unless absolutely necessary.
4. Restrict logs, especially for subject/body content.
5. Use role-based access if the mailbox is shared.
6. Require explicit user approval before sending or drafting responses that include personal data.

## Microsoft Graph configuration

Microsoft Graph OAuth requires:

That would require:

- Microsoft Entra app registration
- client ID and tenant ID for a public-client application
- user or admin consent
- Graph permissions such as `Mail.Read`

The first Graph mail request displays a device-login code in the backend terminal. After sign-in, the local MSAL cache is reused.

## Recommended configuration for your case

For your stated requirement of protecting personal and confidential information, the recommended setup is:

- Use a delegated public-client Graph application, never a shared client secret for a personal mailbox
- Keep the MSAL cache local and protected
- Set `ALLOW_OUTLOOK_FALLBACK=false` where Graph-only access is required
- Configure `MAIL_IMPORTANT_SENDERS` with trusted sender addresses for the important-sender triage rule

## Practical deployment note

This implementation works best when:

- the machine runs Windows
- Outlook desktop is installed and authenticated
- the user is signed into the OS account that owns the mailbox
- `pywin32` is installed in the Python environment

## Conclusion

The mail service uses Microsoft-supported delegated Graph access and keeps its credential cache local.

If you want, the next step can be to add a stricter privacy mode that:

- removes message-body previews entirely
- returns only metadata and action items
- stores no message content at all
- requires explicit confirmation before any send/draft action
