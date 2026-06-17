import {
  AimOutlined,
  CompressOutlined,
  MinusOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Button, Space, Tooltip } from 'antd';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import styles from './index.module.less';

interface FlowCanvasProps {
  width: number;
  height: number;
  ariaLabel: string;
  children: React.ReactNode;
}

const MIN_SCALE = 0.35;
const MAX_SCALE = 2.5;

const FlowCanvas: React.FC<FlowCanvasProps> = ({
  width,
  height,
  ariaLabel,
  children,
}) => {
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ x: number; y: number; left: number; top: number }>();
  const [scale, setScale] = useState(1);
  const [dragging, setDragging] = useState(false);

  const clamp = (value: number) =>
    Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));

  const center = useCallback((nextScale = scale) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({
      left: Math.max(0, (width * nextScale - viewport.clientWidth) / 2),
      top: Math.max(0, (height * nextScale - viewport.clientHeight) / 2),
      behavior: 'smooth',
    });
  }, [height, scale, width]);

  const changeScale = useCallback((next: number) => {
    const viewport = viewportRef.current;
    const normalized = clamp(next);
    if (!viewport) return setScale(normalized);
    const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / scale;
    const centerY = (viewport.scrollTop + viewport.clientHeight / 2) / scale;
    setScale(normalized);
    requestAnimationFrame(() => viewport.scrollTo({
      left: centerX * normalized - viewport.clientWidth / 2,
      top: centerY * normalized - viewport.clientHeight / 2,
    }));
  }, [scale]);

  const fit = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const next = clamp(Math.min(
      (viewport.clientWidth - 40) / width,
      (viewport.clientHeight - 40) / height,
    ));
    setScale(next);
    requestAnimationFrame(() => center(next));
  }, [center, height, width]);

  const reset = () => {
    setScale(1);
    requestAnimationFrame(() => center(1));
  };

  useEffect(() => {
    const timer = window.setTimeout(fit, 0);
    return () => window.clearTimeout(timer);
  }, [fit]);

  return (
    <div className={styles.shell}>
      <div className={styles.toolbar}>
        <Space.Compact>
          <Tooltip title="缩小"><Button size="small" icon={<MinusOutlined />} onClick={() => changeScale(scale - 0.15)} /></Tooltip>
          <Button size="small" className={styles.scaleLabel}>{Math.round(scale * 100)}%</Button>
          <Tooltip title="放大"><Button size="small" icon={<PlusOutlined />} onClick={() => changeScale(scale + 0.15)} /></Tooltip>
        </Space.Compact>
        <Space.Compact>
          <Tooltip title="适配窗口"><Button size="small" icon={<CompressOutlined />} onClick={fit} /></Tooltip>
          <Tooltip title="居中"><Button size="small" icon={<AimOutlined />} onClick={() => center()} /></Tooltip>
          <Tooltip title="100% 并居中"><Button size="small" icon={<ReloadOutlined />} onClick={reset} /></Tooltip>
        </Space.Compact>
      </div>
      <div
        ref={viewportRef}
        className={`${styles.viewport} ${dragging ? styles.dragging : ''}`}
        onPointerDown={(event) => {
          const viewport = viewportRef.current;
          if (!viewport || (event.target as Element).closest('[role="button"]')) return;
          dragRef.current = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
          viewport.setPointerCapture(event.pointerId);
          setDragging(true);
        }}
        onPointerMove={(event) => {
          const viewport = viewportRef.current;
          const drag = dragRef.current;
          if (!viewport || !drag) return;
          viewport.scrollLeft = drag.left - (event.clientX - drag.x);
          viewport.scrollTop = drag.top - (event.clientY - drag.y);
        }}
        onPointerUp={(event) => {
          dragRef.current = undefined;
          setDragging(false);
          viewportRef.current?.releasePointerCapture(event.pointerId);
        }}
        onWheel={(event) => {
          if (!event.ctrlKey && !event.metaKey) return;
          event.preventDefault();
          changeScale(scale + (event.deltaY < 0 ? 0.12 : -0.12));
        }}
      >
        <svg
          width={width * scale}
          height={height * scale}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={ariaLabel}
          className={styles.svg}
        >
          {children}
        </svg>
      </div>
      <span className={styles.hint}>拖拽平移 · Ctrl/⌘ + 滚轮缩放</span>
    </div>
  );
};

export default FlowCanvas;
