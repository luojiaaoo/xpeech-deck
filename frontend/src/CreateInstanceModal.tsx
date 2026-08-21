import { useState } from 'react'
import { Form, Input, Modal } from 'antd'

interface Props {
  open: boolean
  onCancel: () => void
  onCreate: (name: string) => Promise<void>
}

export default function CreateInstanceModal({ open, onCancel, onCreate }: Props) {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const handleCancel = () => {
    form.resetFields()
    onCancel()
  }

  const handleFinish = async () => {
    const name = (form.getFieldValue('name') as string | undefined)?.trim() ?? ''
    setSubmitting(true)
    try {
      await onCreate(name)
      form.resetFields()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="添加实例"
      open={open}
      onCancel={handleCancel}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      okText="创建"
      cancelText="取消"
    >
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item
          name="name"
          label="实例名"
          rules={[
            { required: true, message: '请输入实例名' },
            {
              pattern: /^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$/,
              message: '只能由字母、数字、下划线和连字符组成，以字母或数字开头，最长 63 字符',
            },
          ]}
        >
          <Input placeholder="例如 demo01" autoFocus maxLength={63} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
