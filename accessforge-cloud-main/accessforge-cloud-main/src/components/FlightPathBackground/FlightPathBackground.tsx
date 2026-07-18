import React, { useEffect, useRef } from 'react';

export const FlightPathBackground: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    let disposed = false;
    let appInstance: any = null;

    import('./App').then(({ App }) => {
      if (disposed || !containerRef.current) return;
      const style = document.createElement('style');
      style.id = 'hide-dat-gui';
      style.innerHTML = '.dg.ac { display: none !important; } #ui-container { display: none !important; }';
      document.head.appendChild(style);

      appInstance = new App(containerRef.current);
    }).catch(() => {});

    return () => {
      disposed = true;
      if (appInstance) {
        appInstance.dispose();
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
