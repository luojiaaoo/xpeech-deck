import { useCallback, useEffect, useState } from 'react'
import { Button, Empty, Modal, Space, Spin, Typography, message } from 'antd'
import { FileTextOutlined, ReloadOutlined } from '@ant-design/icons'
import * as api from './api'
import CommandResultModal from './CommandResultModal'
import type { ComposeResult } from './types'

interface Props {
  open: boolean
  instanceName: string
  onClose: () => void
}

export default function DockerLogsModal({
  open,
  instanceName,
  onClose,
}: Props) {
  const [services, setServices] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [viewing, setViewing] = useState<string[]>([])
  const [result, setResult] = useState<ComposeResult | null>(null)
  const [resultService, setResultService] = useState<string | null>(null)
  const [resultOpen, setResultOpen] = useState(false)

  const loadServices = useCallback(async () => {
    if (!instanceName) return
    setLoading(true)
    try {
      const data = await api.listComposeServices(instanceName)
      if (data.success) {
        setServices(data.services)
      } else {
        setServices([])
        message.error(data.stderr || data.stdout || '读取 Compose 服务列表失败')
      }
    } catch (error) {
      setServices([])
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setLoading(false)
    }
  }, [instanceName])

  useEffect(() => {
    if (open) {
      setServices([])
      setResultOpen(false)
      void loadServices()
    }
  }, [open, loadServices])

  const viewLogs = async (service: string) => {
    setViewing((current) => [...current, service])
    try {
      const data = await api.composeLogs(instanceName, service)
      setResult(data)
      setResultService(service)
      setResultOpen(true)
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setViewing((current) => current.filter((item) => item !== service))
    }
  }

  return (
    <>
      <Modal
        title={`Docker 日志：${instanceName}`}
        open={open}
        onCancel={onClose}
        width={960}
        footer={[
          <Button
            key="refresh"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => void loadServices()}
          >
            刷新服务
          </Button>,
          <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
        ]}
      >
        <Typography.Paragraph type="secondary">
          选择一个 Compose 子服务，查看其最近 500 行日志。
        </Typography.Paragraph>
        <Spin spinning={loading && services.length === 0}>
          {services.length > 0 ? (
            <Space wrap>
              {services.map((service) => (
                <Button
                  key={service}
                  icon={<FileTextOutlined />}
                  loading={viewing.includes(service)}
                  onClick={() => void viewLogs(service)}
                >
                  {service}
                </Button>
              ))}
            </Space>
          ) : (
            <Empty description={loading ? '正在读取服务列表…' : '未发现 Compose 子服务'} />
          )}
        </Spin>
      </Modal>
      <CommandResultModal
        open={resultOpen}
        result={result}
        title={`${resultService ?? ''} 日志（最近 500 行）`}
        width={1280}
        onClose={() => setResultOpen(false)}
      />
    </>
  )
}
