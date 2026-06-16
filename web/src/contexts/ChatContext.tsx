import {
  AssistantMode,
  AssistantRequestOptions,
  AssistantSourceItem,
  AssistantStreamChunk,
  AssistantToolCallEvent,
  ConversationItem,
  MessageItem,
  ModelsResponse,
  TraceSummary,
  MultiAgentTrace,
  createConversation as apiCreateConversation,
  deleteConversation as apiDeleteConversation,
  selectModel as apiSelectModel,
  getConversationMessages,
  getConversations,
  getHealth,
  getModels,
  sendAssistantMessageStream,
} from '@/services/api';
import { history } from '@umijs/max';
import { message } from 'antd';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

export type MessageRole = 'user' | 'ai';

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export type AssistantTraceEventStatus =
  | 'loading'
  | 'success'
  | 'error'
  | 'abort';

export interface AssistantTraceEventItem {
  id: string;
  event: string;
  title: string;
  description?: string;
  status: AssistantTraceEventStatus;
  payload?: Record<string, unknown>;
  timestamp: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  loading?: boolean;
  provider?: string;
  model?: string;
  latency_ms?: number;
  usage?: TokenUsage;
  assistantRunId?: string;
  agentRunId?: string;
  requestedMode?: AssistantMode;
  resolvedMode?: 'chat' | 'agent' | 'mcp';
  routeReason?: string;
  matchedKeywords?: string[];
  toolCalls?: AssistantToolCallEvent[];
  sources?: AssistantSourceItem[];
  trace?: Record<string, unknown>;
  multiAgentTrace?: MultiAgentTrace;
  traceId?: string;
  traceSummary?: TraceSummary;
  traceEvents?: AssistantTraceEventItem[];
  statusText?: string;
}

interface ChatContextType {
  messages: ChatMessage[];
  loading: boolean;
  health: { ok: boolean; message: string } | null;
  healthError: string | null;
  models: ModelsResponse | null;
  modelsError: string | null;
  modelSwitching: boolean;
  currentProvider: string;
  currentCloudProvider: string;
  currentModel: string;
  conversations: ConversationItem[];
  activeConversationId: string | null;
  activeConversation: ConversationItem | null;
  conversationsLoading: boolean;
  messagesLoading: boolean;
  conversationsError: string | null;
  sendMessage: (
    content: string,
    options?: { mode?: AssistantMode; assistantOptions?: AssistantRequestOptions },
  ) => Promise<void>;
  loadConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<ConversationItem | null>;
  deleteConversation: (conversationId: string) => Promise<void>;
  selectConversation: (conversationId: string) => Promise<void>;
  startNewConversation: () => void;
  loadModels: () => Promise<void>;
  handleSelectProvider: (provider: string) => Promise<void>;
  handleSelectCloudProvider: (cloudProvider: string) => Promise<void>;
  handleSelectModel: (
    model: string,
    provider?: string,
    cloudProvider?: string | null,
  ) => Promise<void>;
  clearMessages: () => void;
}

const ChatContext = createContext<ChatContextType | null>(null);

export const useChatContext = (): ChatContextType => {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
};

function getErrorMessage(err: any, fallback: string): string {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.message ||
    err?.message ||
    fallback
  );
}

function buildConversationTitle(content: string): string {
  const title = content.trim().replace(/\s+/g, ' ');

  if (title.length <= 24) return title;

  return `${title.slice(0, 24)}...`;
}

function toChatMessage(item: MessageItem): ChatMessage | null {
  if (item.role !== 'user' && item.role !== 'assistant') return null;

  const metadata = item.metadata || {};

  // 安全读取 tool_calls
  const rawToolCalls = metadata.tool_calls;
  const toolCalls: AssistantToolCallEvent[] | undefined = Array.isArray(
    rawToolCalls,
  )
    ? (rawToolCalls as AssistantToolCallEvent[])
    : undefined;

  // 安全读取 sources
  const rawSources = metadata.sources;
  const sources: AssistantSourceItem[] | undefined = Array.isArray(rawSources)
    ? (rawSources as AssistantSourceItem[])
    : undefined;

  // 安全读取 trace（必须是对象且非 null）
  const rawTrace = metadata.trace;
  const rawMultiAgent = metadata.multi_agent;
  const multiAgentTrace: MultiAgentTrace | undefined =
    rawMultiAgent !== null &&
    typeof rawMultiAgent === 'object' &&
    !Array.isArray(rawMultiAgent)
      ? (rawMultiAgent as MultiAgentTrace)
      : undefined;
  const trace: Record<string, unknown> | undefined =
    rawTrace !== null &&
    typeof rawTrace === 'object' &&
    !Array.isArray(rawTrace)
      ? (rawTrace as Record<string, unknown>)
      : multiAgentTrace
      ? { multi_agent: multiAgentTrace }
      : undefined;
  const assistantRunId =
    typeof metadata.assistant_run_id === 'string'
      ? metadata.assistant_run_id
      : undefined;
  const rawTraceSummary = metadata.trace_summary;
  const traceSummary: TraceSummary | undefined =
    rawTraceSummary !== null &&
    typeof rawTraceSummary === 'object' &&
    !Array.isArray(rawTraceSummary)
      ? (rawTraceSummary as TraceSummary)
      : undefined;
  const traceId =
    typeof metadata.trace_id === 'string'
      ? metadata.trace_id
      : typeof traceSummary?.trace_id === 'string'
      ? traceSummary.trace_id
      : typeof trace?.trace_id === 'string'
      ? trace.trace_id
      : assistantRunId
      ? `trace_${assistantRunId}`
      : undefined;

  // 从 trace.route_decision 恢复路由原因
  let routeReason: string | undefined;
  let matchedKeywords: string[] | undefined;
  if (trace) {
    const rd = trace.route_decision;
    if (rd !== null && typeof rd === 'object' && !Array.isArray(rd)) {
      const rdObj = rd as Record<string, unknown>;
      routeReason = typeof rdObj.reason === 'string' ? rdObj.reason : undefined;
      matchedKeywords = Array.isArray(rdObj.matched_keywords)
        ? (rdObj.matched_keywords as string[])
        : undefined;
    }
  }

  // agentRunId：兼容 run_id 和 agent_run_id
  const agentRunId: string | undefined =
    typeof metadata.agent_run_id === 'string'
      ? metadata.agent_run_id
      : typeof metadata.run_id === 'string'
      ? metadata.run_id
      : undefined;

  return {
    id: item.id,
    role: item.role === 'assistant' ? 'ai' : 'user',
    content: item.content,
    timestamp: new Date(item.created_at).getTime(),
    provider:
      typeof metadata.provider === 'string' ? metadata.provider : undefined,
    model: typeof metadata.model === 'string' ? metadata.model : undefined,
    latency_ms:
      typeof metadata.latency_ms === 'number' ? metadata.latency_ms : undefined,
    resolvedMode:
      metadata.mode === 'chat' ||
      metadata.mode === 'agent' ||
      metadata.mode === 'mcp'
        ? metadata.mode
        : undefined,
    assistantRunId,
    agentRunId,
    routeReason,
    matchedKeywords,
    toolCalls,
    sources,
    trace,
    multiAgentTrace,
    traceId,
    traceSummary,
  };
}

function getModeLabel(mode?: AssistantMode | 'chat' | 'agent' | 'mcp'): string {
  if (mode === 'agent') return 'Agent';
  if (mode === 'mcp') return 'MCP 外部工具';
  if (mode === 'chat') return '普通';
  return '自动';
}

function getTraceEventTitle(event: string): string {
  const labels: Record<string, string> = {
    assistant_start: 'Assistant 启动',
    route_decision: '路由决策',
    short_term_memory_loaded: '短期记忆加载',
    long_term_memory_retrieval_start: '长期记忆检索',
    long_term_memory_item: '长期记忆命中',
    long_term_memory_write: '长期记忆写入',
    working_memory_updated: '工作记忆更新',
    context_assembled: '上下文组装',
    tool_call_start: '工具调用',
    tool_call_end: '工具调用完成',
    assistant_end: 'Assistant 完成',
  };

  return labels[event] || event;
}

function toRecord(value: unknown): Record<string, unknown> | undefined {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  return undefined;
}

function buildTraceEvent(
  chunk: AssistantStreamChunk,
  fallbackStatus: AssistantTraceEventStatus = 'success',
): AssistantTraceEventItem {
  const payload = toRecord(chunk);
  const event = String(chunk.event || 'message');
  const toolName = typeof chunk.tool_name === 'string' ? chunk.tool_name : '';
  const step = typeof chunk.step === 'number' ? chunk.step : undefined;
  const id =
    event === 'tool_call_start' || event === 'tool_call_end'
      ? `tool:${step ?? 'unknown'}:${toolName || 'unknown'}`
      : `${event}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
  const description =
    event === 'route_decision'
      ? chunk.reason
      : event === 'tool_call_start' || event === 'tool_call_end'
      ? toolName || undefined
      : undefined;

  return {
    id,
    event,
    title:
      event === 'tool_call_start' || event === 'tool_call_end'
        ? toolName || getTraceEventTitle(event)
        : getTraceEventTitle(event),
    description,
    status:
      event === 'tool_call_start'
        ? 'loading'
        : chunk.success === false
        ? 'error'
        : fallbackStatus,
    payload,
    timestamp: Date.now(),
  };
}

function appendTraceEvent(
  message: ChatMessage,
  eventItem: AssistantTraceEventItem,
): ChatMessage {
  const traceEvents = message.traceEvents || [];
  const existingIndex = traceEvents.findIndex(
    (item) => item.id === eventItem.id,
  );

  if (existingIndex < 0) {
    return {
      ...message,
      traceEvents: [...traceEvents, eventItem],
    };
  }

  return {
    ...message,
    traceEvents: traceEvents.map((item, index) =>
      index === existingIndex
        ? {
            ...item,
            ...eventItem,
            timestamp: item.timestamp,
          }
        : item,
    ),
  };
}

interface ChatProviderProps {
  children: React.ReactNode;
  routeConversationId?: string;
}

export const ChatProvider: React.FC<ChatProviderProps> = ({
  children,
  routeConversationId,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<{ ok: boolean; message: string } | null>(
    null,
  );
  const [healthError, setHealthError] = useState<string | null>(null);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelSwitching, setModelSwitching] = useState(false);
  const [currentProvider, setCurrentProvider] = useState<string>('');
  const [currentCloudProvider, setCurrentCloudProvider] =
    useState<string>('deepseek');
  const [currentModel, setCurrentModel] = useState<string>('');
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [conversationsError, setConversationsError] = useState<string | null>(
    null,
  );
  const conversationsLoadedRef = useRef(false);

  const activeConversation =
    conversations.find((item) => item.id === activeConversationId) || null;

  const navigateToConversation = useCallback((conversationId: string) => {
    const nextPath = `/conversations/${conversationId}`;
    if (history.location.pathname !== nextPath) {
      history.push(nextPath);
    }
  }, []);

  const navigateToHome = useCallback(() => {
    if (history.location.pathname !== '/') {
      history.push('/');
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const data = await getModels();
      setModels(data);
      setCurrentProvider(data.current_provider);
      setCurrentCloudProvider(data.current_cloud_provider || 'deepseek');
      setCurrentModel(data.current_model);
      setModelsError(null);
    } catch {
      setModelsError('模型列表加载失败');
    }
  }, []);

  const getProviderModels = useCallback(
    (provider: string) =>
      models?.providers?.find((item) => item.provider === provider),
    [models],
  );

  const getCloudProviderModels = useCallback(
    (provider: string) =>
      models?.cloud_providers?.find((item) => item.provider === provider),
    [models],
  );

  const loadConversations = useCallback(async () => {
    const shouldShowLoading = !conversationsLoadedRef.current;
    if (shouldShowLoading) {
      setConversationsLoading(true);
    }

    try {
      const data = await getConversations();
      setConversations(data.items);
      setConversationsError(null);
    } catch (err: any) {
      setConversationsError(getErrorMessage(err, '会话列表加载失败'));
    } finally {
      conversationsLoadedRef.current = true;
      if (shouldShowLoading) {
        setConversationsLoading(false);
      }
    }
  }, []);

  const selectConversation = useCallback(
    async (conversationId: string) => {
      setActiveConversationId(conversationId);
      setMessages([]);
      setMessagesLoading(true);
      navigateToConversation(conversationId);

      try {
        const data = await getConversationMessages(conversationId);
        setMessages(
          data.items
            .map(toChatMessage)
            .filter((item): item is ChatMessage => Boolean(item)),
        );
        setConversationsError(null);
      } catch (err: any) {
        setConversationsError(getErrorMessage(err, '会话消息加载失败'));
      } finally {
        setMessagesLoading(false);
      }
    },
    [navigateToConversation],
  );

  useEffect(() => {
    if (routeConversationId) {
      if (routeConversationId !== activeConversationId) {
        selectConversation(routeConversationId);
      }
      return;
    }

    if (activeConversationId) {
      setActiveConversationId(null);
      setMessages([]);
    }
  }, [activeConversationId, routeConversationId, selectConversation]);

  useEffect(() => {
    (async () => {
      try {
        const h = await getHealth();
        setHealth(h);
        setHealthError(null);
      } catch {
        setHealthError('后端服务不可用，请确认 FastAPI 服务已启动');
        setHealth(null);
      }
    })();

    loadModels();
    loadConversations();
  }, [loadConversations, loadModels]);

  const createConversation = useCallback(
    async (title = '新会话'): Promise<ConversationItem | null> => {
      try {
        const conversation = await apiCreateConversation({
          title,
          provider: currentProvider || null,
          model: currentModel || null,
        });

        setConversations((prev) => [
          conversation,
          ...prev.filter((item) => item.id !== conversation.id),
        ]);
        setActiveConversationId(conversation.id);
        setMessages([]);
        setConversationsError(null);
        navigateToConversation(conversation.id);

        return conversation;
      } catch (err: any) {
        message.error(getErrorMessage(err, '创建会话失败'));
        return null;
      }
    },
    [currentModel, currentProvider, navigateToConversation],
  );

  const deleteConversation = useCallback(
    async (conversationId: string) => {
      try {
        await apiDeleteConversation(conversationId);

        setConversations((prev) =>
          prev.filter((item) => item.id !== conversationId),
        );

        if (activeConversationId === conversationId) {
          setActiveConversationId(null);
          setMessages([]);
          navigateToHome();
        }

        message.success('会话已删除');
      } catch (err: any) {
        message.error(getErrorMessage(err, '删除会话失败'));
      }
    },
    [activeConversationId, navigateToHome],
  );

  const handleSelectModel = useCallback(
    async (model: string, provider?: string, cloudProvider?: string | null) => {
      const nextProvider = provider || currentProvider;
      const nextCloudProvider =
        nextProvider === 'cloud'
          ? cloudProvider || currentCloudProvider || 'deepseek'
          : null;

      try {
        setModelSwitching(true);
        const res = await apiSelectModel(
          model,
          nextProvider,
          nextCloudProvider,
        );
        if (res.success) {
          const selectedProvider = res.selected_provider || nextProvider;
          const selectedCloudProvider =
            res.selected_cloud_provider || nextCloudProvider;

          setCurrentProvider(selectedProvider);
          if (selectedCloudProvider) {
            setCurrentCloudProvider(selectedCloudProvider);
          }
          setCurrentModel(res.selected_model);
          setModels((prev) =>
            prev
              ? {
                  ...prev,
                  current_provider: selectedProvider,
                  current_cloud_provider: selectedCloudProvider,
                  current_model: res.selected_model,
                  available_models:
                    selectedProvider === 'cloud'
                      ? prev.cloud_providers?.find(
                          (item) => item.provider === selectedCloudProvider,
                        )?.available_models || prev.available_models
                      : prev.providers?.find(
                          (item) => item.provider === selectedProvider,
                        )?.available_models || prev.available_models,
                  providers: prev.providers?.map((item) =>
                    item.provider === selectedProvider
                      ? { ...item, current_model: res.selected_model }
                      : item,
                  ),
                  cloud_providers: prev.cloud_providers?.map((item) =>
                    selectedProvider === 'cloud' &&
                    item.provider === selectedCloudProvider
                      ? { ...item, current_model: res.selected_model }
                      : item,
                  ),
                }
              : prev,
          );
          message.success(
            res.message ||
              `已切换模型：${res.selected_provider}/${res.selected_model}`,
          );
        } else {
          message.error(res.message || '模型切换失败');
        }
      } catch (err: any) {
        message.error(getErrorMessage(err, '模型切换失败'));
      } finally {
        setModelSwitching(false);
      }
    },
    [currentCloudProvider, currentProvider],
  );

  const handleSelectProvider = useCallback(
    async (provider: string) => {
      const providerModels = getProviderModels(provider);
      const nextCloudProvider =
        provider === 'cloud' ? currentCloudProvider || 'deepseek' : null;
      const nextModel =
        providerModels?.current_model || providerModels?.available_models[0];

      setCurrentProvider(provider);

      if (!nextModel) {
        setCurrentModel('');
        message.error('该 Provider 暂无可用模型');
        return;
      }

      await handleSelectModel(nextModel, provider, nextCloudProvider);
    },
    [currentCloudProvider, getProviderModels, handleSelectModel],
  );

  const handleSelectCloudProvider = useCallback(
    async (cloudProvider: string) => {
      const providerModels = getCloudProviderModels(cloudProvider);
      const nextModel =
        providerModels?.current_model || providerModels?.available_models[0];

      setCurrentProvider('cloud');
      setCurrentCloudProvider(cloudProvider);

      if (!nextModel) {
        setCurrentModel('');
        message.error('该 Cloud 供应商暂无可用模型');
        return;
      }

      await handleSelectModel(nextModel, 'cloud', cloudProvider);
    },
    [getCloudProviderModels, handleSelectModel],
  );

  const sendMessage = useCallback(
    async (
      content: string,
      options?: {
        mode?: AssistantMode;
        assistantOptions?: AssistantRequestOptions;
      },
    ) => {
      const trimmedContent = content.trim();
      const requestedMode = options?.mode || 'auto';
      const requestOptions = options?.assistantOptions;
      const streamOptions: AssistantRequestOptions | undefined =
        requestOptions ||
        (requestedMode === 'mcp'
          ? {
              enable_mcp_tools: true,
              enable_tools: true,
              enable_working_memory: true,
              enable_long_term_memory: true,
            }
          : undefined);

      if (!trimmedContent || loading) return;

      let conversationId = activeConversationId;

      if (!conversationId) {
        const conversation = await createConversation(
          buildConversationTitle(trimmedContent),
        );

        if (!conversation) return;

        conversationId = conversation.id;
      }

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: trimmedContent,
        timestamp: Date.now(),
      };
      const aiMsgId = `ai-${Date.now() + 1}`;
      const aiMsgPlaceholder: ChatMessage = {
        id: aiMsgId,
        role: 'ai',
        content: '',
        timestamp: Date.now() + 1,
        loading: true,
        requestedMode,
        statusText: `${getModeLabel(requestedMode)}模式处理中`,
      };

      setMessages((prev) => [...prev, userMsg, aiMsgPlaceholder]);
      setLoading(true);

      try {
        await sendAssistantMessageStream(
          conversationId,
          {
            message: trimmedContent,
            mode: requestedMode,
            provider: currentProvider || null,
            model: currentModel || null,
            options: streamOptions,
          },
          (chunk: AssistantStreamChunk) => {
            if (chunk.event === 'assistant_start') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? appendTraceEvent(
                        {
                          ...m,
                          assistantRunId: chunk.assistant_run_id || m.id,
                          requestedMode: chunk.requested_mode || requestedMode,
                          resolvedMode: chunk.mode,
                          statusText: chunk.mode
                            ? `${getModeLabel(chunk.mode)}模式处理中`
                            : m.statusText,
                        },
                        buildTraceEvent(chunk),
                      )
                    : m,
                ),
              );
              return;
            }

            if (chunk.event === 'route_decision') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? appendTraceEvent(
                        {
                          ...m,
                          resolvedMode: chunk.mode,
                          routeReason: chunk.reason,
                          matchedKeywords: chunk.matched_keywords || [],
                          statusText: `${getModeLabel(chunk.mode)}模式处理中`,
                        },
                        buildTraceEvent(chunk),
                      )
                    : m,
                ),
              );
              return;
            }

            if (chunk.event === 'tool_call_start') {
              const toolCall: AssistantToolCallEvent = {
                tool_name: chunk.tool_name,
                arguments: chunk.arguments,
                reason: chunk.reason,
                step: chunk.step,
                source: chunk.source,
                role: chunk.role,
                multi_agent_run_id: chunk.multi_agent_run_id,
                metadata: chunk.metadata,
              };

              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? appendTraceEvent(
                        {
                          ...m,
                          toolCalls: [...(m.toolCalls || []), toolCall],
                          statusText: chunk.tool_name
                            ? `调用工具：${chunk.tool_name}`
                            : '调用工具中',
                        },
                        buildTraceEvent(chunk),
                      )
                    : m,
                ),
              );
              return;
            }

            if (chunk.event === 'tool_call_end') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? appendTraceEvent(
                        {
                          ...m,
                          toolCalls: (m.toolCalls || []).map((item) =>
                            item.tool_name === chunk.tool_name &&
                            item.step === chunk.step
                              ? {
                                  ...item,
                                  success: chunk.success,
                                  latency_ms: chunk.latency_ms,
                                  error_code: chunk.error_code,
                                  error_message: chunk.error_message,
                                  source: chunk.source || item.source,
                                  role: chunk.role || item.role,
                                  multi_agent_run_id:
                                    chunk.multi_agent_run_id ||
                                    item.multi_agent_run_id,
                                  metadata: chunk.metadata || item.metadata,
                                }
                              : item,
                          ),
                          statusText: '整理回答中',
                        },
                        buildTraceEvent(chunk),
                      )
                    : m,
                ),
              );
              return;
            }

            if (chunk.event === 'error' || chunk.error) {
              throw new Error(
                chunk.error?.detail ||
                  chunk.error?.message ||
                  '流式会话消息失败',
              );
            }

            if (chunk.event === 'delta') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? {
                        ...m,
                        content: `${m.content}${chunk.delta || ''}`,
                        loading: true,
                        provider:
                          currentProvider ||
                          activeConversation?.provider ||
                          'ollama',
                        model: currentModel || activeConversation?.model,
                        statusText: m.statusText,
                      }
                    : m,
                ),
              );
              return;
            }

            if (chunk.event === 'assistant_end') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? appendTraceEvent(
                        {
                          ...m,
                          id: chunk.assistant_message_id || m.id,
                          loading: false,
                          assistantRunId: chunk.assistant_run_id,
                          agentRunId: chunk.agent_run_id,
                          resolvedMode: chunk.mode || m.resolvedMode,
                          latency_ms: chunk.latency_ms,
                          toolCalls: chunk.tool_calls || m.toolCalls,
                          sources: Array.isArray(chunk.sources)
                            ? chunk.sources
                            : m.sources,
                          multiAgentTrace:
                            chunk.multi_agent ||
                            (toRecord(chunk.trace)?.multi_agent as
                              | MultiAgentTrace
                              | undefined) ||
                            m.multiAgentTrace,
                          trace:
                            chunk.trace !== null &&
                            typeof chunk.trace === 'object' &&
                            !Array.isArray(chunk.trace)
                              ? chunk.trace
                              : m.trace,
                          traceId:
                            chunk.trace_id ||
                            m.traceId ||
                            (chunk.assistant_run_id
                              ? `trace_${chunk.assistant_run_id}`
                              : undefined),
                          traceSummary:
                            chunk.trace_summary &&
                            typeof chunk.trace_summary === 'object'
                              ? chunk.trace_summary
                              : m.traceSummary,
                          provider:
                            chunk.provider ||
                            currentProvider ||
                            activeConversation?.provider,
                          model:
                            chunk.model ||
                            currentModel ||
                            activeConversation?.model,
                          statusText: undefined,
                        },
                        buildTraceEvent(chunk),
                      )
                    : m,
                ),
              );
              return;
            }

            if (
              chunk.event !== 'delta' &&
              chunk.event !== 'done' &&
              chunk.event !== 'message'
            ) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? appendTraceEvent(m, buildTraceEvent(chunk))
                    : m,
                ),
              );
            }
          },
        );

        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsgId
              ? {
                  ...m,
                  loading: false,
                }
              : m,
          ),
        );

        await loadConversations();
        const latestMessages = await getConversationMessages(conversationId);
        setMessages(
          latestMessages.items
            .map(toChatMessage)
            .filter((item): item is ChatMessage => Boolean(item)),
        );
      } catch (err: any) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsgId
              ? {
                  ...m,
                  content: getErrorMessage(
                    err,
                    '模型调用失败，请检查后端或模型服务',
                  ),
                  loading: false,
                }
              : m,
          ),
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeConversation,
      activeConversationId,
      createConversation,
      currentModel,
      currentProvider,
      loadConversations,
      loading,
    ],
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const startNewConversation = useCallback(() => {
    setActiveConversationId(null);
    setMessages([]);
    navigateToHome();
  }, [navigateToHome]);

  return (
    <ChatContext.Provider
      value={{
        messages,
        loading,
        health,
        healthError,
        models,
        modelsError,
        modelSwitching,
        currentProvider,
        currentCloudProvider,
        currentModel,
        conversations,
        activeConversationId,
        activeConversation,
        conversationsLoading,
        messagesLoading,
        conversationsError,
        sendMessage,
        loadConversations,
        createConversation,
        deleteConversation,
        selectConversation,
        startNewConversation,
        loadModels,
        handleSelectProvider,
        handleSelectCloudProvider,
        handleSelectModel,
        clearMessages,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};
