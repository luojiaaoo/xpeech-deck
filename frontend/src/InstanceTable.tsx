import type { ReactNode } from 'react'
import { Button, Space, Table, Tooltip } from 'antd'
import type { TableProps } from 'antd'
import {
  AppstoreOutlined,
  CaretRightOutlined,
  BranchesOutlined,
  CloudDownloadOutlined,
  ExportOutlined,
  FileTextOutlined,
  PauseOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  SettingOutlined,
  TableOutlined,
} from '@ant-design/icons'
import type { Instance } from './types'
import { getWebClientUrl } from './webClient'

export type Action = 'up' | 'start' | 'stop' | 'restart' | 'down' | 'ps' | 'logs'

interface ActionDef {
  key: Action
  label: string
  icon: ReactNode
  danger?: boolean
}

const ACTIONS: ActionDef[] = [
  { key: 'up', label: 'Up', icon: <CloudDownloadOutlined /> },
  { key: 'start', label: 'Start', icon: <CaretRightOutlined /> },
  { key: 'stop', label: 'Stop', icon: <PauseOutlined /> },
  { key: 'restart', label: 'Restart', icon: <ReloadOutlined /> },
  { key: 'down', label: 'Down', icon: <PoweroffOutlined />, danger: true },
  { key: 'ps', label: 'PS', icon: <TableOutlined /> },
  { key: 'logs', label: '日志', icon: <FileTextOutlined /> },
]

interface Props {
  instances: Instance[]
  loading: boolean
  busy: { name: string; action: Action }[]
  onConfig: (name: string) => void
  onSkills: (name: string) => void
  onVersion: (name: string) => void
  onCommand: (instance: Instance, action: Action) => void
}

export default function InstanceTable({
  instances,
  loading,
  busy,
  onConfig,
  onSkills,
  onVersion,
  onCommand,
}: Props) {
  const columns: TableProps<Instance>['columns'] = [
    {
      title: '实例名',
      dataIndex: 'name',
      key: 'name',
      sorter: (left, right) => left.name.localeCompare(right.name, undefined, { numeric: true }),
    },
    {
      title: '端口',
      key: 'ports',
      render: (_, record) => record.ports.join(', ') || '-',
    },
    {
      title: '超链接',
      key: 'web_client',
      width: 160,
      render: (_, record) => (
        <Tooltip title={record.web_client_port === null ? '未配置有效的 WEB_CLIENT_PORT' : `Web 端口：${record.web_client_port}`}>
          <Button
            type="link"
            icon={<ExportOutlined />}
            disabled={record.web_client_port === null}
            href={record.web_client_port === null ? undefined : getWebClientUrl(record.web_client_port)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`进入 ${record.name} 的 Web 客户端`}
          >
            WEB_CLIENT
          </Button>
        </Tooltip>
      ),
    },
    {
      title: '版本',
      key: 'version',
      width: 100,
      render: (_, record) => (
        <Button icon={<BranchesOutlined />} onClick={() => onVersion(record.name)}>
          切换
        </Button>
      ),
    },
    {
      title: '技能',
      key: 'skills',
      width: 120,
      render: (_, record) => (
        <Button
          icon={<AppstoreOutlined />}
          onClick={() => onSkills(record.name)}
        >
          技能管理
        </Button>
      ),
    },
    {
      title: '配置',
      key: 'config',
      width: 90,
      render: (_, record) => (
        <Button icon={<SettingOutlined />} onClick={() => onConfig(record.name)}>
          配置
        </Button>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => {
        const rowBusy = busy.filter((item) => item.name === record.name)
        return (
          <Space wrap>
            {ACTIONS.map((a) => (
              <Tooltip
                key={a.key}
                title={a.key === 'logs' ? '选择子服务并查看最近 500 行日志' : `docker compose ${a.key}`}
              >
                <Button
                  danger={a.danger}
                  icon={a.icon}
                  loading={rowBusy.some((item) => item.action === a.key)}
                  onClick={() => onCommand(record, a.key)}
                >
                  {a.label}
                </Button>
              </Tooltip>
            ))}
          </Space>
        )
      },
    },
  ]

  return (
    <Table<Instance>
      rowKey="name"
      columns={columns}
      dataSource={instances}
      loading={loading}
      pagination={false}
    />
  )
}
