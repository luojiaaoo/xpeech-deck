import type { ReactNode } from 'react'
import { Button, Space, Table, Tooltip } from 'antd'
import type { TableProps } from 'antd'
import {
  CaretRightOutlined,
  CloudDownloadOutlined,
  PauseOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  SettingOutlined,
  TableOutlined,
} from '@ant-design/icons'
import type { Instance } from './types'

export type Action = 'up' | 'start' | 'stop' | 'restart' | 'down' | 'ps'

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
]

interface Props {
  instances: Instance[]
  loading: boolean
  busy: { name: string; action: Action } | null
  onConfig: (name: string) => void
  onCommand: (instance: Instance, action: Action) => void
}

export default function InstanceTable({ instances, loading, busy, onConfig, onCommand }: Props) {
  const columns: TableProps<Instance>['columns'] = [
    { title: '实例名', dataIndex: 'name', key: 'name' },
    { title: 'Backend 端口', dataIndex: 'backend_port', key: 'backend_port', width: 130 },
    { title: 'Web 端口', dataIndex: 'web_client_port', key: 'web_client_port', width: 110 },
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
              <Tooltip key={a.key} title={`docker compose ${a.key}`}>
                <Button
                  danger={a.danger}
                  icon={a.icon}
                  loading={rowBusy?.action === a.key}
                  disabled={rowBusy !== null}
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
