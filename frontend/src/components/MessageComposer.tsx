import { Button, Input } from 'antd'
import {
  AppstoreOutlined,
  AudioOutlined,
  BulbOutlined,
  FileTextOutlined,
  SendOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'

export interface MessageComposerProps {
  value: string
  onChange: (value: string) => void
  disabled: boolean
  isStreaming: boolean
  onSend: () => void
  onStop: () => void
}

export function MessageComposer({
  value,
  onChange,
  disabled,
  isStreaming,
  onSend,
  onStop,
}: MessageComposerProps) {
  const append = (snippet: string) => {
    onChange(value ? `${value.trimEnd()} ${snippet}` : snippet)
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button
          size="small"
          className="saas-quick-pill h-8"
          icon={<AppstoreOutlined />}
          onClick={() => append('Suggest movies by theme: ')}
        >
          Segments
        </Button>
        <Button
          size="small"
          className="saas-quick-pill h-8"
          icon={<FileTextOutlined />}
          onClick={() => append('Tell me about the plot of: ')}
        >
          Files
        </Button>
        <Button
          size="small"
          className="saas-quick-pill h-8"
          icon={<BulbOutlined />}
          onClick={() => append('Movie trivia question: ')}
        >
          Questions
        </Button>
      </div>

      <div
        className={`flex items-end gap-1 rounded-2xl border px-2 py-1.5 bg-white ${
          disabled
            ? 'border-pink-100 opacity-90'
            : 'border-pink-200/90 shadow-sm'
        }`}
      >
        <Button
          type="text"
          className="!text-pink-400 shrink-0"
          icon={<ThunderboltOutlined className="text-lg" />}
          title="Suggestions"
        />
        <Input.TextArea
          className="flex-1 !max-h-36 !shadow-none !border-none !bg-transparent !px-1 !py-2 text-gray-800"
          placeholder="Ask anything about movies, or describe what you want…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          autoSize={{ minRows: 1, maxRows: 6 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              if (!isStreaming && value.trim()) onSend()
            }
          }}
        />
        <Button
          type="text"
          className="!text-gray-400 shrink-0"
          icon={<AudioOutlined className="text-lg" />}
          title="Voice (not connected)"
          disabled
        />
        {isStreaming ? (
          <Button
            danger
            shape="circle"
            className="shrink-0"
            icon={<StopOutlined />}
            onClick={onStop}
          />
        ) : (
          <Button
            shape="circle"
            type="primary"
            className="saas-cta-gradient shrink-0 w-10 h-10 flex items-center justify-center p-0"
            icon={<SendOutlined />}
            onClick={() => value.trim() && onSend()}
            disabled={!value.trim()}
          />
        )}
      </div>
    </div>
  )
}
