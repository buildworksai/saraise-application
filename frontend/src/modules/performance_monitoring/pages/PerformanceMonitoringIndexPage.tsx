import { Navigate } from 'react-router-dom';
import { ROUTES } from '../contracts';

export function PerformanceMonitoringIndexPage() {
  return <Navigate to={ROUTES.OVERVIEW} replace />;
}
