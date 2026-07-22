import {ApiError,apiClient} from '@/services/api-client';
import type {ApiPage,ApiSuccess,ListFilters,PaginationMeta} from '../contracts';

export class ProjectManagementApiError extends Error{
 constructor(message:string,readonly status:number,readonly code:string,readonly correlationId:string|null){super(message);this.name='ProjectManagementApiError'}
}
export interface PageResult<T>{readonly items:readonly T[];readonly pagination:PaginationMeta;readonly correlationId:string}
const params=(filters:ListFilters={})=>{const query=new URLSearchParams();Object.entries(filters).forEach(([key,value])=>{if(value!==undefined&&value!=='')query.set(key,String(value))});return query.toString()};
export const withQuery=(path:string,filters:ListFilters={})=>{const q=params(filters);return q?`${path}?${q}`:path};
const mapError=(error:ApiError)=>new ProjectManagementApiError(error.message,error.status,error.code??'REQUEST_FAILED',error.correlationId??null);
export async function detail<T>(promise:Promise<ApiSuccess<T>>):Promise<T>{try{return(await promise).data}catch(error){if(error instanceof ApiError)throw mapError(error);throw error}}
export async function page<T>(promise:Promise<ApiPage<T>>):Promise<PageResult<T>>{try{const response=await promise;return{items:response.data,pagination:response.meta.pagination,correlationId:response.meta.correlation_id}}catch(error){if(error instanceof ApiError)throw mapError(error);throw error}}
export const idempotencyHeaders=(key:string):RequestInit=>({headers:{'Idempotency-Key':key}});
export const archive=async(path:string,version:number,key:string):Promise<void>=>{try{await apiClient.delete<void>(path,{...idempotencyHeaders(key),body:JSON.stringify({version,idempotency_key:key})})}catch(error){if(error instanceof ApiError)throw mapError(error);throw error}};
export {apiClient};
