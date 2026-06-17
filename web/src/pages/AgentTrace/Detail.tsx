import JsonViewer from '@/components/JsonViewer';
import { ArtifactPreview, MultiAgentRoleGraph } from '@/components/TraceDrawer';
import { MultiAgentTrace, TraceDetailResponse, TraceSpan, getTrace } from '@/services';
import {
  ApartmentOutlined,
  ArrowLeftOutlined,
  BranchesOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  FileDoneOutlined,
  MessageOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SendOutlined,
  ToolOutlined,
  WarningFilled,
} from '@ant-design/icons';
import { XMarkdown } from '@ant-design/x-markdown';
import { history, useLocation, useParams } from '@umijs/max';
import { Alert, Button, Card, Collapse, Descriptions, Empty, Modal, Segmented, Space, Spin, Tag, Timeline, Typography } from 'antd';
import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import styles from './index.module.less';

const { Paragraph, Text, Title } = Typography;
type RecordValue = Record<string, unknown>;
const isRecord = (value: unknown): value is RecordValue => !!value && typeof value === 'object' && !Array.isArray(value);
const record = (value: unknown): RecordValue => (isRecord(value) ? value : {});
const records = (value: unknown): RecordValue[] => (Array.isArray(value) ? value.filter(isRecord) : []);
const text = (value: unknown, fallback = '-') => typeof value === 'string' && value ? value : fallback;
const number = (value: unknown) => typeof value === 'number' ? value : undefined;
const formatLatency = (value: unknown) => {
  const ms = number(value);
  return ms === undefined ? '-' : ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
};
const formatTime = (value: unknown) => typeof value === 'string' ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-';
const statusColor = (value: unknown) => {
  const status = text(value, 'unknown');
  return ['completed', 'success'].includes(status) ? 'success' : status === 'running' ? 'processing' : ['failed', 'error'].includes(status) ? 'error' : 'default';
};
const markdownComponents = { a: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a {...props} target="_blank" rel="noopener noreferrer" /> };

const spanLabel: Record<string, string> = {
  'assistant.run': 'Assistant 运行',
  'router.decision': '模式路由',
  'multi_agent.run': 'Multi-Agent',
  'multi_agent.supervisor': 'Supervisor',
  'multi_agent.role': '角色执行',
  'multi_agent.handoff': '角色交接',
  'multi_agent.review': 'Review',
  'agent.run': 'Agent 执行',
  'planner.decision': 'Planner 决策',
  'tool.call': '工具调用',
  'mcp.call': 'MCP 调用',
  'llm.call': '模型调用',
  'context.assemble': '上下文组装',
  'context.final_assemble': '最终上下文',
  'memory.short_term.load': '短期记忆',
  'memory.long_term.retrieve': '长期记忆检索',
  'memory.long_term.write': '长期记忆写入',
};

const roleIcon = (role: string) => role === 'research' ? <SearchOutlined /> : role === 'coding' ? <CodeOutlined /> : role === 'review' ? <CheckCircleFilled /> : <RobotOutlined />;

const AgentTraceDetailPage: React.FC = () => {
  const { runId = '' } = useParams<{ runId: string }>();
  const location = useLocation();
  const [data, setData] = useState<TraceDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<string>('全局流程');
  const [artifactPreview, setArtifactPreview] = useState<ArtifactPreview | null>(null);
  const conversationId = new URLSearchParams(location.search).get('conversation_id') || '';

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setData(await getTrace(decodeURIComponent(runId)));
    } catch (requestError) {
      if (axios.isAxiosError(requestError)) setError(requestError.response?.data?.detail || requestError.message);
      else setError(requestError instanceof Error ? requestError.message : '获取 Trace 失败');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, [runId]);

  const parsed = useMemo(() => {
    const runTrace = record(data?.run?.trace);
    const multi = record(runTrace.multi_agent);
    const coordinator = record(multi.coordinator);
    return {
      multi,
      coordinator,
      rounds: records(coordinator.rounds),
      roleRuns: records(coordinator.role_runs).length ? records(coordinator.role_runs) : records(multi.role_runs),
      artifacts: records(multi.artifacts).length ? records(multi.artifacts) : records(coordinator.artifacts),
      handoffs: records(multi.handoffs).length ? records(multi.handoffs) : records(coordinator.handoffs),
      toolCalls: records(multi.tool_calls).length ? records(multi.tool_calls) : records(coordinator.tool_calls),
    };
  }, [data]);

  const backUrl = conversationId ? `/traces?conversation_id=${encodeURIComponent(conversationId)}` : '/traces';
  const root = data?.spans.find((span) => !span.parent_span_id);
  const flowTrace = useMemo<MultiAgentTrace>(() => {
    const roles = Array.from(new Set([
      ...records(parsed.multi.roles_used).map((item) => text(item.role, '')),
      ...parsed.roleRuns.map((item) => text(item.role, '')),
      ...parsed.artifacts.map((item) => text(item.role, '')),
    ].filter(Boolean)));
    return {
      enabled: true,
      run_id: text(parsed.multi.run_id, ''),
      roles_used: roles,
      artifact_count: parsed.artifacts.length,
      handoff_count: parsed.handoffs.length,
      review_decision: text(parsed.multi.review_decision, ''),
      coordinator: parsed.coordinator,
      artifacts: parsed.artifacts.map((item) => ({
        id: text(item.id, ''), role: text(item.role), artifact_type: text(item.artifact_type),
        title: text(item.title), confidence: number(item.confidence), content: text(item.content, ''),
        data: record(item.data), source_refs: records(item.source_refs), metadata: record(item.metadata),
      })),
      handoffs: parsed.handoffs.map((item) => ({
        id: text(item.id, ''), from_role: text(item.from_role), to_role: text(item.to_role),
        summary: text(item.summary), confidence: number(item.confidence),
      })),
      role_runs: [],
    };
  }, [parsed]);

  const renderRound = (round: RecordValue) => {
    const decision = record(round.decision);
    const role = text(decision.role || decision.target_role, 'coordinator');
    const roleRun = parsed.roleRuns.find((item) => text(item.role) === role && number(record(item.trace).coordinator_round_index) === number(round.round_index))
      || parsed.roleRuns[number(round.round_index)! - 1];
    const trace = record(roleRun?.trace);
    const steps = records(trace.steps);
    const plannerEvents = records(trace.role_planner_events);
    return (
      <div className={styles.roundCard}>
        <div className={styles.roundIndex}>R{number(round.round_index) || '?'}</div>
        <div className={styles.roundBody}>
          <div className={styles.roundHeader}>
            <Space wrap>
              <span className={`${styles.roleIcon} ${styles[`role_${role}`] || ''}`}>{roleIcon(role)}</span>
              <Text strong>{text(decision.task_title, text(decision.type))}</Text>
              <Tag color="geekblue">{text(decision.type)}</Tag>
              <Tag color={statusColor(round.status)}>{text(round.status)}</Tag>
            </Space>
            <Text type="secondary">{formatLatency(round.latency_ms)}</Text>
          </div>
          <Paragraph className={styles.reason}>{text(decision.reason)}</Paragraph>
          <div className={styles.roundFlow}>
            <span><BranchesOutlined /> Coordinator 决策</span><i />
            <span>{roleIcon(role)} {role}</span><i />
            <span><ToolOutlined /> {steps.filter((step) => step.type === 'tool_call').length} tools</span><i />
            <span><FileDoneOutlined /> {round.artifact_id ? 'artifact' : 'no artifact'}</span>
          </div>
          {(steps.length || plannerEvents.length || roleRun) ? (
            <Collapse ghost size="small" items={[{
              key: 'inside',
              label: `展开 ${role} 内部执行 (${steps.length} steps)`,
              children: <div className={styles.innerSteps}>
                {plannerEvents.map((event, index) => <div className={styles.plannerEvent} key={index}><Tag>planner {index + 1}</Tag><Text>{text(record(event.decision).reason, text(event.error_message, '决策已记录'))}</Text><Text type="secondary">{formatLatency(event.latency_ms)}</Text></div>)}
                {steps.map((step, index) => <div className={styles.stepRow} key={index}><span className={styles.stepDot} /><div><Space wrap><Text strong>Step {number(step.step) || index + 1}</Text><Tag color={step.success === false ? 'error' : step.type === 'final' ? 'success' : 'blue'}>{text(step.type)}</Tag>{step.tool_name ? <Tag icon={<ToolOutlined />}>{text(step.tool_name)}</Tag> : null}<Text type="secondary">{formatLatency(step.latency_ms)}</Text></Space><Paragraph>{text(step.reason)}</Paragraph>{step.error_message ? <Alert type="error" showIcon message={text(step.error_message)} /> : null}<Collapse ghost size="small" items={[{ key: 'raw', label: '参数与结果', children: <JsonViewer value={{ arguments: step.arguments, result: step.result, decision: step.decision }} /> }]} /></div></div>)}
                {!steps.length ? <Alert type="warning" showIcon message="本轮没有角色步骤数据" description="服务端角色入口失败或尚未把 role trace 写入 coordinator state。" /> : null}
              </div>,
            }]} />
          ) : null}
        </div>
      </div>
    );
  };

  const spanItems = data?.spans.map((span: TraceSpan) => ({
    key: span.id,
    color: span.status === 'error' ? 'red' : span.status === 'running' ? 'blue' : 'green',
    children: <div className={styles.spanItem}><div className={styles.spanHeader}><Space wrap><Tag color={statusColor(span.status)}>{spanLabel[span.span_type] || span.span_type}</Tag><Text strong>{span.name}</Text></Space><Text type="secondary">{formatLatency(span.latency_ms)}</Text></div><Text type="secondary">{formatTime(span.started_at)} · {span.id}</Text>{span.error_message ? <Alert type="error" showIcon message={span.error_message} /> : null}<Collapse ghost size="small" items={[{ key: 'io', label: 'Input / Output / Metadata', children: <JsonViewer value={{ input: span.input, output: span.output, metadata: span.metadata }} /> }]} /></div>,
  })) || [];

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <div><div className={styles.eyebrow}><ApartmentOutlined /> TRACE DETAIL</div><Title level={2} className={styles.title}>Execution Blueprint</Title><Paragraph className={styles.subtitle}>按服务端真实状态重建 Coordinator 与角色内部循环，不补画不存在的节点。</Paragraph></div>
        <Space wrap><Button icon={<ArrowLeftOutlined />} onClick={() => history.push(backUrl)}>返回列表</Button><Button icon={<MessageOutlined />} onClick={() => history.push('/')}>返回聊天</Button><Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button></Space>
      </header>
      {error ? <Alert className={styles.alert} type="error" showIcon message={error} /> : null}
      {loading && !data ? <div className={styles.loading}><Spin size="large" /></div> : null}
      {data ? <>
        <section className={styles.detailMetrics}>
          <div><span>状态</span><strong><Tag color={statusColor(data.run?.status || root?.status)}>{data.run?.status || root?.status || '-'}</Tag></strong></div>
          <div><span>总耗时</span><strong>{formatLatency(data.run?.latency_ms || data.summary.total_latency_ms)}</strong></div>
          <div><span>Coordinator</span><strong>{parsed.rounds.length} rounds</strong></div>
          <div><span>角色 / 产物</span><strong>{parsed.roleRuns.length} / {parsed.artifacts.length}</strong></div>
          <div><span>工具 / Tokens</span><strong>{parsed.toolCalls.length || data.summary.tool_call_count || 0} / {data.summary.total_tokens || 0}</strong></div>
        </section>

        <Card className={styles.overviewCard}>
          <Descriptions column={{ xs: 1, md: 2 }} size="small">
            <Descriptions.Item label="Trace ID"><Text copyable code>{data.trace_id}</Text></Descriptions.Item>
            <Descriptions.Item label="Multi-Agent Run"><Text copyable>{text(parsed.multi.run_id)}</Text></Descriptions.Item>
            <Descriptions.Item label="模型">{data.run?.model || '-'} · {data.run?.provider || '-'}</Descriptions.Item>
            <Descriptions.Item label="结束原因">{text(parsed.coordinator.finish_reason, text(record(data.run?.trace).finish_reason))}</Descriptions.Item>
          </Descriptions>
          <div className={styles.question}><span>USER REQUEST</span><Paragraph>{data.run?.input || text(root?.input?.message)}</Paragraph></div>
        </Card>

        <Segmented block className={styles.viewSwitch} options={[{ label: '全局流程', value: '全局流程', icon: <BranchesOutlined /> }, { label: '角色产物', value: '角色产物', icon: <FileDoneOutlined /> }, { label: '统一 Spans', value: '统一 Spans', icon: <DatabaseOutlined /> }, { label: '最终回答', value: '最终回答', icon: <SendOutlined /> }]} value={view} onChange={(value) => setView(String(value))} />

        {view === '全局流程' ? <>
          <Card className={styles.flowGraphCard} title="Dynamic Execution Flow">
            <MultiAgentRoleGraph trace={flowTrace} onOpenArtifact={setArtifactPreview} />
          </Card>
          <div className={styles.flowLayout}>
          <aside className={styles.architectureRail}>
            <div className={styles.archNode}><MessageOutlined /><span>Assistant</span><small>request accepted</small></div><i />
            <div className={styles.archNode}><BranchesOutlined /><span>Router</span><small>{text(record(data.run?.trace).route_decision && record(record(data.run?.trace).route_decision).mode, data.run?.mode || '-')}</small></div><i />
            <div className={`${styles.archNode} ${styles.archNodeActive}`}><ApartmentOutlined /><span>Coordinator</span><small>dynamic loop</small></div><i />
            <div className={styles.archNode}><RobotOutlined /><span>Role Runtime</span><small>planner + tools</small></div><i />
            <div className={styles.archNode}><SendOutlined /><span>Final Synthesis</span><small>context assemble</small></div>
          </aside>
          <main className={styles.roundsPanel}>
            <div className={styles.sectionHeading}><div><Text strong>Coordinator Decision Loop</Text><Paragraph>{text(parsed.coordinator.finish_reason, '暂无结束原因')}</Paragraph></div><Space><Tag>{parsed.coordinator.revision_count ? `${parsed.coordinator.revision_count} revision` : 'no revision'}</Tag>{parsed.coordinator.failed_round_count ? <Tag color="error" icon={<WarningFilled />}>{String(parsed.coordinator.failed_round_count)} failed</Tag> : null}</Space></div>
            {parsed.rounds.length ? parsed.rounds.map((round) => <React.Fragment key={String(round.round_index)}>{renderRound(round)}</React.Fragment>) : <Alert type="warning" showIcon message="未发现 Coordinator Round" description="该运行可能来自旧流程，或服务端在进入动态循环前已失败。统一 Span 仍可在对应视图查看。" />}
          </main>
          </div>
        </> : null}

        {view === '角色产物' ? <div className={styles.artifactGrid}>{parsed.artifacts.length ? parsed.artifacts.map((artifact) => <Card key={text(artifact.id)} className={styles.artifactCard} title={<Space>{roleIcon(text(artifact.role))}<span>{text(artifact.title)}</span></Space>} extra={<Tag>{text(artifact.artifact_type)}</Tag>}><Space wrap><Tag color="geekblue">{text(artifact.role)}</Tag><Tag>confidence {number(artifact.confidence)?.toFixed(2) || '-'}</Tag></Space><div className={styles.markdown}><XMarkdown content={text(artifact.content, '')} components={markdownComponents} /></div><Collapse ghost size="small" items={[{ key: 'data', label: '结构化数据与来源', children: <JsonViewer value={{ data: artifact.data, source_refs: artifact.source_refs, metadata: artifact.metadata }} /> }]} /></Card>) : <Card><Empty description="暂无角色产物" /></Card>}</div> : null}
        {view === '统一 Spans' ? <Card className={styles.contentCard}><Timeline items={spanItems} /></Card> : null}
        {view === '最终回答' ? <Card className={styles.contentCard} title="Final Answer"><div className={styles.finalAnswer}><XMarkdown content={data.run?.final_answer || '暂无最终回答'} components={markdownComponents} /></div></Card> : null}
      </> : !loading && !error ? <Card><Empty description="暂无 Trace 数据" /></Card> : null}
      <Modal
        open={Boolean(artifactPreview)}
        title={artifactPreview?.title}
        footer={null}
        width="92vw"
        onCancel={() => setArtifactPreview(null)}
        destroyOnHidden
      >
        <div className={styles.artifactPreviewModal}>
          <XMarkdown content={artifactPreview?.content || ''} components={markdownComponents} />
        </div>
      </Modal>
    </div>
  );
};

export default AgentTraceDetailPage;
