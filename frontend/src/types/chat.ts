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

export interface AgentTraceStep {
  ts: number
  event?: string
  name?: string
  phase?: string
  label?: string
  detail?: string
}

/** Last agent run timeline + optional Langfuse trace id */
export interface AgentTracePayload {
  steps: AgentTraceStep[]
  observability_trace_id: string | null
}

export type WsInbound =
  | { type: 'info'; conversation_id: string }
  | { type: 'message_id'; message_id: string }
  | { type: 'status'; content: string }
  | { type: 'token'; content: string }
  | {
      type: 'agent_trace'
      steps: AgentTraceStep[]
      observability_trace_id: string | null
    }
  | { type: 'done' }
  | { type: 'error'; content: string }
