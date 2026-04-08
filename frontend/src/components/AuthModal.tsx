import { Modal } from 'antd'
import { LoginFormContent } from './LoginFormContent'

export type AuthModalProps = {
  open: boolean
  onClose: () => void
  title?: string
}

export function AuthModal({ open, onClose, title = 'Sign in to save feedback' }: AuthModalProps) {
  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnClose
      width={440}
      centered
      title={null}
    >
      <LoginFormContent subtitle={title} onSuccess={onClose} />
    </Modal>
  )
}
