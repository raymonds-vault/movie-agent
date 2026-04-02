export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  /** Waiting for first streamed token (show skeleton) */
  awaitingFirstToken?: boolean
  /** Agent status line from WebSocket status events */
  agentStatus?: string | null
  /** Set when turn completes; used for feedback API */
  messageId?: string
  error?: boolean
  /** User hit Stop with no content yet */
  stopped?: boolean
}

export type WsInbound =
  | { type: 'info'; conversation_id: string }
  | { type: 'message_id'; message_id: string }
  | { type: 'status'; content: string }
  | { type: 'token'; content: string }
  | { type: 'done' }
  | { type: 'error'; content: string }
