import { ChatMessage } from '@/contexts/ChatContext';
import JsonViewer from '@/components/JsonViewer';
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
  role: string;
  x: number;
  y: number;
  run?: MultiAgentRoleRun;
}

interface RoleGraphEdge {
  id: string;
  from: string;
  to: string;
  summary: string;
  confidence?: number;
}

interface ArtifactPreview {
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

function getRoleOrder(trace: MultiAgentTrace): string[] {
  const orderedRoles: string[] = [];
  const seen = new Set<string>();
  const addRole = (role?: string) => {
    if (!role || seen.has(role)) return;
    seen.add(role);
    orderedRoles.push(role);
  };

  trace.roles_used.forEach(addRole);
  trace.role_runs?.forEach((run) => addRole(run.role));
  trace.handoffs.forEach((handoff) => {
    addRole(handoff.from_role);
    addRole(handoff.to_role);
  });

  const incomingCount = new Map(orderedRoles.map((role) => [role, 0]));
  const outgoing = new Map<string, string[]>();

  trace.handoffs.forEach((handoff) => {
    const from = handoff.from_role;
    const to = handoff.to_role;
    if (!from || !to || from === '-' || to === '-' || from === to) return;

    incomingCount.set(to, (incomingCount.get(to) || 0) + 1);
    outgoing.set(from, [...(outgoing.get(from) || []), to]);
  });

  const queue = orderedRoles.filter((role) => (incomingCount.get(role) || 0) === 0);
  const sorted: string[] = [];

  while (queue.length > 0) {
    const role = queue.shift();
    if (!role || sorted.includes(role)) continue;

    sorted.push(role);
    for (const nextRole of outgoing.get(role) || []) {
      incomingCount.set(nextRole, (incomingCount.get(nextRole) || 0) - 1);
      if ((incomingCount.get(nextRole) || 0) === 0) {
        queue.push(nextRole);
      }
    }
  }

  orderedRoles.forEach((role) => {
    if (!sorted.includes(role)) sorted.push(role);
  });

  return sorted;
}

function buildRoleGraph(trace: MultiAgentTrace): {
  nodes: RoleGraphNode[];
  edges: RoleGraphEdge[];
  width: number;
  height: number;
} {
  const roleRunsByRole = new Map(
    (trace.role_runs || []).map((run) => [run.role, run]),
  );
  const roles = getRoleOrder(trace);
  const nodeWidth = 150;
  const gap = 110;
  const marginX = 42;
  const width = Math.max(760, marginX * 2 + roles.length * nodeWidth + Math.max(roles.length - 1, 0) * gap);
  const height = 220;
  const centerY = 96;

  const nodes = roles.map((role, index) => ({
    role,
    x: marginX + index * (nodeWidth + gap),
    y: centerY,
    run: roleRunsByRole.get(role),
  }));
  const edges = trace.handoffs
    .filter(
      (handoff) =>
        handoff.from_role &&
        handoff.to_role &&
        handoff.from_role !== '-' &&
        handoff.to_role !== '-',
    )
    .map((handoff, index) => ({
      id: handoff.id || `${handoff.from_role}-${handoff.to_role}-${index}`,
      from: handoff.from_role,
      to: handoff.to_role,
      summary: handoff.summary,
      confidence: handoff.confidence,
    }));

  return { nodes, edges, width, height };
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

const MultiAgentRoleGraph: React.FC<{
  trace: MultiAgentTrace;
  onOpenArtifact: (artifact: ArtifactPreview) => void;
}> = ({ trace, onOpenArtifact }) => {
  const graph = useMemo(() => buildRoleGraph(trace), [trace]);
  const [selectedRole, setSelectedRole] = useState<string | undefined>(
    graph.nodes[0]?.role,
  );
  const nodeMap = useMemo(
    () => new Map(graph.nodes.map((node) => [node.role, node])),
    [graph.nodes],
  );
  const effectiveSelectedRole =
    graph.nodes.find((node) => node.role === selectedRole)?.role ||
    graph.nodes[0]?.role;
  const selectedNode = effectiveSelectedRole
    ? nodeMap.get(effectiveSelectedRole)
    : undefined;
  const selectedIncoming = trace.handoffs.filter(
    (handoff) => handoff.to_role === effectiveSelectedRole,
  );
  const selectedOutgoing = trace.handoffs.filter(
    (handoff) => handoff.from_role === effectiveSelectedRole,
  );

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
      <div className={styles.roleGraphViewport}>
        <svg
          className={styles.roleGraphSvg}
          viewBox={`0 0 ${graph.width} ${graph.height}`}
          role="img"
          aria-label="Multi-Agent role execution graph"
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

            const startX = fromNode.x + 150;
            const startY = fromNode.y + 33;
            const endX = toNode.x;
            const endY = toNode.y + 33;
            const controlOffset = Math.max(Math.abs(endX - startX) * 0.42, 48);
            const path = `M ${startX} ${startY} C ${startX + controlOffset} ${startY}, ${endX - controlOffset} ${endY}, ${endX} ${endY}`;
            const labelX = (startX + endX) / 2;
            const labelY = (startY + endY) / 2 - 10;

            return (
              <g key={edge.id}>
                <title>{edge.summary}</title>
                <path
                  d={path}
                  className={styles.roleGraphEdge}
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
            const isSelected = node.role === effectiveSelectedRole;
            const status = node.run?.status || 'pending';
            const artifactTitle = node.run?.artifact?.title || '';

            return (
              <g
                key={node.role}
                className={styles.roleGraphNode}
                transform={`translate(${node.x}, ${node.y})`}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedRole(node.role)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    setSelectedRole(node.role);
                  }
                }}
              >
                <title>
                  {artifactTitle
                    ? `${node.role}: ${artifactTitle}`
                    : `${node.role}: ${status}`}
                </title>
                <rect
                  width="150"
                  height="66"
                  rx="8"
                  className={
                    isSelected
                      ? styles.roleGraphNodeRectSelected
                      : styles.roleGraphNodeRect
                  }
                />
                <text x="16" y="24" className={styles.roleGraphNodeTitle}>
                  {compactText(node.role, 16)}
                </text>
                <text x="16" y="43" className={styles.roleGraphNodeStatus}>
                  {status}
                </text>
                <text x="16" y="58" className={styles.roleGraphNodeMeta}>
                  {formatLatency(node.run?.latency_ms)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className={styles.roleGraphDetail}>
        {selectedNode?.run ? (
          renderRoleRun(selectedNode.run, onOpenArtifact)
        ) : (
          <>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="Role">
                {effectiveSelectedRole || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Status">pending</Descriptions.Item>
            </Descriptions>
            {renderHandoffList('Incoming Handoffs', selectedIncoming)}
            {renderHandoffList('Outgoing Handoffs', selectedOutgoing)}
          </>
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
      </Descriptions>

      <div className={styles.section}>
        <Text strong className={styles.sectionTitle}>
          Role Execution Flow
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
  if (msg.multiAgentTrace) return msg.multiAgentTrace;

  const candidates = [
    getRecord(msg.trace)?.multi_agent,
    getRecord(nested(detail, ['trace']))?.multi_agent,
    nested(detail, ['metadata', 'multi_agent']),
    nested(detail, ['summary', 'multi_agent']),
  ];

  for (const candidate of candidates) {
    if (!isRecord(candidate)) continue;

    return {
      enabled: getBoolean(candidate.enabled) ?? true,
      run_id: getString(candidate.run_id),
      roles_used: getStringArray(candidate.roles_used),
      artifact_count:
        getNumber(candidate.artifact_count) ?? getRecordArray(candidate.artifacts).length,
      handoff_count:
        getNumber(candidate.handoff_count) ?? getRecordArray(candidate.handoffs).length,
      review_decision: getString(candidate.review_decision),
      role_runs: getRecordArray(candidate.role_runs).map(normalizeRoleRun),
      artifacts: getRecordArray(candidate.artifacts).map((item) => ({
        id: getString(item.id) || '',
        role: getString(item.role) || '-',
        artifact_type: getString(item.artifact_type) || '-',
        title: getString(item.title) || '-',
        confidence: getNumber(item.confidence),
        content: getString(item.content),
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
