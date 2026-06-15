import { useChatContext } from '@/contexts/ChatContext';
import {
  ApiOutlined,
  DeleteOutlined,
  FileTextOutlined,
  MessageOutlined,
  PlusOutlined,
  RadarChartOutlined,
} from '@ant-design/icons';
import { Badge, Button, Popconfirm, Select, Typography } from 'antd';
import React, { useMemo } from 'react';
import styles from './index.module.less';

const { Text } = Typography;

const Sidebar: React.FC = () => {
  const {
    health,
    healthError,
    models,
    modelSwitching,
    currentProvider,
    currentCloudProvider,
    currentModel,
    conversations,
    activeConversationId,
    conversationsLoading,
    conversationsError,
    createConversation,
    deleteConversation,
    selectConversation,
    startNewConversation,
    handleSelectProvider,
    handleSelectCloudProvider,
    handleSelectModel,
  } = useChatContext();

  const providerOptions = useMemo(
    () =>
      models?.providers?.map((item) => ({
        label: item.provider,
        value: item.provider,
      })) ?? [],
    [models?.providers],
  );

  const selectedProviderModels = useMemo(
    () => models?.providers?.find((item) => item.provider === currentProvider),
    [currentProvider, models?.providers],
  );
  const selectedCloudProviderModels = useMemo(
    () =>
      models?.cloud_providers?.find(
        (item) => item.provider === currentCloudProvider,
      ),
    [currentCloudProvider, models?.cloud_providers],
  );

  const modelOptions = useMemo(
    () =>
      (
        (currentProvider === 'cloud'
          ? selectedCloudProviderModels?.available_models
          : selectedProviderModels?.available_models) ||
        models?.available_models ||
        []
      ).map((m) => ({
        label: m,
        value: m,
      })),
    [
      currentProvider,
      models?.available_models,
      selectedCloudProviderModels?.available_models,
      selectedProviderModels?.available_models,
    ],
  );

  const cloudProviderOptions = useMemo(
    () =>
      models?.cloud_providers?.map((item) => ({
        label:
          item.provider === 'deepseek'
            ? 'DeepSeek'
            : item.provider === 'qwen'
            ? 'Qwen'
            : 'GLM',
        value: item.provider,
      })) ?? [],
    [models?.cloud_providers],
  );

  return (
    <div className={styles.sidebar}>
      {/* App Title */}
      <div className={styles.newChatWrapper}>
        <Text strong className={styles.appTitle}>
          NexusAI
        </Text>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          className={styles.newChatBtn}
          block
          onClick={() => {
            startNewConversation();
            createConversation();
          }}
        >
          新建会话
        </Button>
      </div>

      <div className={styles.divider} />

      {/* Backend Status */}
      <div className={styles.sectionPad}>
        {healthError ? (
          <Badge
            status="error"
            text={<Text className={styles.textDanger}>后端离线</Text>}
          />
        ) : health ? (
          <Badge
            status="success"
            text={<Text className={styles.textSuccess}>后端在线</Text>}
          />
        ) : (
          <Badge
            status="processing"
            text={<Text className={styles.textSm}>连接中…</Text>}
          />
        )}
      </div>

      {/* Provider / Model Selection */}
      {providerOptions.length > 0 && (
        <div className={styles.sectionPad}>
          <Text className={styles.sectionLabel}>选择 Provider</Text>
          <Select
            className={styles.modelSelect}
            value={currentProvider || undefined}
            options={providerOptions}
            onChange={handleSelectProvider}
            disabled={modelSwitching}
            placeholder="选择 Provider"
          />
        </div>
      )}

      {currentProvider === 'cloud' && cloudProviderOptions.length > 0 && (
        <div className={styles.sectionPad}>
          <Text className={styles.sectionLabel}>选择 Cloud</Text>
          <Select
            className={styles.modelSelect}
            value={currentCloudProvider || undefined}
            options={cloudProviderOptions}
            onChange={handleSelectCloudProvider}
            disabled={modelSwitching}
            placeholder="选择 Cloud"
          />
        </div>
      )}

      {modelOptions.length > 0 && (
        <div className={styles.sectionPad}>
          <Text className={styles.sectionLabel}>选择模型</Text>
          <Select
            className={styles.modelSelect}
            value={currentModel || undefined}
            options={modelOptions}
            disabled={modelSwitching}
            onChange={(model) =>
              handleSelectModel(
                model,
                currentProvider,
                currentProvider === 'cloud' ? currentCloudProvider : null,
              )
            }
            placeholder="选择模型"
          />
        </div>
      )}

      <div className={styles.divider} />

      {/* Bottom Panel: flex column = conversationList(flex:1) + quickTools */}
      <div className={styles.bottomPanel}>
        <div className={`${styles.historyHeader} ${styles.listHeader}`}>
          <Text className={styles.sectionLabel}>会话</Text>
        </div>
        <div className={styles.conversationList}>
          {conversationsLoading && conversations.length === 0 ? (
            <div className={styles.emptyTip}>
              <Text className={styles.emptyText}>加载中…</Text>
            </div>
          ) : conversationsError && conversations.length === 0 ? (
            <div className={styles.emptyTip}>
              <Text className={styles.emptyText}>{conversationsError}</Text>
            </div>
          ) : conversations.length === 0 ? (
            <div className={styles.emptyTip}>
              <Text className={styles.emptyText}>暂无会话</Text>
            </div>
          ) : (
            conversations.map((item) => (
              <div
                key={item.id}
                className={`${styles.convItem} ${
                  item.id === activeConversationId ? styles.convItemActive : ''
                }`}
                onClick={() => selectConversation(item.id)}
              >
                <MessageOutlined className={styles.convIcon} />
                <Text
                  ellipsis={{ tooltip: item.title }}
                  className={styles.convTitle}
                >
                  {item.title}
                </Text>
                <Text className={styles.convMeta}>{item.message_count}</Text>
                <Popconfirm
                  title="删除会话"
                  description="确定要删除该会话及其全部消息吗？"
                  onConfirm={(e) => {
                    e?.stopPropagation();
                    deleteConversation(item.id);
                  }}
                  onCancel={(e) => {
                    e?.stopPropagation();
                  }}
                  okText="确定"
                  cancelText="取消"
                  placement="right"
                >
                  <DeleteOutlined
                    className={styles.convDeleteBtn}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              </div>
            ))
          )}
        </div>

        <div className={`${styles.divider} ${styles.toolsDivider}`} />
        <div className={`${styles.historyHeader} ${styles.toolsHeader}`}>
          <Text className={styles.sectionLabel}>快捷工具</Text>
        </div>
        <div className={styles.quickToolsPanel}>
          <div
            className={styles.quickToolItem}
            onClick={() => {
              window.location.href = '/docs';
            }}
          >
            <FileTextOutlined className={styles.quickToolIcon} />
            <Text className={styles.quickToolTitle}>文档管理</Text>
            <Text className={styles.quickToolArrow}>›</Text>
          </div>
          <div
            className={styles.quickToolItem}
            onClick={() => {
              window.location.href = '/traces';
            }}
          >
            <RadarChartOutlined className={styles.quickToolIcon} />
            <Text className={styles.quickToolTitle}>Agent Trace</Text>
            <Text className={styles.quickToolArrow}>›</Text>
          </div>
          <div
            className={styles.quickToolItem}
            onClick={() => {
              window.location.href = '/admin/mcp';
            }}
          >
            <ApiOutlined className={styles.quickToolIcon} />
            <Text className={styles.quickToolTitle}>MCP 管理</Text>
            <Text className={styles.quickToolArrow}>›</Text>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
