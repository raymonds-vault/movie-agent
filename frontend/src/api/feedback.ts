export async function submitMessageFeedback(
  messageId: string,
  isLiked: boolean,
  getToken?: () => Promise<string | null>,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (getToken) {
    const t = await getToken()
    if (t) headers.Authorization = `Bearer ${t}`
  }
  const res = await fetch(`/api/v1/chat/message/${messageId}/feedback`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ is_liked: isLiked }),
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || res.statusText)
  }
}
