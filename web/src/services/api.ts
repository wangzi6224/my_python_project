import axios from 'axios';

export const API_BASE_URL =
  process.env.UMI_APP_API_BASE_URL || 'http://127.0.0.1:8000';

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

// ---- 类型定义 ----

export interface HealthResponse {
  ok: boolean;
  message: string;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ChatRequest {
  message: string;
  provider?: string | null;
  model?: string | null;
}

export interface ChatResponse {
  answer: string;
  provider: string;
  model: string;
  latency_ms: number;
  usage: TokenUsage;
}

export interface ChatStreamChunk {
  delta?: string;
  done?: boolean;
  model?: string;
  latency_ms?: number;
  error?: {
    code?: string;
    message?: string;
    detail?: string;
  };
}

export interface ConversationItem {
  id: string;
  title: string;
  summary: string | null;
  model: string;
  provider: string;
  status: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationItem[];
}

export type ConversationDetailResponse = ConversationItem;

export type MessageRole = 'system' | 'user' | 'assistant' | 'tool';

export interface MessageItem {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MessageListResponse {
  items: MessageItem[];
}

export interface ConversationCreateRequest {
  title: string;
  provider?: string | null;
  model?: string | null;
}

export interface SendMessageRequest {
  content: string;
  provider?: string | null;
  model?: string | null;
}

export type AssistantMode = 'auto' | 'chat' | 'agent' | 'mcp';

export interface AssistantStreamRequest {
  message: string;
  mode?: AssistantMode;
  model?: string | null;
  provider?: string | null;
  options?: AssistantRequestOptions;
}

export interface AssistantRequestOptions {
  top_k?: number;
  score_threshold?: number;
  max_steps?: number;
  enable_tools?: boolean;
  enable_rag_tools?: boolean;
  enable_mcp_tools?: boolean;
  enable_context_debug?: boolean;
  enable_working_memory?: boolean;
  enable_working_memory_trace?: boolean;
  enable_long_term_memory?: boolean;
  enable_multi_agent?: boolean;
  enable_multi_agent_review?: boolean;
  enable_multi_agent_trace?: boolean;
}

export interface SendMessageResponse {
  user_message: MessageItem;
  assistant_message: MessageItem;
}

export type ConversationStreamEvent =
  | 'message_start'
  | 'delta'
  | 'message_end'
  | 'error'
  | 'done'
  | 'message';

export interface ConversationStreamChunk {
  event: ConversationStreamEvent;
  delta?: string;
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  content?: string;
  latency_ms?: number;
  error?: {
    code?: string;
    message?: string;
    detail?: string;
  };
}

export type AssistantStreamEvent =
  | 'assistant_start'
  | 'route_decision'
  | 'short_term_memory_loaded'
  | 'long_term_memory_retrieval_start'
  | 'long_term_memory_item'
  | 'long_term_memory_write'
  | 'working_memory_updated'
  | 'context_assembled'
  | 'tool_call_start'
  | 'tool_call_end'
  | 'delta'
  | 'assistant_end'
  | 'error'
  | 'done'
  | 'message'
  | (string & Record<never, never>);

export interface AssistantToolCallEvent {
  tool_name?: string;
  arguments?: Record<string, unknown>;
  reason?: string | null;
  step?: number;
  success?: boolean;
  latency_ms?: number;
  error_code?: string | null;
  error_message?: string | null;
  source?: 'internal' | 'mcp' | string;
  server_name?: string | null;
  risk_level?: 'low' | 'medium' | 'high' | string | null;
  role?: string | null;
  multi_agent_run_id?: string | null;
  metadata?: Record<string, unknown>;
  result?: Record<string, unknown>;
}

export interface AssistantSourceItem {
  chunk_id?: string;
  document_id?: string;
  filename?: string;
  heading?: string | null;
  score?: number;
  distance?: number;
  rerank_score?: number;
  rrf_score?: number;
  chunk_index?: number;
  content_preview?: string;
}

export type ContextTraceItem = {
  id: string;
  type: string;
  source: string;
  placement: string;
  priority: number;
  score: number;
  estimated_tokens: number;
  source_id?: string;
  metadata?: Record<string, unknown>;
};

export type ContextTrace = {
  candidate_count: number;
  selected_count: number;
  dropped_count: number;
  total_estimated_tokens: number;
  max_context_tokens: number;
  selected_items: ContextTraceItem[];
  dropped_items: Array<{
    id: string;
    type: string;
    source?: string;
    reason: string;
    detail?: string;
  }>;
  risk_flags?: {
    injection_risk?: boolean;
    matched_patterns?: string[];
  };
};

export interface AssistantRunItem {
  id: string;
  conversation_id: string;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  mode: AssistantMode | 'chat' | 'agent' | 'mcp';
  status: string;
  input: string;
  final_answer?: string | null;
  model?: string | null;
  provider?: string | null;
  latency_ms?: number | null;
  agent_run_id?: string | null;
  trace: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TraceSummary {
  trace_id?: string;
  span_count?: number;
  error_count?: number;
  llm_call_count?: number;
  tool_call_count?: number;
  mcp_call_count?: number;
  total_latency_ms?: number;
  total_tokens?: number;
  estimated_cost?: number;
  [key: string]: unknown;
}

export interface TraceSpan {
  id: string;
  trace_id: string;
  parent_span_id?: string | null;
  run_id: string;
  conversation_id?: string | null;
  assistant_run_id?: string | null;
  agent_run_id?: string | null;
  span_type: string;
  name: string;
  status: string;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  metadata: Record<string, unknown>;
  latency_ms?: number | null;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface TraceDetailResponse {
  trace_id: string;
  summary: TraceSummary;
  spans: TraceSpan[];
}

export interface MultiAgentTrace {
  enabled: boolean;
  run_id?: string;
  roles_used: string[];
  artifact_count: number;
  handoff_count: number;
  review_decision?: string;
  role_runs?: Array<{
    role: string;
    status: string;
    latency_ms?: number;
    error_code?: string | null;
    error_message?: string | null;
    artifact?: {
      id: string;
      role: string;
      artifact_type: string;
      title: string;
      confidence?: number;
      content?: string;
      data?: Record<string, unknown>;
      source_refs?: Array<Record<string, unknown>>;
      metadata?: Record<string, unknown>;
    } | null;
    trace?: Record<string, unknown>;
    tool_calls?: AssistantToolCallEvent[];
    handoffs?: {
      incoming?: Array<{
        id: string;
        from_role: string;
        to_role: string;
        summary: string;
        confidence?: number;
      }>;
      outgoing?: Array<{
        id: string;
        from_role: string;
        to_role: string;
        summary: string;
        confidence?: number;
      }>;
    };
  }>;
  artifacts: Array<{
    id: string;
    role: string;
    artifact_type: string;
    title: string;
    confidence?: number;
    content?: string;
  }>;
  handoffs: Array<{
    id: string;
    from_role: string;
    to_role: string;
    summary: string;
    confidence?: number;
  }>;
}

export interface AssistantStreamChunk {
  event: AssistantStreamEvent;
  delta?: string;
  assistant_run_id?: string;
  conversation_id?: string;
  requested_mode?: AssistantMode;
  mode?: 'chat' | 'agent' | 'mcp';
  reason?: string;
  matched_keywords?: string[];
  assistant_message_id?: string;
  agent_run_id?: string;
  latency_ms?: number;
  model?: string;
  provider?: string;
  tool_calls?: AssistantToolCallEvent[];
  sources?: AssistantSourceItem[];
  trace?: Record<string, unknown>;
  multi_agent?: MultiAgentTrace;
  trace_id?: string;
  trace_summary?: TraceSummary;
  context?: ContextTrace;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  step?: number;
  success?: boolean;
  source?: string;
  role?: string | null;
  multi_agent_run_id?: string | null;
  metadata?: Record<string, unknown>;
  error_code?: string | null;
  error_message?: string | null;
  error?: {
    code?: string;
    message?: string;
    detail?: string;
  };
}

export interface HistoryItem {
  timestamp: string;
  model: string;
  user_input: string;
  prompt: string;
  answer: string;
  elapsed_seconds: number;
}

export interface ClearHistoryResponse {
  success: boolean;
  message: string;
}

export interface ModelsResponse {
  current_provider: string;
  current_cloud_provider?: string | null;
  current_model: string;
  available_models: string[];
  providers?: {
    provider: string;
    current_model: string;
    available_models: string[];
  }[];
  cloud_providers?: {
    provider: string;
    current_model: string;
    available_models: string[];
  }[];
}

export interface SelectModelResponse {
  success: boolean;
  selected_provider: string;
  selected_cloud_provider?: string | null;
  selected_model: string;
  message: string;
}

export interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  source_path?: string;
  status: string;
  chunk_count: number;
  char_count: number;
  error_message?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
}

export interface UploadDocumentResponse {
  document_id: string;
  filename: string;
  file_type: string;
  status: string;
  chunk_count: number;
  char_count: number;
  created_at: string;
}

export interface DocumentChunkItem {
  id: string;
  document_id: string;
  chunk_index: number;
  heading?: string | null;
  content: string;
  char_count: number;
  estimated_tokens: number;
  embedding_status?: string;
  created_at: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
}

export interface DocumentChunkListResponse {
  items: DocumentChunkItem[];
}

export interface EmbeddingStatusItem {
  chunk_id: string;
  chunk_index: number;
  embedding_status: string;
  embedding_model?: string | null;
  embedding_error?: string | null;
  embedding_updated_at?: string | null;
}

export interface EmbeddingStatusResponse {
  document_id: string;
  items: EmbeddingStatusItem[];
}

export interface EmbedAllDocumentsResponse {
  total_chunks: number;
  embedded_chunks: number;
  failed_chunks: number;
  embedding_model: string;
  status: string;
}

export interface AgentRunItem {
  id: string;
  conversation_id: string;
  user_message_id: string;
  status: string;
  input: string;
  final_answer?: string | null;
  model?: string | null;
  provider: string;
  max_steps: number;
  step_count: number;
  total_latency_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AgentStepItem {
  id: string;
  run_id: string;
  step_index: number;
  step_type: string;
  thought?: string | null;
  reason?: string | null;
  tool_name?: string | null;
  tool_arguments: Record<string, unknown>;
  tool_result?: Record<string, unknown> | null;
  success: boolean;
  latency_ms: number;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
}

export interface AgentEventItem {
  id: string;
  run_id: string;
  step_id?: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AgentRunListResponse {
  conversation_id: string;
  runs: AgentRunItem[];
}

export interface AgentRunDetailResponse {
  run: AgentRunItem;
  steps: AgentStepItem[];
  events: AgentEventItem[];
}

// ---- API 函数 ----

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>('/health');
  return data;
}

export async function sendChat(payload: ChatRequest): Promise<ChatResponse> {
  const { data } = await http.post<ChatResponse>('/chat', payload);
  return data;
}

export async function sendChatStream(
  payload: ChatRequest,
  onChunk: (chunk: ChatStreamChunk) => void,
): Promise<void> {
  const streamUrl = process.env.UMI_APP_STREAM_API_URL || '/api/chat/stream';

  const response = await fetch(streamUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error('流式响应为空');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const event of events) {
      const lines = event
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.startsWith('data:'));

      for (const line of lines) {
        const data = line.slice(5).trim();

        if (!data) continue;
        if (data === '[DONE]') return;

        try {
          onChunk(JSON.parse(data) as ChatStreamChunk);
        } catch {
          // 忽略非 JSON 的 SSE 数据
        }
      }
    }
  }
}

function buildApiUrl(path: string): string {
  const baseUrl = API_BASE_URL;

  if (!baseUrl) return `/api${path}`;

  return `${baseUrl.replace(/\/$/, '')}${path}`;
}

function parseSseEvent(event: string): { event: string; data: string } | null {
  let eventName = 'message';
  const dataLines: string[] = [];

  event.split('\n').forEach((line) => {
    const trimmedLine = line.trim();

    if (trimmedLine.startsWith('event:')) {
      eventName = trimmedLine.slice(6).trim() || 'message';
    }

    if (trimmedLine.startsWith('data:')) {
      dataLines.push(trimmedLine.slice(5).trim());
    }
  });

  if (dataLines.length === 0) return null;

  return {
    event: eventName,
    data: dataLines.join('\n'),
  };
}

export async function createConversation(
  payload: ConversationCreateRequest,
): Promise<ConversationDetailResponse> {
  const { data } = await http.post<ConversationDetailResponse>(
    '/conversations',
    payload,
  );
  return data;
}

export async function getConversations(): Promise<ConversationListResponse> {
  const { data } = await http.get<ConversationListResponse>('/conversations');
  return data;
}

export interface DeleteConversationResponse {
  success: boolean;
  message: string;
  conversation_id: string;
}

export async function deleteConversation(
  conversationId: string,
): Promise<DeleteConversationResponse> {
  const { data } = await http.delete<DeleteConversationResponse>(
    `/conversations/${conversationId}`,
  );
  return data;
}

export async function getConversation(
  conversationId: string,
): Promise<ConversationDetailResponse> {
  const { data } = await http.get<ConversationDetailResponse>(
    `/conversations/${conversationId}`,
  );
  return data;
}

export async function getConversationMessages(
  conversationId: string,
): Promise<MessageListResponse> {
  const { data } = await http.get<MessageListResponse>(
    `/conversations/${conversationId}/messages`,
  );
  return data;
}

export async function sendConversationMessage(
  conversationId: string,
  payload: SendMessageRequest,
): Promise<SendMessageResponse> {
  const { data } = await http.post<SendMessageResponse>(
    `/conversations/${conversationId}/messages`,
    payload,
  );
  return data;
}

export async function sendConversationMessageStream(
  conversationId: string,
  payload: SendMessageRequest,
  onChunk: (chunk: ConversationStreamChunk) => void,
): Promise<void> {
  const response = await fetch(
    buildApiUrl(`/conversations/${conversationId}/messages/stream`),
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error('流式响应为空');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const rawEvent of events) {
      const parsedEvent = parseSseEvent(rawEvent);

      if (!parsedEvent) continue;
      if (parsedEvent.data === '[DONE]') {
        onChunk({ event: 'done' });
        return;
      }

      try {
        const data = JSON.parse(parsedEvent.data);

        if (parsedEvent.event === 'error') {
          onChunk({
            event: 'error',
            error: data,
          });
          continue;
        }

        onChunk({
          event: parsedEvent.event as ConversationStreamEvent,
          ...data,
        });
      } catch {
        // 忽略非 JSON 的 SSE 数据
      }
    }
  }
}

export async function sendAssistantMessageStream(
  conversationId: string,
  payload: AssistantStreamRequest,
  onChunk: (chunk: AssistantStreamChunk) => void,
): Promise<void> {
  const response = await fetch(
    buildApiUrl(`/conversations/${conversationId}/assistant/stream`),
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error('流式响应为空');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const rawEvent of events) {
      const parsedEvent = parseSseEvent(rawEvent);

      if (!parsedEvent) continue;
      if (parsedEvent.data === '[DONE]') {
        onChunk({ event: 'done' });
        return;
      }

      try {
        const data = JSON.parse(parsedEvent.data);

        if (parsedEvent.event === 'error') {
          onChunk({
            event: 'error',
            error: data,
          });
          continue;
        }

        onChunk({
          event: parsedEvent.event as AssistantStreamEvent,
          ...data,
        });
      } catch {
        // 忽略非 JSON 的 SSE 数据
      }
    }
  }
}

export async function getAssistantRun(
  runId: string,
): Promise<AssistantRunItem> {
  const { data } = await http.get<AssistantRunItem>(`/assistant/runs/${runId}`);
  return data;
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  const { data } = await http.get<TraceDetailResponse>(`/traces/${traceId}`);
  return data;
}

export async function getHistory(): Promise<HistoryItem[]> {
  const { data } = await http.get<HistoryItem[]>('/history');
  return data;
}

export async function clearHistory(): Promise<ClearHistoryResponse> {
  const { data } = await http.post<ClearHistoryResponse>('/history/clear');
  return data;
}

export async function getModels(): Promise<ModelsResponse> {
  const { data } = await http.get<ModelsResponse>('/models');
  return data;
}

export async function selectModel(
  model: string,
  provider?: string,
  cloudProvider?: string | null,
): Promise<SelectModelResponse> {
  const { data } = await http.post<SelectModelResponse>('/model/select', {
    provider,
    cloud_provider: cloudProvider,
    model,
  });
  return data;
}

export async function uploadDocument(
  file: File,
): Promise<UploadDocumentResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await http.post<UploadDocumentResponse>(
    '/documents/upload',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  );

  return data;
}

export async function getDocuments(): Promise<DocumentListResponse> {
  const { data } = await http.get<DocumentListResponse>('/documents');
  return data;
}

export async function triggerDocumentSplit(documentId: string): Promise<void> {
  await http.post(`/documents/${documentId}/split`);
}

export async function getDocumentChunks(
  documentId: string,
): Promise<DocumentChunkListResponse> {
  const { data } = await http.get<DocumentChunkListResponse>(
    `/documents/${documentId}/chunks`,
  );

  return data;
}

export async function getDocumentEmbeddingStatus(
  documentId: string,
): Promise<EmbeddingStatusResponse> {
  const { data } = await http.get<EmbeddingStatusResponse>(
    `/documents/${documentId}/embedding-status`,
  );

  return data;
}

export async function embedAllDocuments(): Promise<EmbedAllDocumentsResponse> {
  const { data } = await http.post<EmbedAllDocumentsResponse>(
    '/documents/embed-all',
  );

  return data;
}

export async function getAgentRuns(
  conversationId: string,
): Promise<AgentRunListResponse> {
  const { data } = await http.get<AgentRunListResponse>(
    `/agent/conversations/${conversationId}/runs`,
  );

  return data;
}

export async function getAgentRunDetail(
  runId: string,
): Promise<AgentRunDetailResponse> {
  const { data } = await http.get<AgentRunDetailResponse>(
    `/agent/runs/${runId}`,
  );

  return data;
}
