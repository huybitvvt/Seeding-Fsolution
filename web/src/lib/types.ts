export type FbUser = { name?: string };

export type FbComment = {
  id?: string;
  from?: FbUser;
  message?: string;
  created_time?: string;
  attachment?: { type?: string };
  comments?: { data?: FbComment[]; summary?: { total_count?: number } };
};

export type FbAttachment = {
  type?: string;
  media?: { image?: { src?: string }; source?: string };
  url?: string;
};

export type FbPost = {
  id: string;
  message?: string;
  from?: FbUser;
  created_time?: string;
  permalink_url?: string;
  is_hidden?: boolean;
  _group_id?: string;
  reactions?: { summary?: { total_count?: number } };
  shares?: { count?: number };
  comments?: { data?: FbComment[]; summary?: { total_count?: number } };
  attachments?: { data?: FbAttachment[] };
};

export type FbPage = { id: string; name: string };

export type GroupRow = { id: string; name: string };

export type StaffAccount = {
  id?: string;
  name?: string;
  username?: string;
  role?: 'admin' | 'staff' | string;
  cookie_masked?: string;
  facebook_user_id?: string;
  enabled?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type ManagedChannel = {
  id?: string;
  platform?: string;
  channel_name?: string;
  channel_type?: string;
  link?: string;
  target_id?: string;
  note?: string;
  created_at?: string;
  updated_at?: string;
};

export type BusinessProfile = {
  business_name?: string;
  phone?: string;
  address?: string;
  why_choose_us?: string;
  extra_notes?: string;
};

export type Lead = {
  id?: string | number;
  lead_key?: string;
  platform?: string;
  name?: string;
  phone?: string;
  phones?: string[];
  need?: string;
  source?: string;
  source_id?: string;
  post_id?: string;
  group_id?: string;
  post_url?: string;
  comment_id?: string;
  comment_url?: string;
  product_or_service?: string;
  location?: string;
  budget?: string;
  intent?: string;
  urgency?: string;
  contact_status?: string;
  confidence?: number;
  evidence?: string;
  created_at?: string;
};

export type ContentPipelineArticle = {
  id: string;
  source_id?: string;
  source_name?: string;
  source_type?: string;
  title?: string;
  url?: string;
  summary?: string;
  published_at?: string;
  status?: 'new' | 'written' | string;
  created_at?: string;
};

export type ContentPipelinePost = {
  id: string;
  article_id?: string;
  article_title?: string;
  article_url?: string;
  source_name?: string;
  format?: string;
  content?: string;
  hashtags?: string;
  status?: 'draft' | 'posted' | string;
  created_by_staff_name?: string;
  created_at?: string;
  updated_at?: string;
};

export type ReplySuggestion = {
  post_id?: string;
  intent_label?: string;
  confidence?: number;
  target_source?: string;
  customer_name?: string;
  customer_need?: string;
  recommended_approach?: string;
  business_phone?: string;
  suggested_replies?: { label?: string; text?: string }[];
  storage?: string;
  warning?: string;
};

export type CommentSummary = {
  post_id?: string;
  comment_count?: number;
  fetched_comment_count?: number;
  comment_authors_count?: number;
  summary?: string;
  sentiment?: string;
  urgency?: string;
  main_topics?: string[];
  customer_intents?: { intent?: string; count?: number; evidence?: string }[];
  top_questions?: string[];
  notable_comments?: { author?: string; text?: string; reason?: string }[];
  lead_signals?: { author?: string; need?: string; evidence?: string }[];
  recommended_action?: string;
  spam_or_noise_count?: number;
  storage?: string;
  warning?: string;
};

export type StoredPostComment = {
  source?: 'facebook' | 'tiktok' | string;
  post_id?: string;
  post_url?: string;
  comment_id?: string;
  parent_comment_id?: string;
  depth?: number;
  author_id?: string;
  author_name?: string;
  message?: string;
  attachment_type?: string;
  created_time?: string;
  matched_keywords?: string[];
  is_matched?: boolean;
  phone?: string;
  phones?: string[];
  comment_url?: string;
  channel_name?: string;
  video_title?: string;
  fetched_at?: string;
};

export type TikTokCommentStat = {
  post_id?: string;
  video_id?: string;
  post_url?: string;
  channel_name?: string;
  video_title?: string;
  comment_count?: number;
  matched_count?: number;
  phone_count?: number;
  latest_fetched_at?: string;
  latest_comment_at?: string;
  comments?: StoredPostComment[];
};

export type CommentLog = {
  id?: string | number;
  staff_id?: string;
  staff_name?: string;
  staff_username?: string;
  post_id?: string;
  group_id?: string;
  post_url?: string;
  comment_text?: string;
  comment_image_url?: string;
  comment_id?: string;
  status?: 'success' | 'failed' | string;
  error_message?: string;
  created_at?: string;
};
