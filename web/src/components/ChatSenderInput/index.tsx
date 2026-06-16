import { Sender } from '@ant-design/x';
import { Button, Checkbox, Flex, Segmented, Tooltip } from 'antd';
import classNames from 'classnames';
import React, { useState } from 'react';
import { useChatContext } from '../../contexts/ChatContext';
import { AssistantMode, AssistantRequestOptions } from '../../services/api';
import styles from './index.module.less';

export interface ChatSenderInputProps {
  /** textarea 最小最大行数 */
  autoSize?: { minRows?: number; maxRows?: number };
  /** 外层包裹 div 的额外 className */
  className?: string;
  /** Sender 组件的额外 className */
  senderClassName?: string;
}

interface AdvancedOptions {
  enableMultiAgent: boolean;
  enableMcpTools: boolean;
  enableLongTermMemory: boolean;
  enableContextDebug: boolean;
}

const ChatSenderInput: React.FC<ChatSenderInputProps> = ({
  autoSize = { minRows: 2, maxRows: 6 },
  className,
  senderClassName,
}) => {
  const { sendMessage, loading } = useChatContext();

  const [inputValue, setInputValue] = useState('');
  const [mode, setMode] = useState<AssistantMode>('auto');
  const [advancedOptions, setAdvancedOptions] = useState<AdvancedOptions>({
    enableMultiAgent: true,
    enableMcpTools: true,
    enableLongTermMemory: true,
    enableContextDebug: true,
  });

  const buildAssistantOptions = (): AssistantRequestOptions => ({
    enable_multi_agent: advancedOptions.enableMultiAgent,
    enable_tools: true,
    enable_mcp_tools: mode === 'mcp' || advancedOptions.enableMcpTools,
    enable_working_memory: true,
    enable_working_memory_trace: advancedOptions.enableContextDebug,
    enable_long_term_memory: advancedOptions.enableLongTermMemory,
    enable_context_debug: advancedOptions.enableContextDebug,
    max_steps: 6,
  });

  const handleSubmit = (val: string) => {
    if (!val.trim() || loading) return;
    sendMessage(val.trim(), {
      mode: advancedOptions.enableMultiAgent ? 'agent' : mode,
      assistantOptions: buildAssistantOptions(),
    });
    setInputValue('');
  };

  const updateAdvancedOption = (key: keyof AdvancedOptions, value: boolean) => {
    setAdvancedOptions((prev) => ({ ...prev, [key]: value }));
  };

  const handleKeyDown = (e: React.KeyboardEvent): false | void => {
    if (
      e.key === 'Enter' &&
      !e.shiftKey &&
      !e.ctrlKey &&
      !e.altKey &&
      !e.metaKey &&
      !e.nativeEvent.isComposing
    ) {
      e.preventDefault();
      handleSubmit(inputValue);
      return false;
    }
  };

  return (
    <div className={classNames(styles.wrapper, className)}>
      <Sender
        className={classNames(styles.sender, senderClassName)}
        value={inputValue}
        onChange={setInputValue}
        suffix={false}
        onSubmit={handleSubmit}
        onKeyDown={handleKeyDown}
        submitType="enter"
        placeholder="请输入你的问题"
        autoSize={autoSize}
        loading={loading}
        footer={
          <div className={styles.footer}>
            <Flex align="center" justify="space-between" gap={8} wrap>
              <Tooltip title="自动会按问题类型选择；MCP = 使用外部工具，不是新的回答模式">
                <Flex align="center" gap={8} wrap>
                  <span className={styles.footerLabel}>模式：</span>
                  <Segmented
                    size="small"
                    value={mode}
                    onChange={(value) => setMode(value as AssistantMode)}
                    options={[
                      { label: '自动', value: 'auto' },
                      { label: '普通', value: 'chat' },
                      { label: 'Agent', value: 'agent' },
                      { label: 'MCP', value: 'mcp' },
                    ]}
                    className={styles.modeSegmented}
                  />
                </Flex>
              </Tooltip>
              <Button
                type="primary"
                className={styles.sendBtn}
                onClick={() => handleSubmit(inputValue)}
                disabled={!inputValue.trim() || loading}
              >
                发送
              </Button>
            </Flex>
            <Flex
              align="center"
              gap={10}
              wrap
              className={styles.advancedOptions}
            >
              <span className={styles.footerLabel}>高级选项：</span>
              <Checkbox
                checked={advancedOptions.enableMultiAgent}
                onChange={(event) =>
                  updateAdvancedOption('enableMultiAgent', event.target.checked)
                }
              >
                多智能体协作
              </Checkbox>
              <Checkbox
                checked={mode === 'mcp' || advancedOptions.enableMcpTools}
                disabled={mode === 'mcp'}
                onChange={(event) =>
                  updateAdvancedOption('enableMcpTools', event.target.checked)
                }
              >
                MCP 工具
              </Checkbox>
              <Checkbox
                checked={advancedOptions.enableLongTermMemory}
                onChange={(event) =>
                  updateAdvancedOption(
                    'enableLongTermMemory',
                    event.target.checked,
                  )
                }
              >
                长期记忆
              </Checkbox>
              <Checkbox
                checked={advancedOptions.enableContextDebug}
                onChange={(event) =>
                  updateAdvancedOption(
                    'enableContextDebug',
                    event.target.checked,
                  )
                }
              >
                上下文调试
              </Checkbox>
            </Flex>
          </div>
        }
      />
    </div>
  );
};

export default ChatSenderInput;
