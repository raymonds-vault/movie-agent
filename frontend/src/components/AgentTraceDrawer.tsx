import { useMemo } from 'react'
import {
  Button,
  Drawer,
  Empty,
  Space,
  Timeline,
  Typography,
} from 'antd'
import { LinkOutlined } from '@ant-design/icons'
import type { AgentTracePayload } from '../types/chat'

const { Text, Paragraph } = Typography

const defaultLangfuseHost = 'http://localhost:3000'

function langfuseBaseUrl(): string {
  const v = import.meta.env.VITE_LANGFUSE_HOST as string | undefined
  if (v && v.trim()) return v.replace(/\/$/, '')
  return defaultLangfuseHost
}

function formatTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ''
  }
}

function stepColor(phase?: string): 'blue' | 'green' | 'gray' | 'orange' | 'red' {
  if (!phase) return 'blue'
  if (phase.startsWith('tool')) return 'orange'
  if (phase === 'llm_start') return 'green'
  if (phase === 'node_end') return 'gray'
  return 'blue'
}

export function AgentTraceDrawer(props: {
  open: boolean
  onClose: () => void
  trace: AgentTracePayload | null
}) {
  const { open, onClose, trace } = props
  const langfuseUrl = langfuseBaseUrl()

  const items = useMemo(() => {
    if (!trace?.steps?.length) return []
    return trace.steps.map((s, i) => {
      const label = s.label || s.name || s.event || 'step'
      const detail = s.detail
      const time = formatTime(s.ts)
      return {
        key: `${i}-${s.ts}-${label}`,
        color: stepColor(s.phase),
        children: (
          <div className="text-xs">
            <div className="flex flex-wrap items-baseline gap-2">
              <Text strong className="!text-gray-900">
                {s.phase ? `${s.phase}: ` : ''}
                {label}
              </Text>
              {time ? (
                <Text type="secondary" className="!text-[10px]">
                  {time}
                </Text>
              ) : null}
            </div>
            {detail ? (
              <Paragraph
                className="!mb-0 !mt-1 !text-gray-600 whitespace-pre-wrap break-words max-h-32 overflow-y-auto"
                copyable={{ text: detail }}
              >
                {detail}
              </Paragraph>
            ) : null}
          </div>
        ),
      }
    })
  }, [trace])

  return (
    <Drawer
      title="Agent run trace"
      placement="right"
      width={420}
      onClose={onClose}
      open={open}
      styles={{ body: { paddingTop: 12 } }}
    >
      <Space direction="vertical" size="middle" className="w-full">
        <Text type="secondary" className="text-xs">
          Execution timeline from LangGraph (
          <code className="text-[11px]">astream_events</code>). With Langfuse enabled,
          full LLM/tool spans appear in the Langfuse UI.
        </Text>
        {trace?.observability_trace_id ? (
          <div className="flex flex-wrap items-center gap-2">
            <Text className="text-xs shrink-0">Trace id:</Text>
            <Text code className="text-[11px] break-all">
              {trace.observability_trace_id}
            </Text>
            <Button
              type="link"
              size="small"
              className="!px-0"
              href={langfuseUrl}
              target="_blank"
              rel="noreferrer"
              icon={<LinkOutlined />}
            >
              Open Langfuse
            </Button>
          </div>
        ) : null}
        {!trace?.steps?.length ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No trace yet — send a message while not on cache hit."
          />
        ) : (
          <Timeline mode="left" items={items} className="!mt-2" />
        )}
      </Space>
    </Drawer>
  )
}
