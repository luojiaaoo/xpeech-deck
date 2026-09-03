import { Button, Modal, Tag, Typography, message } from 'antd'
import type { ComposeResult } from './types'

interface Props {
  open: boolean
  result: ComposeResult | null
  onClose: () => void
  title?: string
  width?: number | string
}

function copy(text: string): void {
  if (!text) {
    message.info('内容为空')
    return
  }
  navigator.clipboard
    ?.writeText(text)
    .then(
      () => message.success('已复制'),
      () => message.error('复制失败'),
    )
}

function OutputBlock({ title, content }: { title: string; content: string }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Text strong>{title}</Typography.Text>
        <Button size="small" onClick={() => copy(content)}>
          复制
        </Button>
      </div>
      <pre className="command-output">{content || '(空)'}</pre>
    </div>
  )
}

export default function CommandResultModal({
  open,
  result,
  onClose,
  title = '命令执行结果',
  width = 720,
}: Props) {
  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      onOk={onClose}
      okText="关闭"
      cancelButtonProps={{ style: { display: 'none' } }}
      width={width}
    >
      {result && (
        <div>
          <p style={{ marginBottom: 8 }}>
            {result.success ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag>}
            <span style={{ marginLeft: 8 }}>退出码：{result.exit_code}</span>
          </p>
          <OutputBlock title="标准输出（stdout）：" content={result.stdout} />
          <OutputBlock title="错误输出（stderr）：" content={result.stderr} />
        </div>
      )}
    </Modal>
  )
}
