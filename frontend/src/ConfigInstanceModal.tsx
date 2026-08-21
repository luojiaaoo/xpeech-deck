import { useEffect, useState } from 'react'
import { Form, Input, Modal, Spin, message } from 'antd'
import * as api from './api'

interface Props {
  open: boolean
  instanceName: string
  onCancel: () => void
  onSaved: () => void
}

export default function ConfigInstanceModal({ open, instanceName, onCancel, onSaved }: Props) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [backendPort, setBackendPort] = useState('')
  const [webClientPort, setWebClientPort] = useState('')
  const [confToml, setConfToml] = useState('')

  // 打开时读取实例配置原文
  useEffect(() => {
    if (!open || !instanceName) return
    setLoading(true)
    api
      .getConfig(instanceName)
      .then((c) => {
        setBackendPort(String(c.backend_port))
        setWebClientPort(String(c.web_client_port))
        setConfToml(c.conf_toml)
      })
      .catch((e) => message.error(String(e instanceof Error ? e.message : e)))
      .finally(() => setLoading(false))
  }, [open, instanceName])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.saveConfig(instanceName, {
        backend_port: backendPort.trim(),
        web_client_port: webClientPort.trim(),
        conf_toml: confToml,
      })
      message.success('配置已保存')
      onSaved()
    } catch (e) {
      message.error(String(e instanceof Error ? e.message : e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`配置实例：${instanceName}`}
      open={open}
      onCancel={onCancel}
      onOk={() => void handleSave()}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      width={720}
    >
      <Spin spinning={loading}>
        <Form layout="vertical">
          <Form.Item label="实例名">
            <Input value={instanceName} disabled />
          </Form.Item>
          <Form.Item label="Backend 端口">
            <Input value={backendPort} onChange={(e) => setBackendPort(e.target.value)} />
          </Form.Item>
          <Form.Item label="Web Client 端口">
            <Input value={webClientPort} onChange={(e) => setWebClientPort(e.target.value)} />
          </Form.Item>
          <Form.Item label="conf.toml">
            <Input.TextArea
              className="mono"
              value={confToml}
              onChange={(e) => setConfToml(e.target.value)}
              rows={18}
              spellCheck={false}
            />
          </Form.Item>
        </Form>
      </Spin>
    </Modal>
  )
}
