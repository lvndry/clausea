import type { Message } from "./message";

export interface Conversation {
  id: string;
  user_id: string;
  product_name: string;
  product_slug?: string;
  company_name?: string | null;
  product_description?: string;
  documents: string[];
  messages: Message[];
  title?: string | null;
  archived?: boolean;
  pinned?: boolean;
  tags?: string[];
  message_count?: number;
  last_message_at?: string | null;
  created_at: string;
  updated_at: string;
}
