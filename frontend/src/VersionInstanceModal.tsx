import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Form, Modal, Select, Space, Spin, Tag, Typography, message } from 'antd'
import { CloudDownloadOutlined } from '@ant-design/icons'
import * as api from './api'
import type { InstanceVersions } from './types'

interface Props {
  open: boolean
  instanceName: string
  onCancel: () => void
  onSwitched: () => void
}

export default function VersionInstanceModal({ open, instanceName, onCancel, onSwitched }: Props) {
  const [data, setData] = useState<InstanceVersions | null>(null)
  const [selectedRef, setSelectedRef] = useState<string>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [fetching, setFetching] = useState(false)
  const session = useRef(0)

  useEffect(() => {
    if (!open || !instanceName) return
    let active = true
    session.current += 1
    setFetching(false)
    setSubmitting(false)
    setLoading(true)
    setData(null)
    setSelectedRef(undefined)
    api
      .getVersions(instanceName)
      .then((value) => {
        if (!active) return
        setData(value)
        if (value.versions.some((item) => item.ref === value.current_ref)) {
          setSelectedRef(value.current_ref)
        }
      })
      .catch((error: unknown) => {
        if (active) message.error(String(error instanceof Error ? error.message : error))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      session.current += 1
    }
  }, [open, instanceName])

  const handleFetch = async () => {
    if (loading || fetching || submitting) return
    const requestSession = session.current
    setFetching(true)
    try {
      const result = await api.fetchInstance(instanceName)
      if (requestSession !== session.current) return
      if (!result.success) throw new Error(result.stderr || result.stdout || '拉取最新版本失败')
      const value = await api.getVersions(instanceName)
      if (requestSession !== session.current) return
      setData(value)
      setSelectedRef((previous) =>
        value.versions.some((item) => item.ref === previous) ? previous : undefined,
      )
      message.success('最新版本已拉取，可选择目标版本进行切换')
    } catch (error) {
      if (requestSession === session.current) {
        message.error(error instanceof Error ? error.message : String(error))
      }
    } finally {
      if (requestSession === session.current) setFetching(false)
    }
  }

  const handleSwitch = async () => {
    if (!selectedRef || loading || fetching || submitting) return
    const requestSession = session.current
    setSubmitting(true)
    try {
      const result = await api.switchVersion(instanceName, selectedRef)
      if (requestSession !== session.current) return
      message.success(`已切换到 ${result.current_label} (${result.current_commit})`)
      onSwitched()
    } catch (error) {
      if (requestSession === session.current) {
        message.error(String(error instanceof Error ? error.message : error))
      }
    } finally {
      if (requestSession === session.current) setSubmitting(false)
    }
  }

  const kindLabel = (kind: 'branch' | 'tag' | 'commit') => {
    if (kind === 'tag') return 'Tag'
    if (kind === 'branch') return 'Branch'
    return 'Commit'
  }

  const kindColor = (kind: 'branch' | 'tag' | 'commit') => {
    if (kind === 'tag') return 'gold'
    if (kind === 'branch') return 'blue'
    return 'default'
  }

  return (
    <Modal
      title={`切换版本：${instanceName}`}
      width={860}
      open={open}
      onCancel={onCancel}
      onOk={() => void handleSwitch()}
      okText="Reset --hard"
      cancelText="取消"
      okButtonProps={{ disabled: loading || fetching || !selectedRef || selectedRef === data?.current_ref }}
      confirmLoading={submitting}
      destroyOnClose
    >
      <Spin spinning={loading}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Button
              icon={<CloudDownloadOutlined />}
              loading={fetching}
              disabled={loading || submitting}
              onClick={() => void handleFetch()}
            >
              拉取最新版本
            </Button>
            <Typography.Text type="secondary">拉取后刷新可选版本，选择目标版本后切换。</Typography.Text>
          </Space>
          {data && (
            <Typography.Text>
              当前：<Typography.Text code>{data.current_label}</Typography.Text>{' '}
              <Typography.Text type="secondary">{data.current_commit}</Typography.Text>
            </Typography.Text>
          )}
          <Alert
            type="warning"
            showIcon
            message="切换会执行 git reset --hard，实例中已跟踪文件的本地修改将被覆盖。"
          />
          <Form layout="vertical">
            <Form.Item label="目标版本" required>
              <Select
                style={{ width: '100%' }}
                disabled={fetching || submitting}
                value={selectedRef}
                onChange={setSelectedRef}
                placeholder="选择分支、标签或最近 20 次提交"
                showSearch
                optionFilterProp="label"
                options={(data?.versions ?? []).map((item) => ({
                  value: item.ref,
                  label: `${item.label} ${item.branches.length ? `[${item.branches.join(', ')}] ` : ''}${item.commit}`,
                  title: `${item.label} ${item.branches.join(', ')} ${item.commit}`,
                  kind: item.kind,
                }))}
                optionRender={(option) => {
                  const item = data?.versions.find((value) => value.ref === option.value)
                  return item ? (
                    <Space wrap>
                      <Tag color={kindColor(item.kind)}>{kindLabel(item.kind)}</Tag>
                      <span>{item.label}</span>
                      {item.kind !== 'branch' && (
                        item.branches.length ? item.branches.map((branch) => (
                          <Tag key={branch} color="blue">{branch}</Tag>
                        )) : <Typography.Text type="secondary">无远程分支</Typography.Text>
                      )}
                      <Typography.Text type="secondary">{item.commit}</Typography.Text>
                      {item.committed_at ? (
                        <Typography.Text type="secondary">
                          {new Date(item.committed_at).toLocaleString()}
                        </Typography.Text>
                      ) : null}
                    </Space>
                  ) : null
                }}
                notFoundContent={loading ? <Spin size="small" /> : '没有可用版本'}
              />
            </Form.Item>
          </Form>
        </Space>
      </Spin>
    </Modal>
  )
}
