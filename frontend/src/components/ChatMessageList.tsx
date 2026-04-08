import { App, Button, Skeleton, Tag, Typography } from 'antd'
import {
  CopyOutlined,
  DislikeOutlined,
  LikeOutlined,
  LoadingOutlined,
  ReloadOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../types/chat'
import { submitMessageFeedback } from '../api/feedback'
import { useAuth } from '../contexts/AuthContext'
import { authDevBypass } from '../firebase'

const { Text } = Typography

export interface ChatMessageListProps {
  messages: ChatMessage[]
  onScrollState?: (nearBottom: boolean) => void
  scrollToBottomSignal?: number
  /** Re-run the last user message (same conversation). */
  onRegenerate?: () => void
  canRegenerate?: boolean
  lastAssistantId?: string | null
  /** When set, like/dislike without login opens sign-in (not used with dev bypass). */
  onRequestSignIn?: () => void
}

export function ChatMessageList({
  messages,
  onScrollState,
  scrollToBottomSignal = 0,
  onRegenerate,
  canRegenerate,
  lastAssistantId,
  onRequestSignIn,
}: ChatMessageListProps) {
  const { message: antMessage } = App.useApp()
  const { getIdToken, user } = useAuth()
  const containerRef = useRef<HTMLDivElement>(null)
  const [feedbackVote, setFeedbackVote] = useState<
    Record<string, 'up' | 'down' | undefined>
  >({})

  const scrollBottom = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [])

  useEffect(() => {
    scrollBottom()
  }, [messages, scrollBottom, scrollToBottomSignal])

  const onScroll = useCallback(() => {
    const el = containerRef.current
    if (!el || !onScrollState) return
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 80
    onScrollState(nearBottom)
  }, [onScrollState])

  const onFeedback = useCallback(
    async (messageId: string, isLiked: boolean) => {
      if (!authDevBypass && !user) {
        onRequestSignIn?.()
        return
      }
      const key = isLiked ? 'up' : 'down'
      setFeedbackVote((prev) => ({ ...prev, [messageId]: key }))
      try {
        await submitMessageFeedback(messageId, isLiked, getIdToken)
      } catch {
        setFeedbackVote((prev) => {
          const next = { ...prev }
          delete next[messageId]
          return next
        })
        antMessage.error('Could not save feedback')
      }
    },
    [antMessage, getIdToken, user, onRequestSignIn],
  )

  const copyText = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      antMessage.success('Copied')
    } catch {
      antMessage.error('Copy failed')
    }
  }, [antMessage])

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className="flex-1 min-h-0 w-full overflow-y-auto bg-[#f7f8fc]"
    >
      <div className="mx-auto w-full max-w-7xl space-y-5 px-6 py-6 sm:px-10 sm:py-8 lg:px-12">
      {messages.map((m) =>
        m.role === 'user' ? (
          <div key={m.id} className="flex w-full justify-end">
            <div className="max-w-[min(92%,42rem)] rounded-2xl px-4 py-3.5 text-sm bg-[#FCE4EC] text-[#880E4F] shadow-sm border border-pink-200/80">
              <p className="m-0 whitespace-pre-wrap leading-relaxed">{m.content}</p>
            </div>
          </div>
        ) : (
          <div key={m.id} className="w-full max-w-[min(100%,56rem)]">
            <div className="flex gap-2 items-start mb-1.5 text-pink-500">
              <RobotOutlined />
              <Text className="text-xs !text-pink-600 font-medium">
                CinemaBot
              </Text>
            </div>
            <div className="rounded-2xl px-4 py-3.5 text-sm border border-gray-200/90 bg-white text-gray-900 shadow-sm">
              {m.agentStatus ? (
                <Tag
                  icon={<LoadingOutlined spin />}
                  className="!mb-2 !rounded-full !border-pink-200 !bg-pink-50 !text-pink-700"
                >
                  {m.agentStatus}
                </Tag>
              ) : null}
              {m.awaitingFirstToken && !m.error && !m.stopped ? (
                <Skeleton
                  active
                  paragraph={{ rows: 3 }}
                  title={false}
                  className="!mt-1"
                />
              ) : null}
              {m.stopped ? (
                <Text type="secondary">
                  <em>Response stopped by user.</em>
                </Text>
              ) : null}
              {m.error ? (
                <Text type="danger">{m.content}</Text>
              ) : null}
              {!m.error && !m.stopped && m.content ? (
                <div className="cinemabot-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {m.content}
                  </ReactMarkdown>
                </div>
              ) : null}
              {m.messageId && m.content && !m.error && !m.stopped ? (
                <div className="flex items-center flex-wrap gap-1 mt-3 pt-2 border-t border-pink-50">
                  <Button
                    type="text"
                    size="small"
                    className={
                      feedbackVote[m.messageId!] === 'up'
                        ? '!text-pink-600'
                        : '!text-gray-400'
                    }
                    icon={<LikeOutlined />}
                    onClick={() => onFeedback(m.messageId!, true)}
                  />
                  <Button
                    type="text"
                    size="small"
                    className={
                      feedbackVote[m.messageId!] === 'down'
                        ? '!text-pink-600'
                        : '!text-gray-400'
                    }
                    icon={<DislikeOutlined />}
                    onClick={() => onFeedback(m.messageId!, false)}
                  />
                  <Button
                    type="text"
                    size="small"
                    className="!text-gray-400"
                    icon={<CopyOutlined />}
                    onClick={() => copyText(m.content)}
                  />
                  {canRegenerate &&
                  onRegenerate &&
                  lastAssistantId === m.id ? (
                    <Button
                      type="text"
                      size="small"
                      className="!text-gray-500"
                      icon={<ReloadOutlined />}
                      onClick={onRegenerate}
                    >
                      Regenerate
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        ),
      )}
      </div>
    </div>
  )
}
