/** API 响应类型定义。 */

export interface SessionUser {
  username: string
  role: string
  role_label: string
  is_admin: boolean
}

export interface Category {
  key: string
  label: string
}

export interface Meta {
  categories: Category[]
  brands: string[]
  total: number
  dataset_name: string
  disclaimer: string
  score_display_name: string
  user: SessionUser
}

export interface Product {
  id: string
  name: string
  category: string
  price: number | null
  brand: string
  specs: Record<string, unknown>
  use_cases: string[]
  pros: string[]
  cons: string[]
  data_source: string
  data_status: string
  model: string
  image_url: string
  source_url: string
  updated_at: string
  missing_fields?: string[]
}

export interface ProductList {
  products: Product[]
  categories: Category[]
  brands: string[]
  total: number
  dataset_name: string
  disclaimer: string
  issues: string[]
}

/** 决策报告里的商品快照字段。 */
export interface ReportItem {
  rank: number
  product_id: string
  name: string
  brand: string
  category_label: string
  price_label: string
  score_total: number
  match_level: string
  budget_label: string
  reasons: string[]
  pros: string[]
  cons: string[]
  data_source: string
  updated_at: string
  data_issues: string[]
  model: string
  source_url: string
  data_status: string
  price_source: string
  price_collected_at: string
}

export interface DecisionReport {
  title?: string
  demand_summary?: string
  created_at?: string
  conclusion?: string
  recommendations: ReportItem[]
  over_budget: ReportItem[]
  demand_facts?: [string, string][]
  filter_facts?: [string, string][]
  notes?: string[]
  to_verify?: string[]
  relaxations?: string[]
  dataset_disclaimer?: string
  within_budget_total?: number
  over_budget_total?: number
  [key: string]: unknown
}

export interface AnalysisResult {
  status: 'ok' | 'need_info'
  questions?: string[]
  report?: DecisionReport
  ai_enhanced?: boolean
}

export interface HistoryEntry {
  id: number
  created_at: string
  demand_summary: string
  top_product: string
  top_score: number | null
  result_count: number
  user_id: string | null
}

export interface Preferences {
  ai_enhanced: boolean
  price_priority: 'none' | 'value' | 'performance' | 'brand'
  show_over_budget: boolean
  auto_apply: boolean
}

export interface Overview {
  healthy: boolean
  message: string
  user_count: number
  admin_count: number
  users: { username: string; role: string; is_active: boolean; created_at: string }[]
  product_count: number
  incomplete_products: number
  categories: Category[]
  dataset_name: string
  dataset_updated_at: string
}

export interface Citation {
  title: string
  excerpt: string
}

export interface QASpec { key: string; label: string; value: string }
export interface QADimension {
  key: string
  label: string
  score: number
  weight: number
  reason: string
}
export interface QAProduct {
  id: string
  name: string
  brand: string
  model: string
  category_label: string
  price: number | null
  score_total: number
  budget_label: string
  within_budget: boolean
  use_cases: string[]
  pros: string[]
  cons: string[]
  specs: QASpec[]
  dimensions: QADimension[]
  data_source: string
  data_status: string
  updated_at: string
  price_source: string
  price_collected_at: string
  source_url: string
  image_url: string
}

export interface QAResult {
  answer: string
  source: 'knowledge+products' | 'knowledge' | 'general-knowledge' | 'catalog' | 'empty'
  products: QAProduct[]
  citations: Citation[]
  retrieval_mode: string
  retrieval_note: string
}

export interface ComparisonTable {
  products: Record<string, unknown>[]
  rows: Record<string, unknown>[]
}
