import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Cascader, Form, Modal, Space, Spin, Tag, Typography, message } from 'antd'
import { CloudDownloadOutlined } from '@ant-design/icons'
import * as api from './api'
import type { GitVersion, InstanceVersions } from './types'

interface Props {
  open: boolean
  instanceName: string
  onCancel: () => void
  onSwitched: () => void
}

interface VersionOption {
  value: string
  label: string
  version?: GitVersion
  children?: VersionOption[]
}

function buildVersionOptions(versions: GitVersion[]): VersionOption[] {
  const branches = versions.filter((item) => item.kind === 'branch')
  const branchNames = new Set(branches.map((item) => item.label))
  const leaf = (version: GitVersion): VersionOption => ({
    value: version.ref,
    label: `${version.kind === 'branch' ? '分支最新版本' : version.label} ${version.commit}`,
    version,
  })
  const groups: VersionOption[] = branches.map((branch) => ({
    value: branch.ref,
    label: branch.label,
    children: [
      leaf(branch),
      ...versions
        .filter((item) => item.kind !== 'branch' && item.branches.includes(branch.label))
        .map(leaf),
    ],
  }))
  const unassigned = versions.filter(
    (item) => item.kind !== 'branch' && !item.branches.some((name) => branchNames.has(name)),
  )
  if (unassigned.length) {
    groups.push({ value: '__unassigned__', label: '无远程分支', children: unassigned.map(leaf) })
  }
  return groups
}

function findVersionPath(options: VersionOption[], ref?: string, preferredGroup?: string): string[] | undefined {
  const group = options.find(
    (item) => item.value === preferredGroup && item.children?.some((child) => child.value === ref),
  ) ?? options.find((item) => item.children?.some((child) => child.value === ref))
  return group && ref ? [group.value, ref] : undefined
}

export default function VersionInstanceModal({ open, instanceName, onCancel, onSwitched }: Props) {
  const [data, setData] = useState<InstanceVersions | null>(null)
  const [selectedPath, setSelectedPath] = useState<string[]>()
  const selectedRef = selectedPath?.[1]
  const versionOptions = useMemo(() => buildVersionOptions(data?.versions ?? []), [data])
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
    setSelectedPath(undefined)
    api
      .getVersions(instanceName)
      .then((value) => {
        if (!active) return
        setData(value)
        setSelectedPath(findVersionPath(buildVersionOptions(value.versions), value.current_ref))
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
      setSelectedPath((previous) =>
        findVersionPath(buildVersionOptions(value.versions), previous?.[1], previous?.[0]),
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
              <Cascader<VersionOption>
                style={{ width: '100%' }}
                disabled={loading || fetching || submitting}
                value={selectedPath}
                onChange={(path) => setSelectedPath(path.length === 2 ? path : undefined)}
                placeholder="先选择分支，再选择具体版本"
                options={versionOptions}
                classNames={{ popup: { root: 'version-cascader-popup' } }}
                styles={{ popup: { root: { width: 560, maxWidth: 'calc(100vw - 32px)', minWidth: 0 } } }}
                showSearch={{
                  filter: (input, path) => path.some((option) =>
                    `${option.label} ${option.version?.kind ?? ''}`.toLowerCase().includes(input.toLowerCase()),
                  ),
                  limit: false,
                  matchInputWidth: false,
                }}
                optionRender={(option) => {
                  const item = option.version
                  return item ? (
                    <div className="version-option" title={`${item.label} · ${item.commit}`}>
                      <div className="version-option-summary">
                        <Tag color={kindColor(item.kind)}>{kindLabel(item.kind)}</Tag>
                        <span className="version-option-label">
                          {item.kind === 'branch' ? '分支最新版本' : item.label}
                        </span>
                        <Typography.Text type="secondary" className="version-option-commit mono">
                          {item.commit}
                        </Typography.Text>
                      </div>
                      {item.committed_at ? (
                        <Typography.Text type="secondary" className="version-option-date">
                          {new Date(item.committed_at).toLocaleString()}
                        </Typography.Text>
                      ) : null}
                    </div>
                  ) : option.label
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
