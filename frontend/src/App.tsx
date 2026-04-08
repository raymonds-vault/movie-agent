import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  App as AntApp,
  Button,
  ConfigProvider,
  FloatButton,
  Layout,
  Typography,
} from 'antd'
import {
  LoginOutlined,
  MenuOutlined,
  PlusOutlined,
  RobotOutlined,
  VerticalAlignBottomOutlined,
  LineChartOutlined,
} from '@ant-design/icons'
import { useChatWebSocket } from './hooks/useChatWebSocket'
import { ChatMessageList } from './components/ChatMessageList'
import { MessageComposer } from './components/MessageComposer'
import { AgentTraceDrawer } from './components/AgentTraceDrawer'
import { AuthModal } from './components/AuthModal'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { authDevBypass } from './firebase'
import { buildAntdTheme } from './theme'

const { Header, Content } = Layout
const { Text } = Typography

function AppShell() {
  const { getIdToken, logOut, user } = useAuth()
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const prevUidRef = useRef<string | null>(null)

  const {
    messages,
    sendMessage,
    regenerate,
    stop,
    newChat,
    isStreaming,
    lastAgentTrace,
    conversationId,
  } = useChatWebSocket(getIdToken)

  useEffect(() => {
    if (authDevBypass) return
    const uid = user?.uid ?? null
    if (uid === null) {
      prevUidRef.current = null
      return
    }
    if (!prevUidRef.current && conversationId) {
      newChat()
    }
    prevUidRef.current = uid
  }, [user, conversationId, newChat])

  const lastAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.role === 'assistant' && m.id !== 'welcome') return m.id
    }
    return null
  }, [messages])

  const canRegenerate =
    !isStreaming &&
    !!conversationId &&
    lastAssistantId !== null &&
    messages.some(
      (m) =>
        m.id === lastAssistantId &&
        !!m.content?.trim() &&
        !m.error &&
        !m.stopped,
    )

  const [traceDrawerOpen, setTraceDrawerOpen] = useState(false)
  const [input, setInput] = useState('')
  const [nearBottom, setNearBottom] = useState(true)
  const [scrollTick, setScrollTick] = useState(0)

  const onSend = useCallback(() => {
    const t = input.trim()
    if (!t) return
    sendMessage(t)
    setInput('')
    setScrollTick((x) => x + 1)
  }, [input, sendMessage])

  const onNewChat = useCallback(() => {
    newChat()
    setInput('')
    setScrollTick((x) => x + 1)
  }, [newChat])

  const handleSignOut = useCallback(async () => {
    await logOut()
    newChat()
  }, [logOut, newChat])

  useEffect(() => {
    document.documentElement.classList.remove('dark')
    document.documentElement.style.colorScheme = 'light'
  }, [])

  return (
    <div className="saas-app-shell flex h-dvh min-h-0 w-full flex-col overflow-hidden">
      <Layout className="!flex !h-full !min-h-0 !w-full !flex-col !bg-transparent">
        <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden bg-white">
          <Header className="saas-web-header !flex !h-14 !items-center !justify-between !px-6 !py-0 !leading-[3.5rem] sm:!px-10 lg:!px-12 shrink-0 !border-b !border-pink-100/90 !bg-white">
            <div className="flex items-center gap-3 min-w-0">
              <Button
                type="text"
                icon={<MenuOutlined className="text-gray-600" />}
                aria-label="Menu"
              />
              <div className="flex items-center gap-2 min-w-0">
                <RobotOutlined className="text-pink-500 text-lg shrink-0" />
                <Text className="!text-gray-900 font-semibold !mb-0 truncate text-base">
                  CinemaBot
                </Text>
                <Text type="secondary" className="!mb-0 hidden sm:inline text-xs">
                  AI Movie Agent
                </Text>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!authDevBypass && user && (
                <Text type="secondary" className="!mb-0 hidden md:inline text-xs max-w-[140px] truncate">
                  {user.email}
                </Text>
              )}
              {!authDevBypass && !user ? (
                <Button
                  size="small"
                  type="primary"
                  icon={<LoginOutlined />}
                  onClick={() => setAuthModalOpen(true)}
                >
                  Sign in
                </Button>
              ) : null}
              <Button
                size="small"
                type="text"
                icon={<LineChartOutlined className="text-gray-600" />}
                onClick={() => setTraceDrawerOpen(true)}
                aria-label="Agent trace"
              >
                Trace
              </Button>
              <Button
                size="small"
                icon={<PlusOutlined className="text-xs" />}
                onClick={onNewChat}
                className="!rounded-full !bg-[#FCE4EC] !text-[#AD1457] !border !border-pink-200 hover:!border-pink-400"
              >
                New +
              </Button>
              {!authDevBypass && user ? (
                <Button size="small" type="default" onClick={() => void handleSignOut()}>
                  Sign out
                </Button>
              ) : null}
            </div>
          </Header>

          <Content className="!flex !min-h-0 !flex-1 !flex-col !overflow-hidden !bg-transparent">
            <ChatMessageList
              messages={messages}
              onScrollState={setNearBottom}
              scrollToBottomSignal={scrollTick}
              onRegenerate={regenerate}
              canRegenerate={canRegenerate}
              lastAssistantId={lastAssistantId}
              onRequestSignIn={() => setAuthModalOpen(true)}
            />
            <div className="saas-web-composer shrink-0 border-t border-pink-100/90 bg-[#fafbfd] px-6 py-4 sm:px-10 lg:px-12">
              <div className="mx-auto w-full max-w-7xl">
                <MessageComposer
                  value={input}
                  onChange={setInput}
                  disabled={isStreaming}
                  isStreaming={isStreaming}
                  onSend={onSend}
                  onStop={stop}
                />
                <p className="text-center text-[11px] text-gray-400 mt-3 mb-0">
                  LangGraph · LangChain · OMDb · Redis
                </p>
              </div>
            </div>
          </Content>
        </div>

        {!nearBottom ? (
          <FloatButton
            icon={<VerticalAlignBottomOutlined />}
            tooltip="Scroll to bottom"
            onClick={() => setScrollTick((x) => x + 1)}
            className="saas-float-cta"
            style={{ right: 32, bottom: 32 }}
          />
        ) : null}

        <AgentTraceDrawer
          open={traceDrawerOpen}
          onClose={() => setTraceDrawerOpen(false)}
          trace={lastAgentTrace}
        />

        <AuthModal open={authModalOpen} onClose={() => setAuthModalOpen(false)} />
      </Layout>
    </div>
  )
}

export default function App() {
  return (
    <ConfigProvider theme={buildAntdTheme()}>
      <AuthProvider>
        <AntApp>
          <AppShell />
        </AntApp>
      </AuthProvider>
    </ConfigProvider>
  )
}
