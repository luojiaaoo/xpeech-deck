import { useEffect, useState } from 'react'
import { Alert, Form, Modal, Select, Space, Spin, Tag, Typography, message } from 'antd'
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

  useEffect(() => {
    if (!open || !instanceName) return
    let active = true
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
    }
  }, [open, instanceName])

  const handleSwitch = async () => {
    if (!selectedRef) return
    setSubmitting(true)
    try {
      const result = await api.switchVersion(instanceName, selectedRef)
      message.success(`已切换到 ${result.current_label} (${result.current_commit})`)
      onSwitched()
    } catch (error) {
      message.error(String(error instanceof Error ? error.message : error))
    } finally {
      setSubmitting(false)
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
      open={open}
      onCancel={onCancel}
      onOk={() => void handleSwitch()}
      okText="Reset --hard"
      cancelText="取消"
      okButtonProps={{ disabled: !selectedRef || selectedRef === data?.current_ref }}
      confirmLoading={submitting}
      destroyOnClose
    >
      <Spin spinning={loading}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
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
                value={selectedRef}
                onChange={setSelectedRef}
                placeholder="选择分支、标签或最近 20 次提交"
                showSearch
                optionFilterProp="label"
                options={(data?.versions ?? []).map((item) => ({
                  value: item.ref,
                  label: `${item.label} ${item.commit}`,
                  searchLabel: item.label,
                  title: item.label,
                  kind: item.kind,
                }))}
                optionRender={(option) => {
                  const item = data?.versions.find((value) => value.ref === option.value)
                  return item ? (
                    <Space>
                      <Tag color={kindColor(item.kind)}>{kindLabel(item.kind)}</Tag>
                      <span>{item.label}</span>
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
