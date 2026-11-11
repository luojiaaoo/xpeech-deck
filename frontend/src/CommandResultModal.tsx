import { Button, Modal, Tag, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ComposeResult } from './types'

interface Props {
  open: boolean
  result: ComposeResult | null
  onClose: () => void
  title?: string
  width?: number | string
  onRefresh?: () => void
  refreshing?: boolean
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

function OutputBlock({ title, content, showCopy }: { title: string; content: string; showCopy: boolean }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Text strong>{title}</Typography.Text>
        {showCopy && (
          <Button size="small" onClick={() => copy(content)}>
            复制
          </Button>
        )}
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
  onRefresh,
  refreshing = false,
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span>
              {result.success ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag>}
              <span style={{ marginLeft: 8 }}>退出码：{result.exit_code}</span>
            </span>
            {onRefresh && (
              <Button size="small" icon={<ReloadOutlined />} loading={refreshing} onClick={onRefresh}>
                刷新
              </Button>
            )}
          </div>
          <OutputBlock title="标准输出（stdout）：" content={result.stdout} showCopy={!onRefresh} />
          <OutputBlock title="错误输出（stderr）：" content={result.stderr} showCopy={!onRefresh} />
        </div>
      )}
    </Modal>
  )
}
