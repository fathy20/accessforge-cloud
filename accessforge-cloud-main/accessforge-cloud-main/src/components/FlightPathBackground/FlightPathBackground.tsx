import React, { useEffect, useRef } from 'react';
import { App } from './App';

export const FlightPathBackground: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<App | null>(null);

  useEffect(() => {
    if (containerRef.current && !appRef.current) {
      // Hide any UI from dat.gui if it leaks
      const style = document.createElement('style');
      style.id = 'hide-dat-gui';
      style.innerHTML = '.dg.ac { display: none !important; } #ui-container { display: none !important; }';
      document.head.appendChild(style);

      appRef.current = new App(containerRef.current);
    }

    return () => {
      if (appRef.current) {
        appRef.current.dispose();
        appRef.current = null;
      }
      const style = document.getElementById('hide-dat-gui');
      if (style) {
        style.remove();
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
      }}
    />
  );
};
