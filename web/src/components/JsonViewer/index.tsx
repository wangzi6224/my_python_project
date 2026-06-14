import React from 'react';
import ReactJson from 'react-json-view';
import { Typography } from 'antd';
import styles from './index.module.less';

const { Text } = Typography;

interface JsonViewerProps {
  value: unknown;
  collapsed?: boolean | number;
  maxHeight?: number;
}

function normalizeJsonValue(value: unknown): object | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'object') return value as object;
  return { value };
}

const JsonViewer: React.FC<JsonViewerProps> = ({
  value,
  collapsed = 2,
  maxHeight = 360,
}) => {
  const source = normalizeJsonValue(value);

  if (!source) {
    return <Text type="secondary">-</Text>;
  }

  return (
    <div className={styles.viewer} style={{ maxHeight }}>
      <ReactJson
        src={source}
        name={false}
        theme="monokai"
        iconStyle="triangle"
        collapsed={collapsed}
        collapseStringsAfterLength={180}
        displayDataTypes={false}
        displayObjectSize
        enableClipboard
        indentWidth={2}
        style={{
          background: 'transparent',
          fontSize: 12,
          lineHeight: 1.55,
        }}
      />
    </div>
  );
};

export default JsonViewer;
