import { useEffect, useState } from 'react'
import { Modal, Spin, Tabs, message } from 'antd'
import * as api from './api'
import LineNumberEditor from './LineNumberEditor'

interface Props {
  open: boolean
  instanceName: string
  onCancel: () => void
  onSaved: () => void
}

export default function ConfigInstanceModal({ open, instanceName, onCancel, onSaved }: Props) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [envContent, setEnvContent] = useState('')
  const [confToml, setConfToml] = useState('')

  // 打开时读取实例配置原文
  useEffect(() => {
    if (!open || !instanceName) return
    let active = true
    setLoading(true)
    setLoaded(false)
    setEnvContent('')
    setConfToml('')
    api
      .getConfig(instanceName)
      .then((c) => {
        if (!active) return
        setEnvContent(c.env_content)
        setConfToml(c.conf_toml)
        setLoaded(true)
      })
      .catch((e) => {
        if (active) message.error(String(e instanceof Error ? e.message : e))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [open, instanceName])

  const handleSave = async () => {
    if (!loaded || loading || saving) return
    setSaving(true)
    try {
      await api.saveConfig(instanceName, {
        env_content: envContent,
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
      onCancel={() => !saving && onCancel()}
      onOk={() => void handleSave()}
      confirmLoading={saving}
      okButtonProps={{ disabled: loading || !loaded }}
      cancelButtonProps={{ disabled: saving }}
      okText="保存"
      cancelText="取消"
      width={960}
    >
      <Spin spinning={loading}>
        <Tabs
          defaultActiveKey="conf.toml"
          items={[
            { key: 'conf.toml', label: 'conf.toml', children: (
              <LineNumberEditor
                label="conf.toml"
                value={confToml}
                onChange={setConfToml}
                rows={24}
                disabled={!loaded || saving}
              />
            ) },
            { key: '.env', label: '.env', children: (
              <LineNumberEditor
                label=".env"
                value={envContent}
                onChange={setEnvContent}
                rows={24}
                disabled={!loaded || saving}
              />
            ) },
          ]}
        />
      </Spin>
    </Modal>
  )
}
