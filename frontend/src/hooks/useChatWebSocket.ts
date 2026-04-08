import { useCallback, useEffect, useRef, useState } from 'react'
import type { AgentTracePayload, ChatMessage, WsInbound } from '../types/chat'

function welcomeMessages(): ChatMessage[] {
  return [
    {
      id: 'welcome',
      role: 'assistant',
      content:
        "Hi there! I'm **CinemaBot**. Ask me anything about movies — search, details, recommendations, trivia. Let's roll!",
    },
  ]
}

export function useChatWebSocket(getIdToken: () => Promise<string | null>) {
  const getIdTokenRef = useRef(getIdToken)
  useEffect(() => {
    getIdTokenRef.current = getIdToken
  }, [getIdToken])

  const [messages, setMessages] = useState<ChatMessage[]>(welcomeMessages)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [lastAgentTrace, setLastAgentTrace] = useState<AgentTracePayload | null>(
    null,
  )

  const conversationIdRef = useRef<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const stopRequestedRef = useRef(false)
  const pendingMessageIdRef = useRef<string | null>(null)

  const finishAssistantTurn = useCallback((assistantId: string) => {
    const msgId = pendingMessageIdRef.current
    pendingMessageIdRef.current = null
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId
          ? {
              ...m,
              awaitingFirstToken: false,
              agentStatus: null,
              messageId: msgId ?? m.messageId,
            }
          : m,
      ),
    )
  }, [])

  const stop = useCallback(() => {
    stopRequestedRef.current = true
    wsRef.current?.close()
    setWsConnected(false)
    setIsStreaming(false)
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last?.role === 'assistant' && last.content === '') {
        return prev.map((m, i) =>
          i === prev.length - 1
            ? {
                ...m,
                awaitingFirstToken: false,
                agentStatus: null,
                stopped: true,
              }
            : m,
        )
      }
      return prev
    })
    wsRef.current = null
  }, [])

  const newChat = useCallback(() => {
    stopRequestedRef.current = true
    wsRef.current?.close()
    wsRef.current = null
    conversationIdRef.current = null
    setConversationId(null)
    pendingMessageIdRef.current = null
    setWsConnected(false)
    setIsStreaming(false)
    setMessages([
      {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'New chat started! What movie are we exploring?',
      },
    ])
    setLastAgentTrace(null)
  }, [])

  const sendMessage = useCallback(
    (raw: string) => {
      const text = raw.trim()
      if (!text || isStreaming) return

      stopRequestedRef.current = false
      pendingMessageIdRef.current = null

      const assistantId = crypto.randomUUID()
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      }
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        awaitingFirstToken: true,
        agentStatus: 'Analyzing context…',
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/chat/ws`)
      wsRef.current = ws

      ws.onopen = () => {
        void (async () => {
          setWsConnected(true)
          const id_token = (await getIdTokenRef.current()) ?? ''
          ws.send(
            JSON.stringify({
              message: text,
              conversation_id: conversationIdRef.current,
              id_token,
            }),
          )
        })()
      }

      ws.onmessage = (evt) => {
        if (stopRequestedRef.current) return
        let data: WsInbound
        try {
          data = JSON.parse(evt.data) as WsInbound
        } catch {
          return
        }

        switch (data.type) {
          case 'info':
            conversationIdRef.current = data.conversation_id
            setConversationId(data.conversation_id)
            break
          case 'agent_trace':
            setLastAgentTrace({
              steps: data.steps,
              observability_trace_id: data.observability_trace_id,
            })
            break
          case 'message_id':
            pendingMessageIdRef.current = data.message_id
            break
          case 'status':
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      agentStatus: data.content || null,
                    }
                  : m,
              ),
            )
            break
          case 'token':
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: m.content + data.content,
                      awaitingFirstToken: false,
                      agentStatus: null,
                    }
                  : m,
              ),
            )
            break
          case 'done':
            finishAssistantTurn(assistantId)
            break
          case 'error':
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: data.content,
                      error: true,
                      awaitingFirstToken: false,
                      agentStatus: null,
                    }
                  : m,
              ),
            )
            finishAssistantTurn(assistantId)
            break
        }
      }

      ws.onerror = () => {
        setWsConnected(false)
      }

      ws.onclose = () => {
        if (wsRef.current !== ws) return
        wsRef.current = null
        setWsConnected(false)
        setIsStreaming(false)
      }
    },
    [isStreaming, finishAssistantTurn],
  )

  const regenerate = useCallback(() => {
    if (isStreaming || !conversationIdRef.current) return

    stopRequestedRef.current = false
    pendingMessageIdRef.current = null

    const assistantId = crypto.randomUUID()
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      awaitingFirstToken: true,
      agentStatus: 'Regenerating…',
    }
    setMessages((prev) => [...prev, assistantMsg])
    setIsStreaming(true)

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/chat/ws`)
    wsRef.current = ws

    ws.onopen = () => {
      void (async () => {
        setWsConnected(true)
        const id_token = (await getIdTokenRef.current()) ?? ''
        ws.send(
          JSON.stringify({
            regenerate: true,
            conversation_id: conversationIdRef.current,
            id_token,
          }),
        )
      })()
    }

    ws.onmessage = (evt) => {
      if (stopRequestedRef.current) return
      let data: WsInbound
      try {
        data = JSON.parse(evt.data) as WsInbound
      } catch {
        return
      }

      switch (data.type) {
        case 'info':
          conversationIdRef.current = data.conversation_id
          setConversationId(data.conversation_id)
          break
        case 'agent_trace':
          setLastAgentTrace({
            steps: data.steps,
            observability_trace_id: data.observability_trace_id,
          })
          break
        case 'message_id':
          pendingMessageIdRef.current = data.message_id
          break
        case 'status':
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    agentStatus: data.content || null,
                  }
                : m,
            ),
          )
          break
        case 'token':
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: m.content + data.content,
                    awaitingFirstToken: false,
                    agentStatus: null,
                  }
                : m,
            ),
          )
          break
        case 'done':
          finishAssistantTurn(assistantId)
          break
        case 'error':
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: data.content,
                    error: true,
                    awaitingFirstToken: false,
                    agentStatus: null,
                  }
                : m,
            ),
          )
          finishAssistantTurn(assistantId)
          break
      }
    }

    ws.onerror = () => {
      setWsConnected(false)
    }

    ws.onclose = () => {
      if (wsRef.current !== ws) return
      wsRef.current = null
      setWsConnected(false)
      setIsStreaming(false)
    }
  }, [isStreaming, finishAssistantTurn])

  return {
    messages,
    sendMessage,
    regenerate,
    conversationId,
    stop,
    newChat,
    isStreaming,
    wsConnected,
    lastAgentTrace,
  }
}
