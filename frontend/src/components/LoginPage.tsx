import { Card } from 'antd'
import { LoginFormContent } from './LoginFormContent'

export function LoginPage() {
  return (
    <div className="min-h-dvh flex items-center justify-center bg-gradient-to-b from-pink-50/80 to-white px-4">
      <Card className="w-full max-w-md shadow-lg border-pink-100">
        <LoginFormContent />
      </Card>
    </div>
  )
}
