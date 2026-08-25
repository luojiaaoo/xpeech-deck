import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  InboxOutlined,
  ReloadOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import * as api from './api'
import type { Skill } from './types'

interface Props {
  open: boolean
  instanceName: string
  instanceNames: string[]
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

export default function SkillManagementModal({
  open,
  instanceName,
  instanceNames,
  onClose,
}: Props) {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)

  const [editingName, setEditingName] = useState<string | null>(null)
  const [editorContent, setEditorContent] = useState('')
  const [editorLoading, setEditorLoading] = useState(false)
  const [editorSaving, setEditorSaving] = useState(false)

  const [migrationSkill, setMigrationSkill] = useState<Skill | null>(null)
  const [migrationTargets, setMigrationTargets] = useState<string[]>([])
  const [migrating, setMigrating] = useState(false)

  const availableTargets = useMemo(
    () => instanceNames.filter((name) => name !== instanceName),
    [instanceName, instanceNames],
  )
  const editorBytes = useMemo(
    () => new TextEncoder().encode(editorContent).length,
    [editorContent],
  )
  const working = uploading || deleting !== null || downloading !== null || migrating

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
    setEditingName(null)
    setMigrationSkill(null)
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
      message.success(`技能 ${skill.name} 已上传并安装`)
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

  const openEditor = async (skill: Skill) => {
    setEditingName(skill.name)
    setEditorContent('')
    setEditorLoading(true)
    try {
      const data = await api.getSkillContent(instanceName, skill.name)
      setEditorContent(data.content)
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
      setEditingName(null)
    } finally {
      setEditorLoading(false)
    }
  }

  const saveEditor = async () => {
    if (!editingName) return
    if (editorBytes > MAX_SKILL_MD_BYTES) {
      message.error('SKILL.md 不能超过 1 MB')
      return
    }
    setEditorSaving(true)
    try {
      const updated = await api.saveSkillContent(instanceName, editingName, editorContent)
      setSkills((current) => current.map((item) => item.name === updated.name ? updated : item))
      message.success(`技能 ${editingName} 已保存`)
      setEditingName(null)
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setEditorSaving(false)
    }
  }

  const download = async (skill: Skill) => {
    setDownloading(skill.name)
    try {
      const blob = await api.downloadSkill(instanceName, skill.name)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${skill.name}.zip`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      message.success(`技能 ${skill.name} 已下载`)
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setDownloading(null)
    }
  }

  const openMigration = (skill: Skill) => {
    if (availableTargets.length === 0) {
      message.info('暂无其他实例可迁移')
      return
    }
    setMigrationSkill(skill)
    setMigrationTargets([])
  }

  const migrate = async (overwrite = false) => {
    if (!migrationSkill || migrationTargets.length === 0) return
    setMigrating(true)
    try {
      const result = await api.migrateSkill(
        instanceName,
        migrationSkill.name,
        migrationTargets,
        overwrite,
      )
      message.success(`技能 ${migrationSkill.name} 已迁移到 ${result.migrated.length} 个实例`)
      setMigrationSkill(null)
      setMigrationTargets([])
    } catch (error) {
      if (error instanceof api.ApiError && error.status === 409 && !overwrite) {
        Modal.confirm({
          title: '部分目标已存在同名技能',
          content: `${error.message}。是否覆盖这些目标实例中的现有版本？`,
          okText: '覆盖并迁移',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: () => migrate(true),
        })
      } else {
        message.error(error instanceof Error ? error.message : String(error))
      }
    } finally {
      setMigrating(false)
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
    <>
      <Modal
        title={`自定义内置技能：${instanceName}`}
        open={open}
        onCancel={onClose}
        width={960}
        destroyOnClose
        footer={[
          <Button
            key="refresh"
            icon={<ReloadOutlined />}
            loading={loading}
            disabled={working}
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
            message="完整管理 x-* 自定义内置技能"
            description="支持上传、在线编辑 SKILL.md、下载完整 ZIP，以及将技能迁移到多个实例。上传后会自动添加 x- 前缀。"
          />
          <Upload.Dragger
            accept=".md,.zip"
            multiple={false}
            showUploadList={false}
            disabled={working}
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
                    <Button
                      key="edit"
                      icon={<EditOutlined />}
                      disabled={working}
                      onClick={() => void openEditor(skill)}
                    >
                      在线编辑
                    </Button>,
                    <Button
                      key="download"
                      icon={<DownloadOutlined />}
                      loading={downloading === skill.name}
                      disabled={working && downloading !== skill.name}
                      onClick={() => void download(skill)}
                    >
                      下载
                    </Button>,
                    <Button
                      key="migrate"
                      icon={<SwapOutlined />}
                      disabled={working || availableTargets.length === 0}
                      onClick={() => openMigration(skill)}
                    >
                      多实例迁移
                    </Button>,
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
                        disabled={working && deleting !== skill.name}
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

      <Modal
        title={`在线编辑：${editingName ?? ''}/SKILL.md`}
        open={editingName !== null}
        width={880}
        okText="保存"
        cancelText="取消"
        confirmLoading={editorSaving}
        okButtonProps={{ disabled: editorLoading || editorBytes > MAX_SKILL_MD_BYTES }}
        onOk={() => void saveEditor()}
        onCancel={() => !editorSaving && setEditingName(null)}
        destroyOnClose
      >
        <Spin spinning={editorLoading}>
          <Input.TextArea
            className="skill-editor"
            value={editorContent}
            rows={24}
            spellCheck={false}
            onChange={(event) => setEditorContent(event.target.value)}
          />
          <Typography.Text type={editorBytes > MAX_SKILL_MD_BYTES ? 'danger' : 'secondary'}>
            {formatSize(editorBytes)} / 1 MB
          </Typography.Text>
        </Spin>
      </Modal>

      <Modal
        title={`多实例迁移：${migrationSkill?.name ?? ''}`}
        open={migrationSkill !== null}
        okText="开始迁移"
        cancelText="取消"
        confirmLoading={migrating}
        okButtonProps={{ disabled: migrationTargets.length === 0 }}
        onOk={() => void migrate()}
        onCancel={() => !migrating && setMigrationSkill(null)}
        destroyOnClose
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="完整技能目录会复制到所选实例"
            description="若目标实例已存在同名技能，系统会在执行前询问是否覆盖。"
          />
          <Space.Compact style={{ width: '100%' }}>
            <Select
              mode="multiple"
              style={{ width: '100%' }}
              placeholder="选择一个或多个目标实例"
              value={migrationTargets}
              options={availableTargets.map((name) => ({ label: name, value: name }))}
              onChange={setMigrationTargets}
              maxTagCount="responsive"
            />
            <Button onClick={() => setMigrationTargets(availableTargets)}>全选</Button>
          </Space.Compact>
        </Space>
      </Modal>
    </>
  )
}
