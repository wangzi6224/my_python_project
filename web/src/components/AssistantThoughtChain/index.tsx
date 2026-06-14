import type {
  AssistantTraceEventItem,
  AssistantTraceEventStatus,
  ChatMessage,
} from '@/contexts/ChatContext';
import JsonViewer from '@/components/JsonViewer';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import type { ThoughtChainItemType } from '@ant-design/x';
import { ThoughtChain } from '@ant-design/x';
import { Tag, Typography } from 'antd';
import React, { useMemo } from 'react';
import styles from './index.module.less';

const { Text } = Typography;

interface AssistantThoughtChainProps {
  message: ChatMessage;
}

function toRecord(value: unknown): Record<string, unknown> | undefined {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  return undefined;
}

function getStatusIcon(status: AssistantTraceEventStatus): React.ReactNode {
  if (status === 'loading') return <LoadingOutlined />;
  if (status === 'error') return <CloseCircleOutlined />;
  return <CheckCircleOutlined />;
}

function eventFromTrace(
  id: string,
  event: string,
  title: string,
  payload?: Record<string, unknown>,
  description?: string,
): AssistantTraceEventItem {
  return {
    id,
    event,
    title,
    description,
    status: 'success',
    payload,
    timestamp: 0,
  };
}

function buildFallbackEvents(message: ChatMessage): AssistantTraceEventItem[] {
  const events: AssistantTraceEventItem[] = [];

  if (message.routeReason || message.resolvedMode) {
    events.push(
      eventFromTrace(
        'route_decision',
        'route_decision',
        '路由决策',
        {
          mode: message.resolvedMode,
          reason: message.routeReason,
          matched_keywords: message.matchedKeywords,
        },
        message.routeReason,
      ),
    );
  }

  const context = toRecord(message.trace?.context);
  if (context) {
    events.push(
      eventFromTrace(
        'context_assembled',
        'context_assembled',
        '上下文组装',
        context,
      ),
    );
  }

  const memory = toRecord(message.trace?.memory);
  if (memory) {
    events.push(eventFromTrace('memory', 'memory', '记忆处理', memory));
  }

  return events;
}

function isToolTraceEvent(event: AssistantTraceEventItem): boolean {
  return event.event === 'tool_call' || event.event.startsWith('tool_call_');
}

function renderPayload(payload?: Record<string, unknown>) {
  if (!payload || Object.keys(payload).length === 0) return undefined;

  return <JsonViewer value={payload} maxHeight={260} />;
}

const AssistantThoughtChain: React.FC<AssistantThoughtChainProps> = ({
  message,
}) => {
  const events = useMemo(() => {
    const baseEvents = (
      message.traceEvents && message.traceEvents.length > 0
        ? message.traceEvents
        : buildFallbackEvents(message)
    ).filter((event) => !isToolTraceEvent(event));

    if (
      message.loading &&
      !baseEvents.some((event) => event.status === 'loading')
    ) {
      return [
        ...baseEvents,
        {
          id: 'assistant-running',
          event: 'running',
          title: message.statusText || '处理中',
          description: '任务仍在执行',
          status: 'loading',
          timestamp: Date.now(),
        } satisfies AssistantTraceEventItem,
      ];
    }

    return baseEvents;
  }, [message]);

  if (events.length === 0) return null;

  const items: ThoughtChainItemType[] = events.map((event) => ({
    key: event.id,
    title: (
      <div className={styles.title}>
        <Text strong className={styles.titleText}>
          {event.title}
        </Text>
        <Tag className={styles.eventTag}>{event.event}</Tag>
      </div>
    ),
    description: event.description,
    status: event.status,
    icon: getStatusIcon(event.status),
    blink: event.status === 'loading',
    collapsible: Boolean(event.payload),
    content: renderPayload(event.payload),
  }));

  return (
    <div className={styles.container}>
      <Text type="secondary" className={styles.heading}>
        思维链
      </Text>
      <ThoughtChain
        items={items}
        defaultExpandedKeys={[]}
        classNames={{ item: styles.chainItem }}
        className={styles.chain}
      />
    </div>
  );
};

export default AssistantThoughtChain;
