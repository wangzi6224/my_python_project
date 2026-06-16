import { AssistantToolCallEvent } from '@/services/api';
import JsonViewer from '@/components/JsonViewer';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Collapse, Tag, Timeline, Typography } from 'antd';
import React from 'react';
import styles from './index.module.less';

const { Text } = Typography;

interface ToolCallTimelineProps {
  toolCalls?: AssistantToolCallEvent[];
}

function getNestedString(
  value: Record<string, unknown> | undefined,
  path: string[],
): string | undefined {
  let current: unknown = value;

  for (const key of path) {
    if (!current || typeof current !== 'object' || Array.isArray(current)) {
      return undefined;
    }

    current = (current as Record<string, unknown>)[key];
  }

  return typeof current === 'string' ? current : undefined;
}

function inferMcpServerName(toolName?: string): string | undefined {
  if (!toolName?.startsWith('mcp__')) return undefined;

  const [, serverName] = toolName.split('__');
  return serverName || undefined;
}

function getToolSource(tc: AssistantToolCallEvent): string {
  return (
    tc.source ||
    getNestedString(tc.metadata, ['source']) ||
    getNestedString(tc.result, ['metadata', 'source']) ||
    (tc.tool_name?.startsWith('mcp__') ? 'mcp' : 'internal')
  );
}

function getToolRole(tc: AssistantToolCallEvent): string | undefined {
  return tc.role || getNestedString(tc.metadata, ['role']);
}

function getMultiAgentRunId(tc: AssistantToolCallEvent): string | undefined {
  return (
    tc.multi_agent_run_id ||
    getNestedString(tc.metadata, ['multi_agent_run_id'])
  );
}

function getServerName(tc: AssistantToolCallEvent): string | undefined {
  return (
    tc.server_name ||
    getNestedString(tc.result, ['metadata', 'server_name']) ||
    getNestedString(tc.result, ['data', 'server_name']) ||
    inferMcpServerName(tc.tool_name)
  );
}

function getRiskLevel(tc: AssistantToolCallEvent): string {
  return (
    tc.risk_level ||
    getNestedString(tc.result, ['metadata', 'risk_level']) ||
    'low'
  );
}

function getStatusLabel(tc: AssistantToolCallEvent): string {
  if (tc.error_code === 'MCP_PERMISSION_DENIED') return 'denied';
  if (tc.success === undefined) return 'running';
  return tc.success ? 'success' : 'failed';
}

function getStatusColor(status: string): string {
  if (status === 'success') return 'success';
  if (status === 'denied') return 'warning';
  if (status === 'failed') return 'error';
  return 'processing';
}

function getRiskColor(riskLevel: string): string {
  if (riskLevel === 'high') return 'error';
  if (riskLevel === 'medium') return 'warning';
  return 'success';
}

const ToolCallTimeline: React.FC<ToolCallTimelineProps> = ({ toolCalls }) => {
  if (!toolCalls || toolCalls.length === 0) return null;

  const items = toolCalls.map((tc, idx) => {
    const key = `${tc.tool_name ?? 'tool'}-${tc.step ?? idx}`;
    const source = getToolSource(tc);
    const role = getToolRole(tc);
    const multiAgentRunId = getMultiAgentRunId(tc);
    const serverName = getServerName(tc);
    const riskLevel = getRiskLevel(tc);
    const status = getStatusLabel(tc);

    // 状态图标
    let dot: React.ReactNode;
    if (tc.success === undefined) {
      dot = <LoadingOutlined />;
    } else if (tc.success) {
      dot = <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    } else {
      dot = <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
    }

    // arguments 折叠内容
    const hasArgs = tc.arguments && Object.keys(tc.arguments).length > 0;
    const argPanel = hasArgs
      ? [
          {
            key: 'args',
            label: '参数',
            children: <JsonViewer value={tc.arguments} maxHeight={260} />,
          },
        ]
      : undefined;

    return {
      key,
      dot,
      children: (
        <div className={styles.item}>
          <div className={styles.itemHeader}>
            <ToolOutlined className={styles.toolIcon} />
            <Text strong className={styles.toolName}>
              {tc.tool_name || '未知工具'}
            </Text>
            <Tag color={source === 'mcp' ? 'purple' : 'blue'}>{source}</Tag>
            {role && <Tag color="cyan">role={role}</Tag>}
            {multiAgentRunId && <Tag color="volcano">run={multiAgentRunId}</Tag>}
            {serverName && <Tag color="geekblue">{serverName}</Tag>}
            <Tag color={getRiskColor(riskLevel)}>{riskLevel}</Tag>
            <Tag color={getStatusColor(status)}>{status}</Tag>
            {tc.step !== undefined && (
              <Tag color="default" className={styles.stepTag}>
                Step {tc.step}
              </Tag>
            )}
            {tc.latency_ms !== undefined && (
              <Text type="secondary" className={styles.latency}>
                {tc.latency_ms}ms
              </Text>
            )}
          </div>
          {tc.reason && (
            <Text type="secondary" className={styles.reason}>
              {tc.reason}
            </Text>
          )}
          {tc.success === false && tc.error_message && (
            <Text type="danger" className={styles.error}>
              {tc.error_code ? `[${tc.error_code}] ` : ''}
              {tc.error_message}
            </Text>
          )}
          {argPanel && (
            <Collapse
              size="small"
              ghost
              items={argPanel}
              className={styles.argsCollapse}
            />
          )}
        </div>
      ),
    };
  });

  return (
    <div className={styles.container}>
      <Text type="secondary" className={styles.title}>
        工具调用
      </Text>
      <Timeline items={items} className={styles.timeline} />
    </div>
  );
};

export default ToolCallTimeline;
