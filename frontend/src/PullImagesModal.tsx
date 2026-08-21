import { useCallback, useEffect, useState } from 'react'
import { Button, Descriptions, List, Modal, Space, Spin, Tag, Typography, message } from 'antd'
import { CloudDownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import * as api from './api'
import type { ImageStatus } from './types'

interface Props {
  open: boolean
  onClose: () => void
}

function formatSize(value: number | null): string {
  if (value === null) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function statusTag(status: ImageStatus['status']) {
  if (status === 'available') return <Tag color="success">已存在</Tag>
  if (status === 'missing') return <Tag>未拉取</Tag>
  return <Tag color="error">检查失败</Tag>
}

export default function PullImagesModal({ open, onClose }: Props) {
  const [images, setImages] = useState<ImageStatus[]>([])
  const [loading, setLoading] = useState(false)
  const [pulling, setPulling] = useState<string | null>(null)

  const loadImages = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listImages()
      setImages(data.images)
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void loadImages()
  }, [open, loadImages])

  const pullImage = async (image: ImageStatus) => {
    setPulling(image.key)
    try {
      const result = await api.pullImage(image.key)
      setImages((current) => current.map((item) => (item.key === image.key ? result.image : item)))
      if (result.success) {
        message.success(`${image.label}拉取完成`)
      } else {
        message.error(result.stderr || result.stdout || `${image.label}拉取失败`)
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setPulling(null)
    }
  }

  return (
    <Modal
      title="拉取镜像"
      open={open}
      onCancel={onClose}
      width={720}
      footer={[
        <Button key="refresh" icon={<ReloadOutlined />} loading={loading} onClick={() => void loadImages()}>
          刷新状态
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
      ]}
    >
      <Spin spinning={loading && images.length === 0}>
        <List
          dataSource={images}
          locale={{ emptyText: loading ? '正在检查镜像状态…' : '暂无镜像信息' }}
          renderItem={(image) => (
            <List.Item
              actions={[
                <Button
                  key="pull"
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  loading={pulling === image.key}
                  disabled={pulling !== null && pulling !== image.key}
                  onClick={() => void pullImage(image)}
                >
                  拉取 {image.label}
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Typography.Text strong>{image.label}</Typography.Text>
                    {statusTag(image.status)}
                  </Space>
                }
                description={
                  <div>
                    <Typography.Text className="mono" copyable>{image.name}</Typography.Text>
                    <Descriptions size="small" column={3} className="image-details">
                      <Descriptions.Item label="镜像 ID">{image.image_id ?? '-'}</Descriptions.Item>
                      <Descriptions.Item label="大小">{formatSize(image.size_bytes)}</Descriptions.Item>
                      <Descriptions.Item label="创建时间">
                        {image.created_at ? new Date(image.created_at).toLocaleString() : '-'}
                      </Descriptions.Item>
                    </Descriptions>
                    {image.message ? <Typography.Text type="danger">{image.message}</Typography.Text> : null}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </Spin>
    </Modal>
  )
}
