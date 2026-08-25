import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  List,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  DeleteOutlined,
  InboxOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import * as api from './api'
import type { Skill } from './types'

interface Props {
  open: boolean
  instanceName: string
  onClose: () => void
}

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024
const MAX_SKILL_MD_BYTES = 1024 * 1024

function formatSize(value: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

export default function SkillManagementModal({ open, instanceName, onClose }: Props) {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)

  const loadSkills = useCallback(async () => {
    if (!instanceName) return
    setLoading(true)
    try {
      const data = await api.listSkills(instanceName)
      setSkills(data.skills)
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setLoading(false)
    }
  }, [instanceName])

  useEffect(() => {
    if (!open) return
    setSkills([])
    void loadSkills()
  }, [open, loadSkills])

  const install = async (file: File, overwrite = false) => {
    if (file.name.toLowerCase() !== 'skill.md' && !file.name.toLowerCase().endsWith('.zip')) {
      message.error('请选择 SKILL.md 或 .zip 技能包')
      return
    }
    if (file.name.toLowerCase() === 'skill.md' && file.size > MAX_SKILL_MD_BYTES) {
      message.error('SKILL.md 不能超过 1 MB')
      return
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      message.error('技能包不能超过 20 MB')
      return
    }

    setUploading(true)
    try {
      const skill = await api.uploadSkill(instanceName, file, overwrite)
      message.success(`技能 ${skill.name} 已安装`)
      await loadSkills()
    } catch (error) {
      if (error instanceof api.ApiError && error.status === 409 && !overwrite) {
        Modal.confirm({
          title: '同名技能已存在',
          content: '是否使用上传的技能包覆盖现有版本？',
          okText: '覆盖',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: () => install(file, true),
        })
      } else {
        message.error(error instanceof Error ? error.message : String(error))
      }
    } finally {
      setUploading(false)
    }
  }

  const remove = async (skill: Skill) => {
    setDeleting(skill.name)
    try {
      await api.deleteSkill(instanceName, skill.name)
      message.success(`技能 ${skill.name} 已删除`)
      setSkills((current) => current.filter((item) => item.name !== skill.name))
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setDeleting(null)
    }
  }

  return (
    <Modal
      title={`自定义内置技能：${instanceName}`}
      open={open}
      onCancel={onClose}
      width={760}
      destroyOnClose
      footer={[
        <Button
          key="refresh"
          icon={<ReloadOutlined />}
          loading={loading}
          disabled={uploading || deleting !== null}
          onClick={() => void loadSkills()}
        >
          刷新
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
      ]}
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="上传后会自动添加 x- 前缀"
          description="可直接上传 SKILL.md，系统会读取其中的 name；技能包含 scripts、references 或 assets 时请上传 .zip。只有 x-* 自定义技能可在这里删除。"
        />
        <Upload.Dragger
          accept=".md,.zip"
          multiple={false}
          showUploadList={false}
          disabled={uploading || deleting !== null}
          beforeUpload={(file) => {
            void install(file)
            return false
          }}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽 SKILL.md / ZIP 技能包到这里上传</p>
          <p className="ant-upload-hint">SKILL.md 最大 1 MB，ZIP 最大 20 MB；同名技能可确认覆盖</p>
        </Upload.Dragger>

        <Spin spinning={loading && skills.length === 0}>
          <List
            bordered
            dataSource={skills}
            locale={{ emptyText: loading ? '正在读取技能…' : '暂无自定义内置技能' }}
            renderItem={(skill) => (
              <List.Item
                actions={[
                  <Popconfirm
                    key="delete"
                    title={`删除技能 ${skill.name}？`}
                    description="删除后无法在 Deck 中恢复。"
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    cancelText="取消"
                    onConfirm={() => remove(skill)}
                  >
                    <Button
                      danger
                      icon={<DeleteOutlined />}
                      loading={deleting === skill.name}
                      disabled={uploading || (deleting !== null && deleting !== skill.name)}
                    >
                      删除
                    </Button>
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Typography.Text strong className="mono">{skill.name}</Typography.Text>
                      <Tag color="blue">自定义内置</Tag>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={2}>
                      <Typography.Text type={skill.description ? undefined : 'secondary'}>
                        {skill.description || 'SKILL.md 未提供描述'}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        {skill.file_count} 个文件 · {formatSize(skill.size_bytes)}
                      </Typography.Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        </Spin>
      </Space>
    </Modal>
  )
}
