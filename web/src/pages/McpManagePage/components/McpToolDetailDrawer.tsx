import JsonViewer from '@/components/JsonViewer';
import { callMcpTool, listMcpAuditLogs } from '@/services/mcpApi';
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React, { useEffect, useMemo, useState } from 'react';
import styles from '../index.module.less';
import { McpAuditLog, McpToolCallResult, McpToolSpec } from '../types';
import JsonEditorField from './JsonEditorField';
import { riskColorMap } from './McpToolTable';

const { Paragraph, Text } = Typography;

interface McpToolDetailDrawerProps {
  open: boolean;
  tool?: McpToolSpec | null;
  activeTab?: string;
  onClose: () => void;
}

const parseArguments = (text: string): Record<string, unknown> => {
  const parsed = JSON.parse(text || '{}') as unknown;

  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('arguments 必须是合法 JSON object');
  }

  return parsed as Record<string, unknown>;
};

const McpToolDetailDrawer: React.FC<McpToolDetailDrawerProps> = ({
  open,
  tool,
  activeTab = 'base',
  onClose,
}) => {
  const [tabKey, setTabKey] = useState(activeTab);
  const [argumentsText, setArgumentsText] = useState('{\n}');
  const [argumentsError, setArgumentsError] = useState('');
  const [callLoading, setCallLoading] = useState(false);
  const [callResult, setCallResult] = useState<McpToolCallResult | null>(null);
  const [auditLogs, setAuditLogs] = useState<McpAuditLog[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState('');

  useEffect(() => {
    if (!open) return;
    setTabKey(activeTab);
    setArgumentsText('{\n}');
    setArgumentsError('');
    setCallResult(null);
  }, [activeTab, open, tool?.full_name]);

  const fetchAuditLogs = async (): Promise<void> => {
    if (!tool) return;
    setAuditLoading(true);
    setAuditError('');

    try {
      const response = await listMcpAuditLogs({
        full_tool_name: tool.full_name,
        limit: 20,
      });
      setAuditLogs(response.items || []);
    } catch (error) {
      setAuditLogs([]);
      setAuditError(
        error instanceof Error
          ? error.message
          : '审计日志接口暂不可用，等待后端补齐',
      );
    } finally {
      setAuditLoading(false);
    }
  };

  useEffect(() => {
    if (open && tool && tabKey === 'audit') {
      void fetchAuditLogs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, tabKey, tool?.full_name]);

  const handleCall = async (): Promise<void> => {
    if (!tool) return;

    try {
      const argumentsPayload = parseArguments(argumentsText);
      setArgumentsError('');
      setCallLoading(true);
      const result = await callMcpTool(tool.full_name, argumentsPayload);
      setCallResult(result);
      if (result.success) {
        message.success('测试调用完成');
      } else {
        message.error(result.error_message || '测试调用失败');
      }
    } catch (error) {
      const text = error instanceof Error ? error.message : '测试调用失败';
      setArgumentsError(text);
      message.error(text);
    } finally {
      setCallLoading(false);
    }
  };

  const auditColumns = useMemo<ColumnsType<McpAuditLog>>(
    () => [
      {
        title: '时间',
        dataIndex: 'created_at',
        width: 170,
        render: (value?: string) => value || '-',
      },
      {
        title: '结果',
        dataIndex: 'success',
        width: 90,
        render: (value: boolean) => (
          <Tag color={value ? 'green' : 'red'}>{value ? 'success' : 'failed'}</Tag>
        ),
      },
      {
        title: 'latency',
        dataIndex: 'latency_ms',
        width: 100,
        render: (value: number) => `${value || 0}ms`,
      },
      {
        title: 'error',
        dataIndex: 'error_message',
        render: (value?: string | null) => value || '-',
      },
    ],
    [],
  );

  if (!tool) {
    return (
      <Drawer title="工具详情" open={open} onClose={onClose}>
        <Empty description="未选择工具" />
      </Drawer>
    );
  }

  return (
    <Drawer
      title={`工具详情：${tool.tool_name}`}
      width={720}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      <Tabs
        activeKey={tabKey}
        onChange={setTabKey}
        items={[
          {
            key: 'base',
            label: '基础信息',
            children: (
              <Descriptions bordered size="small" column={1}>
                <Descriptions.Item label="server_name">{tool.server_name}</Descriptions.Item>
                <Descriptions.Item label="tool_name">{tool.tool_name}</Descriptions.Item>
                <Descriptions.Item label="full_name">
                  <Text code>{tool.full_name}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="description">
                  {tool.description || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="risk_level">
                  <Tag color={riskColorMap[tool.risk_level]}>{tool.risk_level}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="enabled">
                  <Tag color={tool.enabled ? 'green' : 'default'}>
                    {tool.enabled ? 'enabled' : 'disabled'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="metadata">
                  <JsonViewer value={tool.metadata || {}} />
                </Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: 'schema',
            label: '参数 Schema',
            children: <JsonViewer value={tool.input_schema || {}} />,
          },
          {
            key: 'test',
            label: '测试调用',
            children: (
              <div className={styles.drawerSection}>
                <Alert
                  type="warning"
                  showIcon
                  message="测试调用会真实请求外部 MCP Server，请确保参数和工具风险已确认。"
                />
                <JsonEditorField
                  value={argumentsText}
                  onChange={setArgumentsText}
                  error={argumentsError}
                  placeholder="{\n}"
                />
                <Space>
                  <Button type="primary" loading={callLoading} onClick={handleCall}>
                    测试调用
                  </Button>
                </Space>
                {callResult ? (
                  <div className={styles.resultBox}>
                    <Descriptions bordered size="small" column={1}>
                      <Descriptions.Item label="success">
                        <Tag color={callResult.success ? 'green' : 'red'}>
                          {String(callResult.success)}
                        </Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="latency_ms">
                        {callResult.latency_ms}ms
                      </Descriptions.Item>
                      <Descriptions.Item label="content">
                        <Paragraph className={styles.resultContent}>
                          {callResult.content || '-'}
                        </Paragraph>
                      </Descriptions.Item>
                      <Descriptions.Item label="error_code">
                        {callResult.error_code || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="error_message">
                        {callResult.error_message || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="metadata.truncated">
                        {String(Boolean(callResult.metadata?.truncated))}
                      </Descriptions.Item>
                    </Descriptions>
                  </div>
                ) : null}
              </div>
            ),
          },
          {
            key: 'audit',
            label: '审计日志',
            children: (
              <div className={styles.drawerSection}>
                {auditError ? (
                  <Alert
                    type="info"
                    showIcon
                    message="审计日志接口暂不可用"
                    description={auditError}
                  />
                ) : null}
                <Table
                  rowKey="id"
                  size="small"
                  loading={auditLoading}
                  columns={auditColumns}
                  dataSource={auditLogs}
                  pagination={false}
                  locale={{ emptyText: '暂无审计记录' }}
                />
              </div>
            ),
          },
        ]}
      />
    </Drawer>
  );
};

export default McpToolDetailDrawer;
