import {
  DocumentChunkItem,
  DocumentItem,
  embedAllDocuments,
  getDocumentChunks,
  getDocumentEmbeddingStatus,
  getDocuments,
  triggerDocumentSplit,
  uploadDocument,
} from '@/services';
import JsonViewer from '@/components/JsonViewer';
import {
  CloudUploadOutlined,
  EyeOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  MessageOutlined,
  ReloadOutlined,
  ScissorOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { history } from '@umijs/max';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Input,
  message,
  Row,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import styles from './index.module.less';

const ALLOWED_EXTENSIONS = ['.md', '.txt'];
const ACCEPT_ATTR = '.md,.txt';

const formatDateTime = (value?: string): string => {
  if (!value) return '-';
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('zh-CN', { hour12: false });
};

const formatFileSize = (charCount?: number): string => {
  if (
    typeof charCount !== 'number' ||
    Number.isNaN(charCount) ||
    charCount < 0
  ) {
    return '-';
  }

  // 后端未返回 byte 大小时，使用 UTF-8 的粗略估算值用于前端展示。
  const estimatedBytes = charCount * 2;
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = estimatedBytes;
  let idx = 0;

  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }

  return `${size.toFixed(idx === 0 ? 0 : 2)} ${units[idx]} (估算)`;
};

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

  if (error instanceof Error) {
    return error.message;
  }

  return '请求失败，请稍后重试';
};

const statusColor = (status?: string): string => {
  const normalized = (status || '').toLowerCase();

  if (normalized.includes('fail') || normalized.includes('error')) {
    return 'error';
  }

  if (normalized.includes('process') || normalized.includes('pending')) {
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

const DocsPage: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState<boolean>(false);
  const [documentsError, setDocumentsError] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [embeddingAll, setEmbeddingAll] = useState<boolean>(false);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>('');
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState<boolean>(false);
  const [splittingDocumentId, setSplittingDocumentId] = useState<string>('');
  const [chunksLoading, setChunksLoading] = useState<boolean>(false);
  const [chunksError, setChunksError] = useState<string>('');
  const [chunks, setChunks] = useState<DocumentChunkItem[]>([]);
  const [keyword, setKeyword] = useState<string>('');

  const selectedDocument = useMemo(
    () => documents.find((item) => item.id === selectedDocumentId),
    [documents, selectedDocumentId],
  );

  const filteredDocuments = useMemo(() => {
    const normalized = keyword.trim().toLowerCase();

    if (!normalized) return documents;

    return documents.filter((item) =>
      [
        item.id,
        item.filename,
        item.file_type,
        item.status,
        item.error_message || '',
      ].some((value) => String(value || '').toLowerCase().includes(normalized)),
    );
  }, [documents, keyword]);

  const documentStats = useMemo(() => {
    return {
      total: documents.length,
      chunks: documents.reduce((sum, item) => sum + (item.chunk_count || 0), 0),
      chars: documents.reduce((sum, item) => sum + (item.char_count || 0), 0),
      failed: documents.filter(
        (item) => statusColor(item.status) === 'error' || item.error_message,
      ).length,
    };
  }, [documents]);

  const fetchDocuments = async (): Promise<void> => {
    setDocumentsLoading(true);
    setDocumentsError('');

    try {
      const response = await getDocuments();
      setDocuments(response.items || []);
    } catch (error) {
      setDocumentsError(getErrorText(error));
    } finally {
      setDocumentsLoading(false);
    }
  };

  const fetchChunks = async (documentId: string): Promise<void> => {
    setChunksLoading(true);
    setChunksError('');

    try {
      const [chunksResponse, embeddingResponse] = await Promise.all([
        getDocumentChunks(documentId),
        getDocumentEmbeddingStatus(documentId).catch(() => null),
      ]);

      const statusMap = new Map(
        (embeddingResponse?.items || []).map((item) => [
          item.chunk_id,
          item.embedding_status,
        ]),
      );

      const merged = [...(chunksResponse.items || [])]
        .map((chunk) => ({
          ...chunk,
          embedding_status: chunk.embedding_status || statusMap.get(chunk.id),
        }))
        .sort((a, b) => a.chunk_index - b.chunk_index);

      setChunks(merged);
    } catch (error) {
      setChunks([]);
      setChunksError(getErrorText(error));
    } finally {
      setChunksLoading(false);
    }
  };

  useEffect(() => {
    void fetchDocuments();
  }, []);

  useEffect(() => {
    if (!selectedDocumentId || !detailsDrawerOpen) {
      if (!selectedDocumentId) {
        setChunks([]);
        setChunksError('');
      }
      return;
    }

    void fetchChunks(selectedDocumentId);
  }, [selectedDocumentId, detailsDrawerOpen]);

  useEffect(() => {
    if (!selectedDocumentId && documents.length > 0) {
      setSelectedDocumentId(documents[0].id);
      return;
    }

    if (
      selectedDocumentId &&
      documents.every((item) => item.id !== selectedDocumentId)
    ) {
      setSelectedDocumentId(documents[0]?.id || '');
    }
  }, [documents, selectedDocumentId]);

  const handleUpload = async (): Promise<void> => {
    if (!selectedFile) {
      message.warning('请先选择要上传的文件');
      return;
    }

    setUploading(true);

    try {
      const result = await uploadDocument(selectedFile);
      message.success(`上传成功：${result.filename}`);
      setSelectedFile(null);
      await fetchDocuments();
      setSelectedDocumentId(result.document_id);
      setDetailsDrawerOpen(true);
      await fetchChunks(result.document_id);
    } catch (error) {
      message.error(`上传失败：${getErrorText(error)}`);
    } finally {
      setUploading(false);
    }
  };

  const handleSplit = async (document: DocumentItem): Promise<void> => {
    if (splittingDocumentId) {
      return;
    }

    setSplittingDocumentId(document.id);

    try {
      await triggerDocumentSplit(document.id);
      message.success(`文档切分已触发：${document.filename}`);
      await fetchDocuments();
      setSelectedDocumentId(document.id);
      setDetailsDrawerOpen(true);
      await fetchChunks(document.id);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        message.warning(
          '当前后端未开放独立切分接口（/documents/{id}/split），该项目上传文档时会自动切分。',
        );
      } else {
        message.error(`切分失败：${getErrorText(error)}`);
      }
    } finally {
      setSplittingDocumentId('');
    }
  };

  const handleEmbedAllDocuments = async (): Promise<void> => {
    if (embeddingAll) {
      return;
    }

    setEmbeddingAll(true);

    try {
      const result = await embedAllDocuments();
      message.success(
        `全部向量化完成：成功 ${result.embedded_chunks}，失败 ${result.failed_chunks}，总计 ${result.total_chunks}`,
      );

      await fetchDocuments();

      if (selectedDocumentId && detailsDrawerOpen) {
        await fetchChunks(selectedDocumentId);
      }
    } catch (error) {
      message.error(`全部向量化失败：${getErrorText(error)}`);
    } finally {
      setEmbeddingAll(false);
    }
  };

  const documentColumns: ColumnsType<DocumentItem> = [
    {
      title: '文档 ID',
      dataIndex: 'id',
      key: 'id',
      width: 220,
      ellipsis: true,
    },
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'file_type',
      key: 'file_type',
      width: 90,
      render: (value: string) => value || '-',
    },
    {
      title: '大小',
      dataIndex: 'char_count',
      key: 'char_count',
      width: 120,
      render: (value: number) => formatFileSize(value),
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '文档状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (value: string) => (
        <Tag color={statusColor(value)}>{value || '-'}</Tag>
      ),
    },
    {
      title: 'Chunk 数量',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 110,
      render: (value: number) => value ?? '-',
    },
    {
      title: '错误信息',
      dataIndex: 'error_message',
      key: 'error_message',
      width: 180,
      ellipsis: true,
      render: (value: string | null | undefined) =>
        value ? <Typography.Text type="danger">{value}</Typography.Text> : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, record) => (
        <Space size={8}>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => {
              setSelectedDocumentId(record.id);
              setDetailsDrawerOpen(true);
            }}
          >
            查看
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<ScissorOutlined />}
            loading={splittingDocumentId === record.id}
            disabled={Boolean(splittingDocumentId)}
            onClick={() => {
              void handleSplit(record);
            }}
          >
            切分文档
          </Button>
        </Space>
      ),
    },
  ];

  const chunkColumns: ColumnsType<DocumentChunkItem> = [
    {
      title: 'chunk_id',
      dataIndex: 'id',
      key: 'id',
      width: 220,
      ellipsis: true,
      render: (value: string) => (
        <Typography.Text copyable>{value}</Typography.Text>
      ),
    },
    {
      title: 'chunk_index',
      dataIndex: 'chunk_index',
      key: 'chunk_index',
      width: 150,
      sorter: (a, b) => a.chunk_index - b.chunk_index,
      defaultSortOrder: 'ascend',
    },
    {
      title: 'heading',
      dataIndex: 'heading',
      key: 'heading',
      ellipsis: true,
      render: (value?: string | null) => value || '无标题',
    },
    {
      title: 'char_count',
      dataIndex: 'char_count',
      key: 'char_count',
      width: 110,
    },
    {
      title: 'estimated_tokens',
      dataIndex: 'estimated_tokens',
      key: 'estimated_tokens',
      width: 140,
    },
    {
      title: 'embedding_status',
      dataIndex: 'embedding_status',
      key: 'embedding_status',
      width: 160,
      render: (value?: string) => (
        <Tag color={statusColor(value)}>{value || '-'}</Tag>
      ),
    },
    {
      title: 'created_at',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: 'updated_at',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value?: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button
          size="small"
          icon={<FileTextOutlined />}
          onClick={() => {
            void navigator.clipboard.writeText(record.content || '');
            message.success('Chunk 内容已复制');
          }}
        >
          复制
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <Typography.Title level={2} className={styles.title}>
            RAG 文档管理
          </Typography.Title>
          <Typography.Text className={styles.subtitle}>
            管理知识库文件、切分状态和 Chunk 内容。支持上传：
            {ALLOWED_EXTENSIONS.join('、')}
          </Typography.Text>
        </div>
        <Space wrap>
          <Button
            icon={<MessageOutlined />}
            onClick={() => history.push('/')}
          >
            返回聊天
          </Button>
          <Button
            icon={<FileSearchOutlined />}
            onClick={() => history.push('/traces')}
          >
            Trace
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} className={styles.summaryGrid}>
        <Col xs={12} lg={6}>
          <div className={styles.metric}>
            <span className={styles.metricLabel}>文档</span>
            <strong>{documentStats.total}</strong>
          </div>
        </Col>
        <Col xs={12} lg={6}>
          <div className={styles.metric}>
            <span className={styles.metricLabel}>Chunks</span>
            <strong>{documentStats.chunks}</strong>
          </div>
        </Col>
        <Col xs={12} lg={6}>
          <div className={styles.metric}>
            <span className={styles.metricLabel}>字符</span>
            <strong>{documentStats.chars.toLocaleString('zh-CN')}</strong>
          </div>
        </Col>
        <Col xs={12} lg={6}>
          <div className={styles.metric}>
            <span className={styles.metricLabel}>异常</span>
            <strong>{documentStats.failed}</strong>
          </div>
        </Col>
      </Row>

      <Card
        title="上传文档"
        className={styles.card}
        extra={
          <Typography.Text type="secondary">
            仅支持 .md / .txt，上传后自动入库
          </Typography.Text>
        }
      >
        <Space size={12} wrap className={styles.uploadActions}>
          <Upload
            accept={ACCEPT_ATTR}
            maxCount={1}
            beforeUpload={(file) => {
              const name = file.name.toLowerCase();
              const isAllowed = ALLOWED_EXTENSIONS.some((ext) =>
                name.endsWith(ext),
              );

              if (!isAllowed) {
                message.error('当前仅支持 .md 与 .txt 文件');
                return Upload.LIST_IGNORE;
              }

              setSelectedFile(file);
              return false;
            }}
            onRemove={() => {
              setSelectedFile(null);
            }}
            fileList={
              selectedFile
                ? [
                    {
                      uid: selectedFile.name,
                      name: selectedFile.name,
                      status: 'done',
                    },
                  ]
                : []
            }
          >
            <Button icon={<UploadOutlined />}>选择文件</Button>
          </Upload>
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            loading={uploading}
            onClick={() => void handleUpload()}
          >
            点击上传
          </Button>
        </Space>
      </Card>

      <Card
        title="文档列表"
        className={styles.card}
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              className={styles.searchInput}
              placeholder="搜索文件名、ID、状态"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={embeddingAll}
              onClick={() => void handleEmbedAllDocuments()}
            >
              全部向量化
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={documentsLoading}
              onClick={() => void fetchDocuments()}
            >
              刷新列表
            </Button>
          </Space>
        }
      >
        {documentsError ? (
          <Alert
            type="error"
            showIcon
            message="文档列表加载失败"
            description={documentsError}
            className={styles.alert}
          />
        ) : null}

        <Table<DocumentItem>
          rowKey="id"
          size="middle"
          loading={documentsLoading}
          columns={documentColumns}
          dataSource={filteredDocuments}
          pagination={false}
          scroll={{ x: 1300 }}
          locale={{
            emptyText: (
              <Empty
                description="暂无文档，请先上传 .md 或 .txt 文件"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
          rowClassName={(record) =>
            record.id === selectedDocumentId ? styles.selectedRow : ''
          }
          onRow={(record) => ({
            onClick: () => {
              setSelectedDocumentId(record.id);
            },
          })}
        />
      </Card>

      <Drawer
        width={1360}
        title={
          selectedDocument
            ? `文档详情：${selectedDocument.filename}`
            : '文档详情'
        }
        open={detailsDrawerOpen}
        onClose={() => {
          setDetailsDrawerOpen(false);
        }}
      >
        {!selectedDocument ? (
          <Empty
            description="请先在文档列表中选择一条记录"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <div className={styles.drawerContent}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="document_id">
                <Typography.Text copyable>
                  {selectedDocument.id}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="filename">
                {selectedDocument.filename}
              </Descriptions.Item>
              <Descriptions.Item label="file_type">
                {selectedDocument.file_type}
              </Descriptions.Item>
              <Descriptions.Item label="status">
                <Tag color={statusColor(selectedDocument.status)}>
                  {selectedDocument.status || '-'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="chunk_count">
                {selectedDocument.chunk_count ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="uploaded_at">
                {formatDateTime(selectedDocument.created_at)}
              </Descriptions.Item>
            </Descriptions>

            <Typography.Title level={5} className={styles.chunkTitle}>
              Chunks 列表（共 {chunks.length} 条）
            </Typography.Title>

            {chunksError ? (
              <Alert
                type="error"
                showIcon
                message="Chunk 列表加载失败"
                description={chunksError}
                className={styles.alert}
              />
            ) : null}

            <Table<DocumentChunkItem>
              rowKey="id"
              size="small"
              loading={chunksLoading}
              columns={chunkColumns}
              dataSource={chunks}
              pagination={false}
              scroll={{ x: 1500 }}
              locale={{
                emptyText: chunksError
                  ? 'Chunk 加载失败'
                  : '该文档暂无 Chunk 数据',
              }}
              expandable={{
                expandedRowRender: (chunk) => (
                  <div className={styles.expandedContent}>
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="document_id">
                        <Typography.Text copyable>
                          {chunk.document_id}
                        </Typography.Text>
                      </Descriptions.Item>
                      <Descriptions.Item label="content">
                        <Typography.Paragraph
                          className={styles.contentText}
                          copyable={{ text: chunk.content }}
                        >
                          {chunk.content}
                        </Typography.Paragraph>
                      </Descriptions.Item>
                      <Descriptions.Item label="metadata">
                        <JsonViewer value={chunk.metadata} maxHeight={260} />
                      </Descriptions.Item>
                    </Descriptions>
                  </div>
                ),
                rowExpandable: (chunk) =>
                  Boolean(chunk.content || chunk.metadata),
              }}
            />
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default DocsPage;
