import { useEffect, useMemo, useState } from 'react'
import { Button, Form, Input, Modal, Select, Space, Spin, message } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import * as api from './api'
import type { Instance, RedirectMapping } from './types'

interface Props {
  open: boolean
  instances: Instance[]
  onClose: () => void
}

interface MappingRow extends RedirectMapping {
  id: number
}

let nextRowId = 1

function newRow(mapping?: RedirectMapping): MappingRow {
  return {
    id: nextRowId++,
    redirect_to: mapping?.redirect_to ?? '',
    instance_name: mapping?.instance_name ?? '',
  }
}

export default function GlobalConfigModal({ open, instances, onClose }: Props) {
  const [rows, setRows] = useState<MappingRow[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    api
      .getGlobalConfig()
      .then((data) => {
        if (active) setRows(data.mappings.map((mapping) => newRow(mapping)))
      })
      .catch((error) => {
        if (active) message.error(error instanceof Error ? error.message : String(error))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [open])

  const instanceOptions = useMemo(() => {
    const options = instances.map((instance) => ({
      label: `${instance.name}（Web ${instance.web_client_port}）`,
      value: instance.name,
    }))
    const known = new Set(instances.map((instance) => instance.name))
    for (const row of rows) {
      if (row.instance_name && !known.has(row.instance_name)) {
        options.push({
          label: `${row.instance_name}（实例不存在）`,
          value: row.instance_name,
        })
        known.add(row.instance_name)
      }
    }
    return options
  }, [instances, rows])

  const updateRow = (id: number, patch: Partial<RedirectMapping>) => {
    setRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...patch } : row)),
    )
  }

  const save = async () => {
    const mappings = rows.map(({ redirect_to, instance_name }) => ({
      redirect_to: redirect_to.trim(),
      instance_name,
    }))
    if (mappings.some((mapping) => !mapping.redirect_to || !mapping.instance_name)) {
      message.error('请完整填写每一行的 redirect_to 和实例')
      return
    }
    if (new Set(mappings.map((mapping) => mapping.redirect_to)).size !== mappings.length) {
      message.error('redirect_to 不能重复')
      return
    }

    setSaving(true)
    try {
      await api.saveGlobalConfig(mappings)
      message.success('全局配置已保存并实时生效')
      onClose()
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="全局配置"
      open={open}
      onCancel={onClose}
      onOk={() => void save()}
      okText="保存"
      cancelText="取消"
      confirmLoading={saving}
      width={760}
      destroyOnClose
    >
      <Spin spinning={loading}>
        <Form layout="vertical">
          <Form.Item label="redirect_to → 实例映射">
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              {rows.map((row) => (
                <Space.Compact key={row.id} style={{ width: '100%' }}>
                  <Input
                    aria-label="redirect_to"
                    placeholder="redirect_to 值"
                    value={row.redirect_to}
                    onChange={(event) =>
                      updateRow(row.id, { redirect_to: event.target.value })
                    }
                  />
                  <Select
                    aria-label="实例"
                    style={{ width: 280 }}
                    placeholder="选择实例"
                    value={row.instance_name || undefined}
                    options={instanceOptions}
                    onChange={(value) => updateRow(row.id, { instance_name: value })}
                  />
                  <Button
                    danger
                    aria-label="删除映射"
                    icon={<DeleteOutlined />}
                    onClick={() =>
                      setRows((current) => current.filter((item) => item.id !== row.id))
                    }
                  />
                </Space.Compact>
              ))}
              <Button
                block
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => setRows((current) => [...current, newRow()])}
              >
                添加映射
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Spin>
    </Modal>
  )
}
