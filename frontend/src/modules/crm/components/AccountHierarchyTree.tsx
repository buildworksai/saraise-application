/**
 * Account Hierarchy Tree Component
 *
 * Displays account hierarchy as a tree structure.
 */
import { useState } from 'react';
import { ChevronRight, ChevronDown, Building2 } from 'lucide-react';
import type { AccountHierarchyNode } from '../contracts';
import { useCrmConfiguration } from '../hooks/use-crm-configuration';
import { GovernedError, PageSkeleton } from './CrmPage';

interface AccountHierarchyTreeProps {
  hierarchy: AccountHierarchyNode;
}

const TreeNode = ({ node, autoExpandLevels, indentationPixels, level = 0 }: { node: AccountHierarchyNode; autoExpandLevels:number; indentationPixels:number; level?: number }) => {
  const [isExpanded, setIsExpanded] = useState(level < autoExpandLevels);

  const hasChildren = node.children && node.children.length > 0;
  const indent = level * indentationPixels;

  return (
    <div>
      <div
        className="flex items-center gap-2 py-2 hover:bg-muted/50 rounded px-2 cursor-pointer"
        style={{ paddingLeft: `${indent}px` }}
        onClick={() => hasChildren && setIsExpanded(!isExpanded)}
      >
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )
        ) : (
          <div className="w-4" /> // Spacer for alignment
        )}
        <Building2 className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm font-medium">{node.name}</span>
        {node.account_type && (
          <span className="text-xs text-muted-foreground ml-2 capitalize">
            ({node.account_type})
          </span>
        )}
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} autoExpandLevels={autoExpandLevels} indentationPixels={indentationPixels} level={level + 1} />
          ))}
        </div>
      )}
    </div>
  );
};

export const AccountHierarchyTree = ({ hierarchy }: AccountHierarchyTreeProps) => {
  const configuration=useCrmConfiguration();
  if(configuration.isLoading)return <PageSkeleton label="Loading hierarchy presentation configuration"/>;
  if(configuration.error||!configuration.data)return <GovernedError error={configuration.error} onRetry={()=>void configuration.refetch()} subject="Account hierarchy configuration"/>;
  const {hierarchy_auto_expand_levels:autoExpandLevels,hierarchy_indentation_pixels:indentationPixels}=configuration.data.document.ui;
  return (
    <div className="border rounded-lg p-4 bg-background">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-foreground mb-1">Account Hierarchy</h3>
        <p className="text-xs text-muted-foreground">
          {hierarchy.children && hierarchy.children.length > 0
            ? `${hierarchy.children.length} child account(s)`
            : 'No child accounts'}
        </p>
      </div>
      <div className="space-y-1">
        <TreeNode node={hierarchy} autoExpandLevels={autoExpandLevels} indentationPixels={indentationPixels} level={0} />
      </div>
    </div>
  );
};
