import {
  AgentEventItem,
  AgentRunDetailResponse,
  AgentRunItem,
  AgentStepItem,
  getAgentRunDetail,
} from '@/services';
import JsonViewer from '@/components/JsonViewer';
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  MessageOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { XMarkdown } from '@ant-design/x-markdown';
import { history, useLocation, useParams } from '@umijs/max';
import type { CollapseProps } from 'antd';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import axios from 'axios';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import styles from './index.module.less';

const { Paragraph, Text, Title } = Typography;

const getErrorText = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { message?: string; detail?: unknown; code?: string }
      | undefined;
    const detailText =
      typeof data?.detail === 'string' ? data.detail : undefined;

    return (
      data?.message ||
      detailText ||
      data?.code ||
      error.message ||
      '请求失败，请稍后重试'
    );
  }

  if (error instanceof Error) return error.message;

  return '请求失败，请稍后重试';
};

const formatDateTime = (value?: string): string => {
  if (!value) return '-';

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString('zh-CN', { hour12: false });
};

const formatLatency = (value?: number | null): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';

  return `${value}ms`;
};

const statusColor = (status?: string): string => {
  const normalized = (status || '').toLowerCase();

  if (normalized.includes('fail') || normalized.includes('error')) {
    return 'error';
  }

  if (normalized.includes('run') || normalized.includes('pending')) {
    return 'processing';
  }

  if (
    normalized.includes('done') ||
    normalized.includes('complete') ||
    normalized.includes('success')
  ) {
    return 'success';
  }

  return 'default';
};

const successColor = (success?: boolean): string => {
  return success ? 'success' : 'error';
};

const toJsonText = (value: unknown): string => {
  if (value === null || value === undefined) return '-';

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const summarizeResult = (value: unknown): string => {
  if (!value) return '-';

  const jsonText = toJsonText(value).replace(/\s+/g, ' ').trim();

  if (jsonText.length <= 220) return jsonText;

  return `${jsonText.slice(0, 220)}...`;
};

const renderMarkdown = (content: unknown) => (
  <XMarkdown
    content={String(content ?? '')}
    components={{
      a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
    }}
  />
);

const JsonBlock: React.FC<{ value: unknown }> = ({ value }) => (
  <JsonViewer value={value} />
);

interface ChainNode {
  key: string;
  title: string;
  meta: string;
  status: 'success' | 'error' | 'processing' | 'default';
  stepIndex?: number;
}

const buildChainNodes = (
  run: AgentRunItem,
  steps: AgentStepItem[],
): ChainNode[] => {
  const nodes: ChainNode[] = [
    {
      key: 'input',
      title: 'User Input',
      meta: formatDateTime(run.created_at),
      status: 'default',
    },
  ];

  steps.forEach((step) => {
    nodes.push({
      key: step.id,
      title: `Step ${step.step_index}: ${
        step.tool_name || step.step_type || 'unknown'
      }`,
      meta: formatLatency(step.latency_ms),
      status: step.success ? 'success' : 'error',
      stepIndex: step.step_index,
    });
  });

  nodes.push({
    key: 'answer',
    title: 'Final Answer',
    meta: formatLatency(run.total_latency_ms),
    status:
      statusColor(run.status) === 'processing'
        ? 'processing'
        : statusColor(run.status) === 'error'
        ? 'error'
        : 'success',
  });

  return nodes;
};

const AgentTraceDetailPage: React.FC = () => {
  const params = useParams<{ runId: string }>();
  const location = useLocation();
  const [data, setData] = useState<AgentRunDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [activeStepKeys, setActiveStepKeys] = useState<string[]>([]);
  const stepRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const runId = params.runId || '';
  const queryConversationId = useMemo(() => {
    return new URLSearchParams(location.search).get('conversation_id') || '';
  }, [location.search]);

  const backUrl = queryConversationId
    ? `/traces?conversation_id=${encodeURIComponent(queryConversationId)}`
    : '/traces';

  const fetchDetail = async (): Promise<void> => {
    if (!runId) return;

    setLoading(true);
    setError('');

    try {
      const response = await getAgentRunDetail(runId);
      setData(response);
      setActiveStepKeys(response.steps.map((step) => String(step.step_index)));
    } catch (requestError) {
      setData(null);
      setError(getErrorText(requestError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const chainNodes = useMemo(() => {
    if (!data) return [];

    return buildChainNodes(data.run, data.steps);
  }, [data]);

  const focusStep = (stepIndex?: number): void => {
    if (!stepIndex) return;

    const key = String(stepIndex);
    setActiveStepKeys((prev) => Array.from(new Set([...prev, key])));

    window.requestAnimationFrame(() => {
      stepRefs.current[key]?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    });
  };

  const buildStepItems = (steps: AgentStepItem[]): CollapseProps['items'] =>
    steps.map((step) => {
      const key = String(step.step_index);

      return {
        key,
        label: (
          <div
            ref={(node) => {
              stepRefs.current[key] = node;
            }}
            className={styles.stepLabel}
          >
            <Space wrap>
              <Text strong>
                Step {step.step_index} · {step.tool_name || step.step_type}
              </Text>
              <Tag color={successColor(step.success)}>
                {step.success ? 'success' : 'failed'}
              </Tag>
              <Text type="secondary">{formatLatency(step.latency_ms)}</Text>
            </Space>
          </div>
        ),
        children: (
          <div className={styles.stepContent}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="step_type">
                {step.step_type || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="tool_name">
                {step.tool_name || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="reason">
                {step.reason || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="thought">
                {step.thought || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="result summary">
                {summarizeResult(step.tool_result)}
              </Descriptions.Item>
              <Descriptions.Item label="error">
                {step.error_code || step.error_message
                  ? `${step.error_code || ''} ${
                      step.error_message || ''
                    }`.trim()
                  : '-'}
              </Descriptions.Item>
            </Descriptions>

            <Collapse
              size="small"
              ghost
              items={[
                {
                  key: 'arguments',
                  label: 'arguments',
                  children: <JsonBlock value={step.tool_arguments} />,
                },
                {
                  key: 'result',
                  label: 'tool_result',
                  children: <JsonBlock value={step.tool_result} />,
                },
              ]}
            />
          </div>
        ),
      };
    });

  const buildEventItems = (events: AgentEventItem[]) =>
    events.map((event) => ({
      key: event.id,
      color:
        event.event_type.includes('error') || event.event_type.includes('fail')
          ? 'red'
          : event.event_type.includes('end')
          ? 'green'
          : 'blue',
      children: (
        <div className={styles.eventItem}>
          <Space wrap>
            <Text strong>{event.event_type}</Text>
            <Text type="secondary">{formatDateTime(event.created_at)}</Text>
            {event.step_id ? (
              <Tag color="default">step_id: {event.step_id}</Tag>
            ) : null}
          </Space>
          <Collapse
            size="small"
            ghost
            items={[
              {
                key: 'payload',
                label: 'payload',
                children: <JsonBlock value={event.payload} />,
              },
            ]}
          />
        </div>
      ),
    }));

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <Title level={2} className={styles.title}>
            Agent Run Detail
          </Title>
          <Paragraph className={styles.subtitle}>
            查看一次 Agent 执行的输入、步骤、工具结果和事件时间线。
          </Paragraph>
        </div>
        <Space wrap>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => history.push(backUrl)}
          >
            返回列表
          </Button>
          <Button icon={<MessageOutlined />} onClick={() => history.push('/')}>
            返回聊天
          </Button>
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => void fetchDetail()}
          >
            刷新
          </Button>
        </Space>
      </div>

      {error ? (
        <Alert className={styles.alert} type="error" showIcon message={error} />
      ) : null}

      {loading && !data ? (
        <Card className={styles.card}>
          <div className={styles.loadingBox}>
            <Spin />
          </div>
        </Card>
      ) : null}

      {!loading && !data && !error ? (
        <Card className={styles.card}>
          <Empty description="暂无 Run 详情" />
        </Card>
      ) : null}

      {data ? (
        <>
          <Card className={styles.card} title="Run 信息">
            <Descriptions column={2} bordered>
              <Descriptions.Item label="run_id" span={2}>
                <Text copyable>{data.run.id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="status">
                <Tag color={statusColor(data.run.status)}>
                  {data.run.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="model">
                {data.run.model || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="provider">
                {data.run.provider || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="total_latency_ms">
                {formatLatency(data.run.total_latency_ms)}
              </Descriptions.Item>
              <Descriptions.Item label="input" span={2}>
                {data.run.input ? (
                  <div className={styles.markdownBlock}>
                    {renderMarkdown(data.run.input)}
                  </div>
                ) : (
                  <Paragraph className={styles.longText}>-</Paragraph>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="final_answer" span={2}>
                {data.run.final_answer ? (
                  <div className={styles.markdownBlock}>
                    {renderMarkdown(data.run.final_answer)}
                  </div>
                ) : (
                  <Paragraph className={styles.longText}>-</Paragraph>
                )}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card className={styles.card} title="执行链路">
            <div className={styles.traceChain}>
              {chainNodes.map((node, index) => (
                <React.Fragment key={node.key}>
                  <button
                    type="button"
                    className={`${styles.chainNode} ${
                      styles[`chainNode_${node.status}`]
                    }`}
                    onClick={() => focusStep(node.stepIndex)}
                  >
                    <span className={styles.chainIcon}>
                      {node.key === 'input' ? (
                        <UserOutlined />
                      ) : node.status === 'error' ? (
                        <CloseCircleOutlined />
                      ) : node.status === 'processing' ? (
                        <ClockCircleOutlined />
                      ) : (
                        <CheckCircleOutlined />
                      )}
                    </span>
                    <span className={styles.chainBody}>
                      <Text strong ellipsis={{ tooltip: node.title }}>
                        {node.title}
                      </Text>
                      <Text type="secondary" className={styles.chainMeta}>
                        {node.meta}
                      </Text>
                    </span>
                  </button>
                  {index < chainNodes.length - 1 ? (
                    <span className={styles.chainConnector} />
                  ) : null}
                </React.Fragment>
              ))}
            </div>
          </Card>

          <Card className={styles.card} title="Steps">
            {data.steps.length > 0 ? (
              <Collapse
                activeKey={activeStepKeys}
                items={buildStepItems(data.steps)}
                onChange={(keys) =>
                  setActiveStepKeys(
                    Array.isArray(keys) ? keys.map(String) : [String(keys)],
                  )
                }
              />
            ) : (
              <Empty description="暂无 Step 数据" />
            )}
          </Card>

          <Card className={styles.card} title="Events">
            {data.events.length > 0 ? (
              <Timeline items={buildEventItems(data.events)} />
            ) : (
              <Empty description="暂无 Event 数据" />
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
};

export default AgentTraceDetailPage;
