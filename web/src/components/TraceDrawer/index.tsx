import { ChatMessage } from '@/contexts/ChatContext';
import JsonViewer from '@/components/JsonViewer';
import FlowCanvas from '@/components/FlowCanvas';
import ToolCallTimeline from '@/components/ToolCallTimeline';
import { XMarkdown } from '@ant-design/x-markdown';
import type {
  MultiAgentTrace,
  TraceDetailResponse,
  TraceSpan,
  TraceSummary,
} from '@/services/api';
import { getTrace } from '@/services/api';
import { FullscreenOutlined, InfoCircleOutlined } from '@ant-design/icons';
import {
  Button,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  List,
  Modal,
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
type MultiAgentRoleRun = NonNullable<MultiAgentTrace['role_runs']>[number];
type MultiAgentHandoff = MultiAgentTrace['handoffs'][number];
type MultiAgentArtifact = MultiAgentTrace['artifacts'][number];

interface RoleGraphNode {
  id: string;
  kind: 'start' | 'decision' | 'role' | 'finish';
  title: string;
  subtitle: string;
  status: string;
  x: number;
  y: number;
  run?: MultiAgentRoleRun;
  round?: JsonRecord;
}

interface RoleGraphEdge {
  id: string;
  from: string;
  to: string;
  summary: string;
  confidence?: number;
  dashed?: boolean;
}

export interface ArtifactPreview {
  title: string;
  role?: string;
  artifactType?: string;
  content: string;
}

const markdownComponents = {
  a: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
};

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function getRecord(value: unknown): JsonRecord | undefined {
  return isRecord(value) ? value : undefined;
}

function getRecordArray(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function getStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
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

function compactText(value: string, max = 28): string {
  return value.length > max ? `${value.slice(0, max)}...` : value;
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

function renderMarkdown(content: string) {
  return <XMarkdown content={content} components={markdownComponents} />;
}

function renderArtifactMarkdown(
  artifact: ArtifactPreview,
  onOpenArtifact: (artifact: ArtifactPreview) => void,
) {
  return (
    <div className={styles.artifactMarkdownShell}>
      <div className={styles.artifactMarkdownToolbar}>
        <div className={styles.artifactMarkdownMeta}>
          {artifact.role ? <Tag color="geekblue">{artifact.role}</Tag> : null}
          {artifact.artifactType ? <Tag>{artifact.artifactType}</Tag> : null}
        </div>
        <Button
          size="small"
          icon={<FullscreenOutlined />}
          onClick={() => onOpenArtifact(artifact)}
        >
          全屏查看
        </Button>
      </div>
      <div className={styles.artifactMarkdownPreview}>
        {renderMarkdown(artifact.content)}
      </div>
    </div>
  );
}

function normalizeHandoff(item: JsonRecord): MultiAgentHandoff {
  return {
    id: getString(item.id) || '',
    from_role: getString(item.from_role) || '-',
    to_role: getString(item.to_role) || '-',
    summary: getString(item.summary) || '-',
    confidence: getNumber(item.confidence),
  };
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

function confidenceTag(value?: number) {
  if (value === undefined) return null;

  const color = value >= 0.7 ? 'success' : value >= 0.4 ? 'warning' : 'error';
  return <Tag color={color}>{value.toFixed(2)}</Tag>;
}

function reviewDecisionTag(value?: string) {
  if (!value) return <Text type="secondary">-</Text>;

  const color =
    value === 'pass' ? 'success' : value === 'reject' ? 'error' : 'warning';
  return <Tag color={color}>{value}</Tag>;
}

function normalizeRoleRun(item: JsonRecord): MultiAgentRoleRun {
  const artifact = getRecord(item.artifact);
  const handoffs = getRecord(item.handoffs);

  return {
    role: getString(item.role) || '-',
    status: getString(item.status) || 'unknown',
    latency_ms: getNumber(item.latency_ms),
    error_code: getString(item.error_code),
    error_message: getString(item.error_message),
    artifact: artifact
      ? {
          id: getString(artifact.id) || '',
          role: getString(artifact.role) || getString(item.role) || '-',
          artifact_type: getString(artifact.artifact_type) || '-',
          title: getString(artifact.title) || '-',
          confidence: getNumber(artifact.confidence),
          content: getString(artifact.content),
          data: getRecord(artifact.data),
          source_refs: getRecordArray(artifact.source_refs),
          metadata: getRecord(artifact.metadata),
        }
      : null,
    trace: getRecord(item.trace),
    tool_calls: getRecordArray(item.tool_calls),
    handoffs: {
      incoming: getRecordArray(handoffs?.incoming).map(normalizeHandoff),
      outgoing: getRecordArray(handoffs?.outgoing).map(normalizeHandoff),
    },
  };
}

function roleRunStatusTag(status: string) {
  const color =
    status === 'completed'
      ? 'success'
      : status === 'failed'
      ? 'error'
      : status === 'running'
      ? 'processing'
      : 'default';
  return <Tag color={color}>{status}</Tag>;
}

function buildRoleGraph(trace: MultiAgentTrace): {
  nodes: RoleGraphNode[];
  edges: RoleGraphEdge[];
  width: number;
  height: number;
} {
  const coordinator = getRecord(trace.coordinator) || {};
  const rounds = getRecordArray(coordinator.rounds);
  const coordinatorRuns = getRecordArray(coordinator.role_runs).map(normalizeRoleRun);
  const sourceRuns = coordinatorRuns.length ? coordinatorRuns : trace.role_runs || [];
  const nodes: RoleGraphNode[] = [];
  const edges: RoleGraphEdge[] = [];
  const nodeGap = 238;
  const startX = 34;
  let actionRunIndex = 0;
  let previousNodeId = 'start';

  const supervisorRun = (trace.role_runs || []).find(
    (run) => run.role === 'supervisor',
  );
  nodes.push({
    id: 'start',
    kind: 'start',
    title: supervisorRun ? 'Supervisor' : 'Assistant Router',
    subtitle: supervisorRun?.artifact?.title || '进入动态编排',
    status: supervisorRun?.status || 'completed',
    x: startX,
    y: 122,
    run: supervisorRun,
  });

  if (rounds.length > 0) {
    rounds.forEach((round, index) => {
      const decision = getRecord(round.decision) || {};
      const decisionType = getString(decision.type) || 'unknown';
      const role = getString(decision.role, decision.target_role);
      const roundNumber = getNumber(round.round_index) ?? index + 1;
      const x = startX + (index + 1) * nodeGap;
      const decisionId = `round-${roundNumber}-decision`;
      const isRoleAction = ['run_role', 'revise_role', 'request_review'].includes(
        decisionType,
      );

      nodes.push({
        id: decisionId,
        kind: decisionType === 'final' || decisionType === 'fail' ? 'finish' : 'decision',
        title: `Round ${roundNumber} · ${decisionType}`,
        subtitle: getString(decision.task_title, decision.reason) || '-',
        status: getString(round.status) || 'unknown',
        x,
        y: 34,
        round,
      });
      edges.push({
        id: `${previousNodeId}-${decisionId}`,
        from: previousNodeId,
        to: decisionId,
        summary: `进入第 ${roundNumber} 轮`,
      });

      if (isRoleAction && role) {
        const run = sourceRuns[actionRunIndex++];
        const artifactId = getString(round.artifact_id, getRecord(run?.trace)?.artifact_id);
        const artifact = trace.artifacts.find(
          (item) => item.id === artifactId,
        ) || trace.artifacts.find((item) => item.role === role);
        const enrichedRun: MultiAgentRoleRun = run
          ? { ...run, artifact: run.artifact || artifact || null }
          : {
              role,
              status: getString(round.status) || 'unknown',
              artifact: artifact || null,
              trace: {},
              tool_calls: [],
            };
        const roleId = `round-${roundNumber}-role`;
        nodes.push({
          id: roleId,
          kind: 'role',
          title: role,
          subtitle: artifact?.title || getString(decision.task_title) || '角色执行',
          status: enrichedRun.status,
          x,
          y: 172,
          run: enrichedRun,
          round,
        });
        edges.push({
          id: `${decisionId}-${roleId}`,
          from: decisionId,
          to: roleId,
          summary: getString(decision.reason) || `调度 ${role}`,
          confidence: getNumber(decision.confidence),
        });
        previousNodeId = roleId;
      } else {
        previousNodeId = decisionId;
      }
    });
  } else {
    sourceRuns.forEach((run, index) => {
      const id = `legacy-role-${index}`;
      nodes.push({
        id,
        kind: 'role',
        title: run.role,
        subtitle: run.artifact?.title || '角色执行',
        status: run.status,
        x: startX + (index + 1) * nodeGap,
        y: 122,
        run,
      });
      edges.push({ id: `${previousNodeId}-${id}`, from: previousNodeId, to: id, summary: '执行顺序' });
      previousNodeId = id;
    });
  }

  const finishReason = getString(coordinator.finish_reason);
  if (finishReason && !nodes.some((node) => node.kind === 'finish')) {
    const finishId = 'finish';
    nodes.push({
      id: finishId,
      kind: 'finish',
      title: 'Final Synthesis',
      subtitle: finishReason,
      status: finishReason.includes('fail') ? 'failed' : 'completed',
      x: startX + (Math.max(rounds.length, sourceRuns.length) + 1) * nodeGap,
      y: 122,
    });
    edges.push({ id: `${previousNodeId}-${finishId}`, from: previousNodeId, to: finishId, summary: finishReason });
  }

  trace.handoffs.forEach((handoff, index) => {
    const fromNodes = nodes.filter((node) => node.kind === 'role' && node.title === handoff.from_role);
    const toNode = nodes.find((node) => node.kind === 'role' && node.title === handoff.to_role && node.x > (fromNodes.at(-1)?.x || 0));
    const fromNode = fromNodes.at(-1);
    if (fromNode && toNode) {
      edges.push({
        id: `handoff-${handoff.id || index}`,
        from: fromNode.id,
        to: toNode.id,
        summary: handoff.summary,
        confidence: handoff.confidence,
        dashed: true,
      });
    }
  });

  const maxX = Math.max(...nodes.map((node) => node.x), 760);
  return { nodes, edges, width: Math.max(900, maxX + 220), height: 300 };
}

function renderHandoffList(title: string, handoffs: MultiAgentHandoff[]) {
  return (
    <div className={styles.roleRunSubsection}>
      <Text strong className={styles.roleRunSubTitle}>
        {title}
      </Text>
      {handoffs.length > 0 ? (
        <List
          size="small"
          dataSource={handoffs}
          renderItem={(handoff) => (
            <List.Item className={styles.listItem}>
              <div className={styles.multiAgentItem}>
                <div>
                  <Text code>{handoff.from_role}</Text>
                  <Text type="secondary"> {'->'} </Text>
                  <Text code>{handoff.to_role}</Text>
                  {confidenceTag(handoff.confidence)}
                </div>
                <Text type="secondary">{handoff.summary}</Text>
              </div>
            </List.Item>
          )}
        />
      ) : (
        <Text type="secondary">-</Text>
      )}
    </div>
  );
}

function renderRoleRun(
  run: MultiAgentRoleRun,
  onOpenArtifact: (artifact: ArtifactPreview) => void,
) {
  const incomingHandoffs = run.handoffs?.incoming || [];
  const outgoingHandoffs = run.handoffs?.outgoing || [];
  const artifact = run.artifact;
  const roleSteps = getRecordArray(run.trace?.steps);
  const plannerEvents = getRecordArray(run.trace?.role_planner_events);

  return (
    <div className={styles.roleRunDetail}>
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="Role">{run.role}</Descriptions.Item>
        <Descriptions.Item label="Status">
          {roleRunStatusTag(run.status)}
        </Descriptions.Item>
        <Descriptions.Item label="Latency">
          {formatLatency(run.latency_ms)}
        </Descriptions.Item>
        <Descriptions.Item label="Tool Calls">
          {run.tool_calls?.length || 0}
        </Descriptions.Item>
        <Descriptions.Item label="Artifact" span={2}>
          {artifact ? (
            <>
              <Text strong>{artifact.title}</Text>
              <Tag className={styles.inlineTag}>{artifact.artifact_type}</Tag>
              {confidenceTag(artifact.confidence)}
            </>
          ) : (
            <Text type="secondary">-</Text>
          )}
        </Descriptions.Item>
        {(run.error_code || run.error_message) && (
          <Descriptions.Item label="Error" span={2}>
            <Text type="danger">
              {run.error_code ? `[${run.error_code}] ` : ''}
              {run.error_message || 'error'}
            </Text>
          </Descriptions.Item>
        )}
      </Descriptions>

      {artifact?.content ? (
        <div className={styles.roleRunSubsection}>
          <Text strong className={styles.roleRunSubTitle}>
            Artifact Content
          </Text>
          {renderArtifactMarkdown(
            {
              title: artifact.title,
              role: artifact.role,
              artifactType: artifact.artifact_type,
              content: artifact.content,
            },
            onOpenArtifact,
          )}
        </div>
      ) : null}

      {artifact?.data && Object.keys(artifact.data).length > 0 ? (
        <div className={styles.roleRunSubsection}>
          <Text strong className={styles.roleRunSubTitle}>
            Artifact Data
          </Text>
          <JsonViewer value={artifact.data} maxHeight={260} />
        </div>
      ) : null}

      <div className={styles.roleRunSubsection}>
        <Text strong className={styles.roleRunSubTitle}>
          Tool Calls
        </Text>
        <ToolCallTimeline toolCalls={run.tool_calls} />
      </div>

      {roleSteps.length > 0 || plannerEvents.length > 0 ? (
        <div className={styles.roleRunSubsection}>
          <Text strong className={styles.roleRunSubTitle}>
            Planner / Role Steps ({roleSteps.length})
          </Text>
          <Collapse
            size="small"
            className={styles.summaryCollapse}
            items={[
              ...roleSteps.map((step, index) => ({
                key: `step-${index}`,
                label: (
                  <div className={styles.roleRunHeader}>
                    <Text>Step {getNumber(step.step) ?? index + 1}</Text>
                    <Tag color={step.success === false ? 'error' : step.type === 'final' ? 'success' : 'blue'}>
                      {getString(step.type) || 'unknown'}
                    </Tag>
                    {getString(step.tool_name) ? <Tag>{getString(step.tool_name)}</Tag> : null}
                    <Text type="secondary">{formatLatency(getNumber(step.latency_ms))}</Text>
                  </div>
                ),
                children: <JsonViewer value={step} maxHeight={300} />,
              })),
              ...(plannerEvents.length
                ? [{ key: 'planner-events', label: `Planner Events (${plannerEvents.length})`, children: <JsonViewer value={plannerEvents} maxHeight={320} /> }]
                : []),
            ]}
          />
        </div>
      ) : null}

      {renderHandoffList('Incoming Handoffs', incomingHandoffs)}
      {renderHandoffList('Outgoing Handoffs', outgoingHandoffs)}

      {run.trace && Object.keys(run.trace).length > 0 ? (
        <div className={styles.roleRunSubsection}>
          <Text strong className={styles.roleRunSubTitle}>
            Role Trace
          </Text>
          <JsonViewer value={run.trace} maxHeight={320} />
        </div>
      ) : null}
    </div>
  );
}

export const MultiAgentRoleGraph: React.FC<{
  trace: MultiAgentTrace;
  onOpenArtifact: (artifact: ArtifactPreview) => void;
}> = ({ trace, onOpenArtifact }) => {
  const graph = useMemo(() => buildRoleGraph(trace), [trace]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | undefined>(
    graph.nodes[0]?.id,
  );
  const nodeMap = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node])),
    [graph.nodes],
  );
  const effectiveSelectedId = nodeMap.has(selectedNodeId || '')
    ? selectedNodeId
    : graph.nodes[0]?.id;
  const selectedNode = effectiveSelectedId
    ? nodeMap.get(effectiveSelectedId)
    : undefined;

  if (graph.nodes.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无角色执行过程"
      />
    );
  }

  return (
    <div className={styles.roleGraphShell}>
      <FlowCanvas
        width={graph.width}
        height={graph.height}
        ariaLabel="Multi-Agent role execution graph"
      >
          <defs>
            <marker
              id="roleGraphArrow"
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M0,0 L0,6 L9,3 z" className={styles.roleGraphArrow} />
            </marker>
          </defs>

          {graph.edges.map((edge) => {
            const fromNode = nodeMap.get(edge.from);
            const toNode = nodeMap.get(edge.to);
            if (!fromNode || !toNode) return null;

            const startX = fromNode.x + 180;
            const startY = fromNode.y + 35;
            const endX = toNode.x;
            const endY = toNode.y + 35;
            const controlOffset = Math.max(Math.abs(endX - startX) * 0.42, 48);
            const path = fromNode.x === toNode.x
              ? `M ${fromNode.x + 90} ${fromNode.y + 70} L ${toNode.x + 90} ${toNode.y}`
              : `M ${startX} ${startY} C ${startX + controlOffset} ${startY}, ${endX - controlOffset} ${endY}, ${endX} ${endY}`;
            const labelX = (startX + endX) / 2;
            const labelY = (startY + endY) / 2 - 10;

            return (
              <g key={edge.id}>
                <title>{edge.summary}</title>
                <path
                  d={path}
                  className={edge.dashed ? styles.roleGraphEdgeDashed : styles.roleGraphEdge}
                  markerEnd="url(#roleGraphArrow)"
                />
                {edge.confidence !== undefined ? (
                  <text
                    x={labelX}
                    y={labelY}
                    textAnchor="middle"
                    className={styles.roleGraphEdgeLabel}
                  >
                    {edge.confidence.toFixed(2)}
                  </text>
                ) : null}
              </g>
            );
          })}

          {graph.nodes.map((node) => {
            const isSelected = node.id === effectiveSelectedId;

            return (
              <g
                key={node.id}
                className={`${styles.roleGraphNode} ${styles[`roleGraphNode_${node.kind}`] || ''}`}
                transform={`translate(${node.x}, ${node.y})`}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedNodeId(node.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    setSelectedNodeId(node.id);
                  }
                }}
              >
                <title>{`${node.title}: ${node.subtitle}`}</title>
                <rect
                  width="180"
                  height="70"
                  rx="8"
                  className={
                    isSelected
                      ? styles.roleGraphNodeRectSelected
                      : styles.roleGraphNodeRect
                  }
                />
                <text x="14" y="22" className={styles.roleGraphNodeTitle}>
                  {compactText(node.title, 23)}
                </text>
                <text x="14" y="42" className={styles.roleGraphNodeStatus}>
                  {compactText(node.subtitle, 25)}
                </text>
                <text x="14" y="59" className={styles.roleGraphNodeMeta}>
                  {node.status} · {formatLatency(node.run?.latency_ms || getNumber(node.round?.latency_ms))}
                </text>
              </g>
            );
          })}
      </FlowCanvas>

      <div className={styles.roleGraphDetail}>
        {selectedNode?.run ? (
          renderRoleRun(selectedNode.run, onOpenArtifact)
        ) : selectedNode?.round ? (
          <div className={styles.roleRunDetail}>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="Node">{selectedNode.title}</Descriptions.Item>
              <Descriptions.Item label="Status">{roleRunStatusTag(selectedNode.status)}</Descriptions.Item>
              <Descriptions.Item label="Latency">{formatLatency(getNumber(selectedNode.round.latency_ms))}</Descriptions.Item>
              <Descriptions.Item label="Artifact ID">{getString(selectedNode.round.artifact_id) || '-'}</Descriptions.Item>
            </Descriptions>
            <JsonViewer value={selectedNode.round} maxHeight={420} />
          </div>
        ) : (
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="Node">{selectedNode?.title || '-'}</Descriptions.Item>
            <Descriptions.Item label="Status">{selectedNode?.status || '-'}</Descriptions.Item>
            <Descriptions.Item label="Description" span={2}>{selectedNode?.subtitle || '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </div>
    </div>
  );
};

function renderMultiAgentSummary(
  trace: MultiAgentTrace,
  onOpenArtifact: (artifact: ArtifactPreview) => void,
) {
  return (
    <Collapse
      size="small"
      className={styles.summaryCollapse}
      items={[
        {
          key: 'roles',
          label: `Roles Used (${trace.roles_used.length})`,
          children:
            trace.roles_used.length > 0 ? (
              <List
                size="small"
                dataSource={trace.roles_used}
                renderItem={(role) => (
                  <List.Item className={styles.listItem}>
                    <Tag color="blue">{role}</Tag>
                  </List.Item>
                )}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无角色" />
            ),
        },
        {
          key: 'handoffs',
          label: `Handoffs (${trace.handoffs.length})`,
          children:
            trace.handoffs.length > 0 ? (
              <List
                size="small"
                dataSource={trace.handoffs}
                renderItem={(handoff) => (
                  <List.Item className={styles.listItem}>
                    <div className={styles.multiAgentItem}>
                      <div>
                        <Text code>{handoff.from_role}</Text>
                        <Text type="secondary"> {'->'} </Text>
                        <Text code>{handoff.to_role}</Text>
                        {confidenceTag(handoff.confidence)}
                      </div>
                      <Text type="secondary">{handoff.summary}</Text>
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无 Handoffs"
              />
            ),
        },
        {
          key: 'artifacts',
          label: `Artifacts (${trace.artifacts.length})`,
          children:
            trace.artifacts.length > 0 ? (
              <List
                size="small"
                dataSource={trace.artifacts}
                renderItem={(artifact: MultiAgentArtifact) => (
                  <List.Item className={styles.listItem}>
                    <div className={styles.multiAgentItem}>
                      <div>
                        <Text strong>{artifact.title}</Text>
                        <Tag color="geekblue">{artifact.role}</Tag>
                        <Tag>{artifact.artifact_type}</Tag>
                        {confidenceTag(artifact.confidence)}
                      </div>
                      {artifact.content
                        ? renderArtifactMarkdown(
                            {
                              title: artifact.title,
                              role: artifact.role,
                              artifactType: artifact.artifact_type,
                              content: artifact.content,
                            },
                            onOpenArtifact,
                          )
                        : null}
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无 Artifacts"
              />
            ),
        },
      ]}
    />
  );
}

function renderMultiAgentTrace(
  trace: MultiAgentTrace | undefined,
  onOpenArtifact: (artifact: ArtifactPreview) => void,
) {
  if (!trace?.enabled) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无 Multi-Agent Trace"
      />
    );
  }

  const coordinator = getRecord(trace.coordinator);
  const rounds = getRecordArray(coordinator?.rounds);

  return (
    <>
      <Descriptions
        column={2}
        size="small"
        bordered
        className={styles.descriptions}
      >
        <Descriptions.Item label="Run ID" span={2}>
          {trace.run_id ? (
            <Text copyable code className={styles.idText}>
              {trace.run_id}
            </Text>
          ) : (
            <Text type="secondary">-</Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="Roles Used">
          {trace.roles_used.length}
        </Descriptions.Item>
        <Descriptions.Item label="Handoffs">
          {trace.handoff_count}
        </Descriptions.Item>
        <Descriptions.Item label="Artifacts">
          {trace.artifact_count}
        </Descriptions.Item>
        <Descriptions.Item label="Review Decision">
          {reviewDecisionTag(trace.review_decision)}
        </Descriptions.Item>
        <Descriptions.Item label="Coordinator Rounds">
          {rounds.length}
        </Descriptions.Item>
        <Descriptions.Item label="Finish Reason">
          {getString(coordinator?.finish_reason) || '-'}
        </Descriptions.Item>
      </Descriptions>

      <div className={styles.section}>
        <Text strong className={styles.sectionTitle}>
          Dynamic Execution Flow
        </Text>
        <MultiAgentRoleGraph trace={trace} onOpenArtifact={onOpenArtifact} />
      </div>

      <div className={styles.section}>
        <Text strong className={styles.sectionTitle}>
          Execution Summary
        </Text>
        {renderMultiAgentSummary(trace, onOpenArtifact)}
      </div>
    </>
  );
}

function getTraceSummary(msg: ChatMessage, detail: TraceDetailResponse | null) {
  return detail?.summary || msg.traceSummary || {};
}

function getMultiAgentTrace(
  msg: ChatMessage,
  detail: TraceDetailResponse | null,
): MultiAgentTrace | undefined {
  const candidates = [
    nested(detail, ['run', 'trace', 'multi_agent']),
    msg.multiAgentTrace,
    getRecord(msg.trace)?.multi_agent,
    getRecord(nested(detail, ['trace']))?.multi_agent,
    nested(detail, ['metadata', 'multi_agent']),
    nested(detail, ['summary', 'multi_agent']),
  ];

  for (const candidate of candidates) {
    if (!isRecord(candidate)) continue;
    const coordinator = getRecord(candidate.coordinator);
    const coordinatorRoleRuns = getRecordArray(coordinator?.role_runs);
    const roleRuns = getRecordArray(candidate.role_runs);
    const rolesUsed = getStringArray(candidate.roles_used);

    return {
      enabled: getBoolean(candidate.enabled) ?? true,
      run_id: getString(candidate.run_id),
      roles_used: rolesUsed.length
        ? rolesUsed
        : Array.from(
            new Set(
              [...roleRuns, ...coordinatorRoleRuns]
                .map((item) => getString(item.role))
                .filter((role): role is string => Boolean(role)),
            ),
          ),
      artifact_count:
        getNumber(candidate.artifact_count) ?? getRecordArray(candidate.artifacts).length,
      handoff_count:
        getNumber(candidate.handoff_count) ?? getRecordArray(candidate.handoffs).length,
      review_decision: getString(candidate.review_decision),
      coordinator,
      role_runs: roleRuns.map(normalizeRoleRun),
      artifacts: getRecordArray(candidate.artifacts).map((item) => ({
        id: getString(item.id) || '',
        role: getString(item.role) || '-',
        artifact_type: getString(item.artifact_type) || '-',
        title: getString(item.title) || '-',
        confidence: getNumber(item.confidence),
        content: getString(item.content),
        data: getRecord(item.data),
        source_refs: getRecordArray(item.source_refs),
        metadata: getRecord(item.metadata),
      })),
      handoffs: getRecordArray(candidate.handoffs).map((item) => ({
        id: getString(item.id) || '',
        from_role: getString(item.from_role) || '-',
        to_role: getString(item.to_role) || '-',
        summary: getString(item.summary) || '-',
        confidence: getNumber(item.confidence),
      })),
    };
  }

  return undefined;
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
  const [artifactPreview, setArtifactPreview] =
    useState<ArtifactPreview | null>(null);

  const traceId =
    msg.traceId ||
    msg.traceSummary?.trace_id ||
    (msg.assistantRunId ? `trace_${msg.assistantRunId}` : undefined);
  const multiAgentTrace = getMultiAgentTrace(msg, traceDetail);
  const hasTraceTarget = Boolean(
    traceId ||
      msg.traceSummary ||
      multiAgentTrace ||
      (msg.trace && Object.keys(msg.trace).length > 0),
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
    multi_agent: multiAgentTrace,
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
              key: 'multi-agent',
              label: multiAgentTrace
                ? `Multi-Agent (${multiAgentTrace.roles_used.length})`
                : 'Multi-Agent',
              children: renderMultiAgentTrace(multiAgentTrace, setArtifactPreview),
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

      <Modal
        title={
          artifactPreview ? (
            <div className={styles.artifactModalTitle}>
              <Text strong>{artifactPreview.title}</Text>
              {artifactPreview.role ? (
                <Tag color="geekblue">{artifactPreview.role}</Tag>
              ) : null}
              {artifactPreview.artifactType ? (
                <Tag>{artifactPreview.artifactType}</Tag>
              ) : null}
            </div>
          ) : null
        }
        open={Boolean(artifactPreview)}
        onCancel={() => setArtifactPreview(null)}
        footer={null}
        width="96vw"
        className={styles.artifactModal}
        destroyOnHidden
      >
        {artifactPreview ? (
          <div className={styles.artifactModalBody}>
            {renderMarkdown(artifactPreview.content)}
          </div>
        ) : null}
      </Modal>
    </>
  );
};

export default TraceDrawer;
