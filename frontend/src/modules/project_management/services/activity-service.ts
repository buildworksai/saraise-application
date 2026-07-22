import type{ApiPage,ListFilters,ProjectActivity}from'../contracts';import{ENDPOINTS}from'../contracts';import{apiClient,page,withQuery}from'./client';
export const activityService={listForProject:(project_id:string,filters:ListFilters={})=>page(apiClient.get<ApiPage<ProjectActivity>>(withQuery(ENDPOINTS.ACTIVITIES.LIST,{...filters,project_id})))};
