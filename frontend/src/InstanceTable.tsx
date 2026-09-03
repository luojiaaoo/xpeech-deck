import type { ReactNode } from 'react'
import { Button, Space, Table, Tooltip } from 'antd'
import type { TableProps } from 'antd'
import {
  AppstoreOutlined,
  CaretRightOutlined,
  BranchesOutlined,
  CloudDownloadOutlined,
  FileTextOutlined,
  PauseOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  SettingOutlined,
  TableOutlined,
} from '@ant-design/icons'
import type { Instance } from './types'

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
  busy: { name: string; action: Action } | null
  commandBusy: boolean
  onConfig: (name: string) => void
  onSkills: (name: string) => void
  onVersion: (name: string) => void
  onCommand: (instance: Instance, action: Action) => void
}

export default function InstanceTable({
  instances,
  loading,
  busy,
  commandBusy,
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
      title: 'Backend 端口',
      dataIndex: 'backend_port',
      key: 'backend_port',
      width: 130,
      sorter: (left, right) => left.backend_port - right.backend_port,
    },
    {
      title: 'Web 端口',
      dataIndex: 'web_client_port',
      key: 'web_client_port',
      width: 110,
      sorter: (left, right) => left.web_client_port - right.web_client_port,
    },
    {
      title: '版本',
      key: 'version',
      width: 100,
      render: (_, record) => (
        <Button icon={<BranchesOutlined />} disabled={commandBusy} onClick={() => onVersion(record.name)}>
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
          disabled={commandBusy}
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
        const rowBusy = busy && busy.name === record.name ? busy : null
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
                  loading={rowBusy?.action === a.key}
                  disabled={commandBusy}
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
