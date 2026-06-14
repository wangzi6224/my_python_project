import { ChatMessage } from '@/contexts/ChatContext';
import JsonViewer from '@/components/JsonViewer';
import type { TraceDetailResponse, TraceSpan, TraceSummary } from '@/services/api';
import { getTrace } from '@/services/api';
import { InfoCircleOutlined } from '@ant-design/icons';
import {
  Button,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  List,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React, { useCallback, useMemo, useState } from 'react';
import styles from './index.module.less';

const { Text } = Typography;

interface TraceDrawerProps {
  msg: ChatMessage;
}

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function getString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return undefined;
}

function getNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return undefined;
}

function getBoolean(...values: unknown[]): boolean | undefined {
  for (const value of values) {
    if (typeof value === 'boolean') return value;
  }
  return undefined;
}

function nested(value: unknown, path: string[]): unknown {
  let current = value;

  for (const key of path) {
    if (!isRecord(current)) return undefined;
    current = current[key];
  }

  return current;
}

function formatCost(value?: number): string {
  if (value === undefined) return '-';
  if (value === 0) return '0';
  return `$${value.toFixed(6)}`;
}

function formatLatency(value?: number | null): string {
  return typeof value === 'number' ? `${Math.round(value)}ms` : '-';
}

function statusTag(status?: string) {
  const normalized = status || 'unknown';
  const color =
    normalized === 'error'
      ? 'error'
      : normalized === 'success'
      ? 'success'
      : normalized === 'running'
      ? 'processing'
      : 'default';

  return <Tag color={color}>{normalized}</Tag>;
}

function errorText(span: TraceSpan) {
  if (span.status !== 'error' && !span.error_message && !span.error_code) {
    return <Text type="secondary">-</Text>;
  }

  return (
    <Text type="danger">
      {span.error_code ? `[${span.error_code}] ` : ''}
      {span.error_message || 'error'}
    </Text>
  );
}

function jsonBlock(value: unknown) {
  return <JsonViewer value={value} />;
}

function ioCollapse(span: TraceSpan) {
  return (
    <Collapse
      size="small"
      ghost
      items={[
        {
          key: 'input',
          label: 'Input',
          children: jsonBlock(span.input || {}),
        },
        {
          key: 'output',
          label: 'Output',
          children: jsonBlock(span.output || {}),
        },
        {
          key: 'metadata',
          label: 'Metadata',
          children: jsonBlock(span.metadata || {}),
        },
      ]}
    />
  );
}

function getTraceSummary(msg: ChatMessage, detail: TraceDetailResponse | null) {
  return detail?.summary || msg.traceSummary || {};
}

function getLlmTokens(span: TraceSpan): number | undefined {
  return getNumber(
    nested(span.metadata, ['usage', 'total_tokens']),
    nested(span.output, ['usage', 'total_tokens']),
    span.metadata?.total_tokens,
  );
}

function getLlmCost(span: TraceSpan): number | undefined {
  return getNumber(
    nested(span.metadata, ['cost', 'total_cost']),
    span.metadata?.estimated_cost,
    span.output?.estimated_cost,
  );
}

function getToolName(span: TraceSpan): string {
  return (
    getString(
      span.metadata?.tool_name,
      span.input?.tool_name,
      nested(span.output, ['tool_name']),
      span.name,
    ) || '-'
  );
}

function getToolLatency(span: TraceSpan): number | null | undefined {
  return getNumber(span.latency_ms, span.metadata?.latency_ms, span.output?.latency_ms);
}

function getMcpServerName(span: TraceSpan): string {
  return (
    getString(
      span.metadata?.server_name,
      span.input?.server_name,
      span.output?.server_name,
    ) || '-'
  );
}

function getMcpToolName(span: TraceSpan): string {
  return (
    getString(span.metadata?.tool_name, span.input?.tool_name, span.output?.tool_name) ||
    span.name ||
    '-'
  );
}

const timelineColumns: ColumnsType<TraceSpan> = [
  {
    title: 'Time',
    dataIndex: 'started_at',
    key: 'started_at',
    width: 190,
    render: (value?: string) =>
      value ? new Date(value).toLocaleTimeString() : '-',
  },
  {
    title: 'Type',
    dataIndex: 'span_type',
    key: 'span_type',
    width: 190,
    render: (value: string, record) => (
      <Tag color={record.status === 'error' ? 'error' : 'blue'}>{value}</Tag>
    ),
  },
  {
    title: 'Name',
    dataIndex: 'name',
    key: 'name',
    render: (value: string, record) => (
      <Text type={record.status === 'error' ? 'danger' : undefined}>{value}</Text>
    ),
  },
  {
    title: 'Status',
    dataIndex: 'status',
    key: 'status',
    width: 120,
    render: statusTag,
  },
  {
    title: 'Latency',
    dataIndex: 'latency_ms',
    key: 'latency_ms',
    width: 110,
    render: formatLatency,
  },
  {
    title: 'Error',
    key: 'error',
    render: (_, record) => errorText(record),
  },
];

const llmColumns: ColumnsType<TraceSpan> = [
  {
    title: 'Model',
    key: 'model',
    render: (_, record) =>
      getString(record.metadata?.model, record.output?.model) || '-',
  },
  {
    title: 'Provider',
    key: 'provider',
    width: 140,
    render: (_, record) =>
      getString(record.metadata?.provider, record.output?.provider) || '-',
  },
  {
    title: 'Prompt Version',
    key: 'prompt_version',
    width: 180,
    render: (_, record) =>
      getString(record.metadata?.prompt_version, record.metadata?.prompt_name) ||
      '-',
  },
  {
    title: 'Tokens',
    key: 'tokens',
    width: 110,
    render: (_, record) => getLlmTokens(record) ?? '-',
  },
  {
    title: 'Estimated Cost',
    key: 'estimated_cost',
    width: 150,
    render: (_, record) => formatCost(getLlmCost(record)),
  },
  {
    title: 'Status',
    dataIndex: 'status',
    key: 'status',
    width: 110,
    render: statusTag,
  },
  {
    title: 'Error',
    key: 'error',
    render: (_, record) => errorText(record),
  },
];

const toolColumns: ColumnsType<TraceSpan> = [
  {
    title: 'Tool Name',
    key: 'tool_name',
    render: (_, record) => <Text code>{getToolName(record)}</Text>,
  },
  {
    title: 'Source',
    key: 'source',
    width: 120,
    render: (_, record) =>
      getString(record.metadata?.source, record.output?.source) || '-',
  },
  {
    title: 'Risk',
    key: 'risk_level',
    width: 110,
    render: (_, record) => {
      const risk = getString(record.metadata?.risk_level, record.output?.risk_level) || '-';
      const color =
        risk === 'high' ? 'error' : risk === 'medium' ? 'warning' : 'success';
      return risk === '-' ? '-' : <Tag color={color}>{risk}</Tag>;
    },
  },
  {
    title: 'Success',
    key: 'success',
    width: 110,
    render: (_, record) => {
      const success = getBoolean(record.output?.success, record.metadata?.success);
      if (success === undefined) return statusTag(record.status);
      return <Tag color={success ? 'success' : 'error'}>{String(success)}</Tag>;
    },
  },
  {
    title: 'Latency',
    key: 'latency',
    width: 110,
    render: (_, record) => formatLatency(getToolLatency(record)),
  },
  {
    title: 'Error',
    key: 'error',
    render: (_, record) => errorText(record),
  },
];

const mcpColumns: ColumnsType<TraceSpan> = [
  {
    title: 'Server Name',
    key: 'server_name',
    render: (_, record) => getMcpServerName(record),
  },
  {
    title: 'Tool Name',
    key: 'tool_name',
    render: (_, record) => <Text code>{getMcpToolName(record)}</Text>,
  },
  {
    title: 'Result Chars',
    key: 'result_chars',
    width: 130,
    render: (_, record) =>
      getNumber(record.metadata?.result_chars, record.output?.result_chars) ?? '-',
  },
  {
    title: 'Status',
    dataIndex: 'status',
    key: 'status',
    width: 110,
    render: statusTag,
  },
  {
    title: 'Error',
    key: 'error',
    render: (_, record) => errorText(record),
  },
];

const TraceDrawer: React.FC<TraceDrawerProps> = ({ msg }) => {
  const [open, setOpen] = useState(false);
  const [traceDetail, setTraceDetail] = useState<TraceDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const traceId =
    msg.traceId ||
    msg.traceSummary?.trace_id ||
    (msg.assistantRunId ? `trace_${msg.assistantRunId}` : undefined);
  const hasTraceTarget = Boolean(
    traceId || msg.traceSummary || (msg.trace && Object.keys(msg.trace).length > 0),
  );

  const handleOpen = useCallback(async () => {
    setOpen(true);

    if (!traceId || traceDetail) return;

    setLoading(true);
    try {
      const data = await getTrace(traceId);
      setTraceDetail(data);
    } catch (err: any) {
      message.error(
        err?.response?.data?.detail || err?.message || '获取 Trace 失败',
      );
    } finally {
      setLoading(false);
    }
  }, [traceDetail, traceId]);

  const spans = traceDetail?.spans || [];
  const summary = getTraceSummary(msg, traceDetail) as TraceSummary;
  const llmSpans = useMemo(
    () => spans.filter((span) => span.span_type === 'llm.call'),
    [spans],
  );
  const toolSpans = useMemo(
    () => spans.filter((span) => span.span_type === 'tool.call'),
    [spans],
  );
  const mcpSpans = useMemo(
    () => spans.filter((span) => span.span_type === 'mcp.call'),
    [spans],
  );
  const rawJson = traceDetail || {
    trace_id: traceId,
    summary,
    trace: msg.trace || {},
  };

  if (!hasTraceTarget) return null;

  return (
    <>
      <Button
        type="link"
        size="small"
        icon={<InfoCircleOutlined />}
        className={styles.traceBtn}
        onClick={handleOpen}
      >
        查看 Trace
      </Button>

      <Drawer
        title="Assistant Trace"
        className={styles.drawer}
        open={open}
        onClose={() => setOpen(false)}
        width={1200}
        loading={loading}
      >
        <Tabs
          items={[
            {
              key: 'overview',
              label: 'Overview',
              children: (
                <Descriptions
                  column={2}
                  size="small"
                  bordered
                  className={styles.descriptions}
                >
                  <Descriptions.Item label="Trace ID" span={2}>
                    {traceId ? (
                      <Text copyable code className={styles.idText}>
                        {traceId}
                      </Text>
                    ) : (
                      <Text type="secondary">-</Text>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="Spans">
                    {summary.span_count ?? spans.length}
                  </Descriptions.Item>
                  <Descriptions.Item label="Errors">
                    <Text type={summary.error_count ? 'danger' : undefined}>
                      {summary.error_count ?? 0}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="LLM Calls">
                    {summary.llm_call_count ?? llmSpans.length}
                  </Descriptions.Item>
                  <Descriptions.Item label="Tools">
                    {summary.tool_call_count ?? toolSpans.length}
                  </Descriptions.Item>
                  <Descriptions.Item label="MCP Calls">
                    {summary.mcp_call_count ?? mcpSpans.length}
                  </Descriptions.Item>
                  <Descriptions.Item label="Latency">
                    {formatLatency(
                      getNumber(summary.total_latency_ms, msg.latency_ms),
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="Tokens">
                    {summary.total_tokens ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Estimated Cost">
                    {formatCost(getNumber(summary.estimated_cost))}
                  </Descriptions.Item>
                  <Descriptions.Item label="Model">
                    {msg.model || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Provider">
                    {msg.provider || '-'}
                  </Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'timeline',
              label: 'Timeline',
              children:
                spans.length > 0 ? (
                  <Table
                    size="small"
                    rowKey="id"
                    columns={timelineColumns}
                    dataSource={spans}
                    pagination={false}
                    expandable={{ expandedRowRender: ioCollapse }}
                    scroll={{ x: 960 }}
                  />
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={traceId ? '暂无 Trace spans' : '缺少 trace_id'}
                  />
                ),
            },
            {
              key: 'llm',
              label: `LLM Calls (${llmSpans.length})`,
              children:
                llmSpans.length > 0 ? (
                  <Table
                    size="small"
                    rowKey="id"
                    columns={llmColumns}
                    dataSource={llmSpans}
                    pagination={false}
                    expandable={{ expandedRowRender: ioCollapse }}
                    scroll={{ x: 900 }}
                  />
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无 LLM Calls"
                  />
                ),
            },
            {
              key: 'tools',
              label: `Tools (${toolSpans.length + mcpSpans.length})`,
              children: (
                <>
                  <div className={styles.section}>
                    <Text strong className={styles.sectionTitle}>
                      Tool Calls ({toolSpans.length})
                    </Text>
                    {toolSpans.length > 0 ? (
                      <Table
                        size="small"
                        rowKey="id"
                        columns={toolColumns}
                        dataSource={toolSpans}
                        pagination={false}
                        expandable={{ expandedRowRender: ioCollapse }}
                        scroll={{ x: 860 }}
                      />
                    ) : (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="暂无 Tool Calls"
                      />
                    )}
                  </div>

                  <div className={styles.section}>
                    <Text strong className={styles.sectionTitle}>
                      MCP Calls ({mcpSpans.length})
                    </Text>
                    {mcpSpans.length > 0 ? (
                      <Table
                        size="small"
                        rowKey="id"
                        columns={mcpColumns}
                        dataSource={mcpSpans}
                        pagination={false}
                        expandable={{ expandedRowRender: ioCollapse }}
                        scroll={{ x: 760 }}
                      />
                    ) : (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="暂无 MCP Calls"
                      />
                    )}
                  </div>
                </>
              ),
            },
            {
              key: 'raw',
              label: 'Raw JSON',
              children: (
                <Collapse
                  size="small"
                  items={[
                    {
                      key: 'raw',
                      label: 'Raw JSON',
                      children: jsonBlock(rawJson),
                    },
                  ]}
                />
              ),
            },
          ]}
        />

        {!traceId ? (
          <List
            className={styles.section}
            size="small"
            dataSource={['当前消息没有 trace_id，无法请求 /traces/{trace_id}。']}
            renderItem={(item) => (
              <List.Item className={styles.listItem}>
                <Text type="secondary">{item}</Text>
              </List.Item>
            )}
          />
        ) : null}
      </Drawer>
    </>
  );
};

export default TraceDrawer;
