import { useCallback, useEffect, useState } from 'react'
import { Button, Layout, Modal, Result, Typography, message } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import InstanceTable, { type Action } from './InstanceTable'
import CreateInstanceModal from './CreateInstanceModal'
import ConfigInstanceModal from './ConfigInstanceModal'
import CommandResultModal from './CommandResultModal'
import * as api from './api'
import type { ComposeResult, Instance } from './types'

const { Header, Content } = Layout

interface Busy {
  name: string
  action: Action
}

export default function App() {
  const [token, setToken] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const [instances, setInstances] = useState<Instance[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<Busy | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [configName, setConfigName] = useState<string | null>(null)
  const [result, setResult] = useState<ComposeResult | null>(null)
  const [resultOpen, setResultOpen] = useState(false)

  // 从 URL 查询参数读取 Token，只保存在内存中，并清除地址栏
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const t = params.get('token')
    if (t) {
      api.setToken(t)
      history.replaceState(null, '', window.location.pathname)
    }
    setToken(t)
    setReady(true)
  }, [])

  const showError = useCallback((e: unknown) => {
    message.error(String(e instanceof Error ? e.message : e))
  }, [])

  const loadInstances = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listInstances()
      setInstances(data.instances)
    } catch (e) {
      if (e instanceof api.ApiError && e.status === 401) {
        api.setToken(null)
        setToken(null)
        message.error('Token 无效，请重新使用带有 ?token=xxx 的地址打开')
      } else {
        showError(e)
      }
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => {
    if (token) void loadInstances()
  }, [token, loadInstances])

  const handleCreate = async (name: string) => {
    try {
      await api.createInstance(name)
      message.success('实例创建成功')
      setCreateOpen(false)
      await loadInstances()
    } catch (e) {
      showError(e)
    }
  }

  const handleConfigSaved = async () => {
    setConfigName(null)
    await loadInstances()
  }

  const runCommand = async (instance: Instance, action: Action) => {
    setBusy({ name: instance.name, action })
    try {
      const r = await api.compose(instance.name, action)
      setResult(r)
      setResultOpen(true)
    } catch (e) {
      showError(e)
    } finally {
      setBusy(null)
    }
  }

  const handleCommand = (instance: Instance, action: Action) => {
    if (action === 'down') {
      Modal.confirm({
        title: '确定要执行 docker compose down 吗？',
        onOk: () => runCommand(instance, action),
      })
    } else {
      void runCommand(instance, action)
    }
  }

  if (ready && !token) {
    return (
      <Layout style={{ minHeight: '100vh' }}>
        <Content style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Result
            status="warning"
            title="缺少访问 Token"
            subTitle="请重新使用带有 ?token=xxx 的地址打开。"
          />
        </Content>
      </Layout>
    )
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <Typography.Title level={3} style={{ color: '#fff', margin: 0 }}>
            Xpeech Deck
          </Typography.Title>
          <Typography.Text style={{ color: 'rgba(255,255,255,0.75)' }}>
            Xpeech 多实例管理
          </Typography.Text>
        </div>
        <div>
          <Button style={{ marginRight: 12 }} icon={<ReloadOutlined />} onClick={() => void loadInstances()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            添加实例
          </Button>
        </div>
      </Header>
      <Content style={{ padding: 24 }}>
        <InstanceTable
          instances={instances}
          loading={loading}
          busy={busy}
          onConfig={(name) => setConfigName(name)}
          onCommand={handleCommand}
        />
      </Content>
      <CreateInstanceModal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onCreate={handleCreate}
      />
      <ConfigInstanceModal
        open={configName !== null}
        instanceName={configName ?? ''}
        onCancel={() => setConfigName(null)}
        onSaved={handleConfigSaved}
      />
      <CommandResultModal open={resultOpen} result={result} onClose={() => setResultOpen(false)} />
    </Layout>
  )
}
