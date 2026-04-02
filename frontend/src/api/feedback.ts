export async function submitMessageFeedback(
  messageId: string,
  isLiked: boolean,
): Promise<void> {
  const res = await fetch(`/api/v1/chat/message/${messageId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_liked: isLiked }),
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || res.statusText)
  }
}
