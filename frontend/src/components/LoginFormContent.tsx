import { useState } from 'react'
import { Button, Divider, Form, Input, Typography, message } from 'antd'
import { GoogleOutlined, RobotOutlined } from '@ant-design/icons'
import { useAuth } from '../contexts/AuthContext'

const { Title, Text } = Typography

export type LoginFormContentProps = {
  /** Shown under the title */
  subtitle?: string
  /** Called after successful sign-in (e.g. close modal) */
  onSuccess?: () => void
}

export function LoginFormContent({
  subtitle = 'Sign in to continue',
  onSuccess,
}: LoginFormContentProps) {
  const { signInWithEmail, signUpWithEmail, signInWithGoogle } = useAuth()
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [submitting, setSubmitting] = useState(false)

  const onFinish = async (values: { email: string; password: string }) => {
    setSubmitting(true)
    try {
      if (mode === 'signin') {
        await signInWithEmail(values.email, values.password)
      } else {
        await signUpWithEmail(values.email, values.password)
      }
      message.success(mode === 'signin' ? 'Signed in' : 'Account created')
      onSuccess?.()
    } catch (e: unknown) {
      const err = e as { message?: string }
      message.error(err?.message || 'Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  const onGoogle = async () => {
    setSubmitting(true)
    try {
      await signInWithGoogle()
      message.success('Signed in with Google')
      onSuccess?.()
    } catch (e: unknown) {
      const err = e as { message?: string }
      message.error(err?.message || 'Google sign-in failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="text-center mb-6">
        <RobotOutlined className="text-4xl text-pink-500 mb-2" />
        <Title level={3} className="!mb-1">
          CinemaBot
        </Title>
        <Text type="secondary">{subtitle}</Text>
      </div>

      <Button
        block
        size="large"
        icon={<GoogleOutlined />}
        onClick={onGoogle}
        loading={submitting}
        className="mb-4"
      >
        Continue with Google
      </Button>

      <Divider plain>or email</Divider>

      <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
        <Form.Item
          name="email"
          label="Email"
          rules={[{ required: true, type: 'email', message: 'Valid email required' }]}
        >
          <Input size="large" placeholder="you@example.com" autoComplete="email" />
        </Form.Item>
        <Form.Item
          name="password"
          label="Password"
          rules={[{ required: true, min: 6, message: 'At least 6 characters' }]}
        >
          <Input.Password
            size="large"
            placeholder="Password"
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
          />
        </Form.Item>
        <Form.Item className="!mb-2">
          <Button type="primary" htmlType="submit" block size="large" loading={submitting}>
            {mode === 'signin' ? 'Sign in' : 'Create account'}
          </Button>
        </Form.Item>
      </Form>

      <div className="text-center mt-4">
        <Button type="link" onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}>
          {mode === 'signin' ? 'Need an account? Sign up' : 'Have an account? Sign in'}
        </Button>
      </div>
    </div>
  )
}
