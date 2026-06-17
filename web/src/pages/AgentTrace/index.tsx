import {
  ConversationItem,
  TraceListItem,
  getConversations,
  listTraces,
} from '@/services';
import {
  ApiOutlined,
  ApartmentOutlined,
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  MessageOutlined,
  ReloadOutlined,
  SearchOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { history, useLocation } from '@umijs/max';
import { Alert, Button, Card, Empty, Input, Select, Space, Spin, Tag, Typography } from 'antd';
import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import styles from './index.module.less';

const { Paragraph, Text, Title } = Typography;

const errorText = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === 'string' ? detail : error.message;
  }
  return error instanceof Error ? error.message : '请求失败，请稍后重试';
};

const formatTime = (value?: string) =>
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-';
const formatLatency = (value?: number | null) =>
  typeof value === 'number'
    ? value >= 1000
      ? `${(value / 1000).toFixed(2)}s`
      : `${value}ms`
    : '-';
const statusColor = (status: string) =>
  status === 'completed' || status === 'success'
    ? 'success'
    : status === 'running'
    ? 'processing'
    : status === 'failed' || status === 'error'
    ? 'error'
    : 'default';

const AgentTracePage: React.FC = () => {
  const location = useLocation();
  const queryId = useMemo(
    () => new URLSearchParams(location.search).get('conversation_id') || '',
    [location.search],
  );
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [conversationId, setConversationId] = useState('');
  const [traces, setTraces] = useState<TraceListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [keyword, setKeyword] = useState('');
  const [type, setType] = useState('all');

  const loadTraces = async (id: string) => {
    if (!id) return setTraces([]);
    setLoading(true);
    setError('');
    try {
      setTraces((await listTraces(id)).items || []);
    } catch (requestError) {
      setError(errorText(requestError));
      setTraces([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const items = (await getConversations()).items || [];
        setConversations(items);
        const next = items.some((item) => item.id === queryId)
          ? queryId
          : items[0]?.id || '';
        setConversationId(next);
        if (next) await loadTraces(next);
      } catch (requestError) {
        setError(errorText(requestError));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const filtered = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    return traces.filter((item) => {
      const matchesType =
        type === 'all' || (type === 'multi' ? item.multi_agent.enabled : !item.multi_agent.enabled);
      const haystack = [item.input, item.trace_id, item.model, item.provider, item.status]
        .join(' ')
        .toLowerCase();
      return matchesType && (!q || haystack.includes(q));
    });
  }, [keyword, traces, type]);

  const stats = useMemo(
    () => ({
      total: traces.length,
      multi: traces.filter((item) => item.multi_agent.enabled).length,
      rounds: traces.reduce((sum, item) => sum + item.multi_agent.round_count, 0),
      errors: traces.filter((item) => ['failed', 'error'].includes(item.status)).length,
    }),
    [traces],
  );

  const changeConversation = (id: string) => {
    setConversationId(id);
    history.replace(`/traces?conversation_id=${encodeURIComponent(id)}`);
    void loadTraces(id);
  };

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <div>
          <div className={styles.eyebrow}><ApartmentOutlined /> MULTI-AGENT OBSERVABILITY</div>
          <Title level={2} className={styles.title}>Trace Control Center</Title>
          <Paragraph className={styles.subtitle}>从 Assistant 路由到 Coordinator 动态轮次，查看真实 Agent 决策、角色执行与产物流转。</Paragraph>
        </div>
        <Space wrap>
          <Button icon={<MessageOutlined />} onClick={() => history.push('/')}>返回聊天</Button>
          <Button icon={<FileTextOutlined />} onClick={() => history.push('/docs')}>文档管理</Button>
        </Space>
      </header>

      <section className={styles.metrics}>
        <div className={styles.metric}><ApiOutlined /><span>Trace 总数<strong>{stats.total}</strong></span></div>
        <div className={styles.metric}><ApartmentOutlined /><span>Multi-Agent<strong>{stats.multi}</strong></span></div>
        <div className={styles.metric}><ClockCircleOutlined /><span>Coordinator 轮次<strong>{stats.rounds}</strong></span></div>
        <div className={`${styles.metric} ${stats.errors ? styles.metricDanger : ''}`}><WarningOutlined /><span>异常运行<strong>{stats.errors}</strong></span></div>
      </section>

      <Card className={styles.toolbarCard}>
        <div className={styles.toolbar}>
          <Select
            className={styles.conversationSelect}
            value={conversationId || undefined}
            placeholder="选择会话"
            showSearch
            optionFilterProp="label"
            options={conversations.map((item) => ({ value: item.id, label: item.title || item.id }))}
            onChange={changeConversation}
          />
          <Input className={styles.searchInput} allowClear prefix={<SearchOutlined />} placeholder="搜索问题、Trace ID、模型" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          <Select className={styles.typeSelect} value={type} onChange={setType} options={[{ value: 'all', label: '全部流程' }, { value: 'multi', label: 'Multi-Agent' }, { value: 'single', label: 'Single Agent' }]} />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadTraces(conversationId)}>刷新</Button>
        </div>
      </Card>

      {error ? <Alert className={styles.alert} type="error" showIcon message={error} /> : null}
      {loading && !traces.length ? <div className={styles.loading}><Spin size="large" /></div> : null}
      {!loading && !filtered.length ? <Card className={styles.emptyCard}><Empty description={conversationId ? '当前会话暂无 Trace' : '请先选择会话'} /></Card> : null}

      <section className={styles.runList}>
        {filtered.map((item) => (
          <button
            type="button"
            className={styles.runCard}
            key={item.trace_id}
            onClick={() => history.push(`/traces/${encodeURIComponent(item.trace_id)}?conversation_id=${encodeURIComponent(conversationId)}`)}
          >
            <div className={styles.runStripe} />
            <div className={styles.runMain}>
              <div className={styles.runTop}>
                <Space wrap>
                  <Tag color={item.multi_agent.enabled ? 'geekblue' : 'default'}>{item.multi_agent.enabled ? 'MULTI AGENT' : item.mode?.toUpperCase() || 'ASSISTANT'}</Tag>
                  <Tag color={statusColor(item.status)} icon={item.status === 'completed' ? <CheckCircleOutlined /> : undefined}>{item.status}</Tag>
                  {item.multi_agent.review_decision ? <Tag color={item.multi_agent.review_decision === 'pass' ? 'success' : 'warning'}>review: {item.multi_agent.review_decision}</Tag> : null}
                </Space>
                <Text type="secondary">{formatTime(item.created_at)}</Text>
              </div>
              <Text className={styles.runQuestion}>{item.input || '无输入内容'}</Text>
              <div className={styles.runMeta}>
                <span><b>{item.multi_agent.round_count}</b> 轮决策</span>
                <span><b>{item.multi_agent.roles_used.length}</b> 个角色</span>
                <span><b>{item.multi_agent.artifact_count}</b> 个产物</span>
                <span><b>{item.summary.tool_call_count || 0}</b> 次工具</span>
                <span><b>{formatLatency(item.latency_ms)}</b> 总耗时</span>
              </div>
              <div className={styles.runFooter}>
                <Text code ellipsis>{item.trace_id}</Text>
                <span>{item.model || '-'} · {item.provider || '-'}</span>
              </div>
            </div>
            <ArrowRightOutlined className={styles.openIcon} />
          </button>
        ))}
      </section>
    </div>
  );
};

export default AgentTracePage;
