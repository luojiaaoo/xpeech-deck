import { useEffect, useRef, useState } from 'react'
import { Button, Modal, Space, Tag, Typography } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import * as api from './api'
import type { ConsoleEvent } from './types'

interface Props {
  open: boolean
  onClose: () => void
}

function timeOf(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString([], { hour12: false })
}

export default function SystemConsoleModal({ open, onClose }: Props) {
  const [events, setEvents] = useState<ConsoleEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')
  const outputRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setEvents([])
    setConnected(false)
    setError('')
    void api.streamConsole(
      controller.signal,
      (event) => setEvents((current) => [...current, event]),
      () => setConnected(true),
    ).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      setConnected(false)
      setError(reason instanceof Error ? reason.message : String(reason))
    })
    return () => controller.abort()
  }, [open])

  useEffect(() => {
    const output = outputRef.current
    if (output) output.scrollTop = output.scrollHeight
  }, [events])

  return (
    <Modal
      title={
        <Space>
          <span>System Console</span>
          {connected ? <Tag color="success">实时连接</Tag> : <Tag color="default">未连接</Tag>}
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={980}
      footer={[
        <Button key="clear" icon={<DeleteOutlined />} onClick={() => setEvents([])}>
          清空显示
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
      ]}
    >
      <div ref={outputRef} className="system-console" aria-live="polite">
        {events.length === 0 && !error ? (
          <div className="console-empty">等待命令执行…</div>
        ) : null}
        {events.map((event) => (
          <div key={event.sequence} className={`console-line console-${event.kind}`}>
            <span className="console-time">[{timeOf(event.timestamp)}]</span>
            <span className="console-source">[{event.source}]</span>
            <span className="console-text">{event.text}</span>
          </div>
        ))}
        {error ? <div className="console-line console-stderr">连接失败：{error}</div> : null}
      </div>
      <Typography.Text type="secondary">
        历史从服务端 JSONL 日志文件读取，并继续显示 Git / Docker 实时输出；
        「清空显示」不会删除日志文件。
      </Typography.Text>
    </Modal>
  )
}
