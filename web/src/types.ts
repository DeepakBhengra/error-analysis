export type ReplayMode = 'one_up' | 'random'
export type OrderCreateTarget = 'uat' | 'qa'
export type OrderModifyTarget = 'test' | 'qa1'
export type CurlType = 'create' | 'modify'
export type Outcome = 'SUCCESS' | 'FAILED' | 'TIMEOUT' | 'UNKNOWN' | 'READY'
export type TabFilter = 'all' | 'success' | 'failed'
export type OrderRequestSource = 'v6' | 'v2-converted'
export type CurlPanelTab = 'create' | 'modify'

export interface ReplayApiResponse {
  outcome: Outcome
  responsestatus: string
  statuscode: string
  responsemessage: string
  globalorderid: string
  customerOrderNumber: string
  originalCustomerOrderNumber: string
  sourceSearchText?: string | null
  http_status?: number | null
  http_body?: unknown
  message: string
  curl: string
  curlRepaired?: boolean
  repairedFields?: string[]
  unresolvedFields?: string[]
  repairMessage?: string
  result?: Record<string, unknown>
}

export interface CurlHttpResponse {
  httpStatus: number | null
  httpBody: unknown
  curlRepaired: boolean
  repairedFields: string[]
  unresolvedFields: string[]
  repairMessage: string
}

export interface OrderRequestPreviewResponse {
  outcome: 'READY'
  message: string
  curl: string
  body: Record<string, unknown>
  source: OrderRequestSource
  customerOrderNumber: string
  originalCustomerOrderNumber: string
  sourceSearchText?: string | null
  url: string
  query?: string
  recordCount?: number
}

export interface OrderModifyPreviewResponse {
  outcome: 'READY'
  message: string
  curl: string
  body: Record<string, unknown>
  customerOrderNumber: string
  originalCustomerOrderNumber: string
  sourceSearchText?: string | null
  url: string
  orderId: string
  query?: string
  recordCount?: number
  target?: OrderModifyTarget
}

export interface SessionResult extends ReplayApiResponse {
  id: string
  fetchedAt: string
}

export interface ErrorLookupFinding {
  error_code: string
  error_field: string
  program: string
  line?: number | null
  paragraph: string
  condition: string
  summary: string
  historical_resolution: string
}

export interface ErrorLookupResponse {
  error_code: string
  error_field: string
  historical_resolution: string
  program: string
  paragraph: string
  line?: number | null
  summary: string
  program_count: number
  finding_count: number
  findings: ErrorLookupFinding[]
  query?: {
    error_code?: string
    error_field?: string
  }
}

export interface ResolveErrorResponse {
  cached: boolean
  path: string
  result: ErrorLookupResponse
}

export interface AppSettings {
  dd_api_key: string
  dd_app_key: string
  dd_access_token: string
  dd_site: string
  dd_api_key_configured: boolean
  dd_app_key_configured: boolean
  dd_access_token_configured: boolean
  dd_auth_mode: 'access_token' | 'api_keys'
  order_create_username: string
  order_create_password: string
  order_create_cookie: string
  order_create_password_configured: boolean
  order_create_cookie_configured: boolean
  order_modify_test_username: string
  order_modify_test_password: string
  order_modify_qa1_username: string
  order_modify_qa1_password: string
  order_modify_test_password_configured: boolean
  order_modify_qa1_password_configured: boolean
  default_target: OrderCreateTarget
  default_modify_target: OrderModifyTarget
  default_mode: ReplayMode
}

export type AppSettingsUpdate = Partial<{
  dd_api_key: string
  dd_app_key: string
  dd_access_token: string
  dd_site: string
  order_create_username: string
  order_create_password: string
  order_create_cookie: string
  order_modify_test_username: string
  order_modify_test_password: string
  order_modify_qa1_username: string
  order_modify_qa1_password: string
  default_target: OrderCreateTarget
  default_modify_target: OrderModifyTarget
  default_mode: ReplayMode
}>
