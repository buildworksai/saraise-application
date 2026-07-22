import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { ROUTES } from '../contracts';

export function PerformanceMonitoringIndexPage() {
  useEffect(() => {
    document.title = 'Performance monitoring | SARAISE';
  }, []);
  return <Navigate to={ROUTES.OVERVIEW} replace />;
}
