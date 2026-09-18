const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function sendMessage(sessionId: string, message: string) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    throw new Error("Unable to send message");
  }

  return response.json() as Promise<{ session_id: string; answer: string; route?: string }>;
}

export async function sendEmail(recipient: string, subject: string, body: string) {
  const response = await fetch(`${API_BASE_URL}/email/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient, subject, body }),
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Unable to send email");
  }

  return response.json() as Promise<{ status: string; recipient: string }>;
}

export async function getEmailMessages(unreadOnly = true, query = "") {
  const params = new URLSearchParams({ unread_only: String(unreadOnly) });
  if (query.trim()) params.set("query", query.trim());
  const response = await fetch(`${API_BASE_URL}/email/messages?${params.toString()}`, { cache: "no-store" });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to load mailbox");
  return payload as {
    messages: Array<{
      id: string;
      subject: string;
      sender: string;
      sender_email: string;
      received_at: string;
      body: string;
      priority: string;
      has_attachments: boolean;
      attachment_names: string[];
    }>;
  };
}

export async function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/documents/upload`, { method: "POST", body: formData });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? "Unable to analyze document");
  }
  return payload as {
    status: string;
    document_id: string;
    analysis: {
      filename: string;
      characters: number;
      word_count: number;
      summary: string;
      headings: string[];
      action_items: string[];
      keywords: string[];
    };
  };
}

export async function getDashboardSummary() {
  const response = await fetch(`${API_BASE_URL}/dashboard/summary`, { cache: "no-store" });
  if (!response.ok) throw new Error("Unable to load dashboard metrics");
  return response.json() as Promise<{
    status: string;
    connected_integrations: number;
    integration_status: Record<string, boolean>;
    knowledge_documents: number;
  }>;
}

export async function searchKnowledge(query: string) {
  const response = await fetch(`${API_BASE_URL}/knowledge/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error("Unable to search approved knowledge");
  }

  return response.json() as Promise<{
    query: string;
    results: Array<{
      citation: string;
      source: string;
      content: string;
      score: number;
      page: number | null;
    }>;
  }>;
}
