/** Response shapes of the community API (see apps/api/app/modules/community/schemas.py). */

export type TargetType = "discussion" | "comment";

export interface AuthorOut {
  id: string | null;
  username: string | null;
}

export interface DiscussionListItem {
  id: string;
  title: string;
  author: AuthorOut;
  vote_score: number;
  comment_count: number;
  created_at: string;
}

/** A DiscussionListItem plus which problem it's under — used only by the cross-problem `/discussions` feed, where
 * (unlike a problem's own tab) that context isn't already on screen. */
export interface RecentDiscussionItem extends DiscussionListItem {
  problem_slug: string;
  problem_title: string;
}

export interface CommentOut {
  id: string;
  body: string;
  author: AuthorOut;
  vote_score: number;
  /** -1, 0, or 1 — the caller's own vote on this comment; 0 for an anonymous viewer or one who hasn't voted. */
  my_vote: number;
  removed: boolean;
  created_at: string;
}

export interface DiscussionDetail {
  id: string;
  problem_slug: string;
  title: string;
  body: string;
  author: AuthorOut;
  vote_score: number;
  my_vote: number;
  removed: boolean;
  created_at: string;
  comments: CommentOut[];
}

export interface NotificationOut {
  id: string;
  type: "DISCUSSION_REPLY" | "COMMENT_REPLY" | "CONTENT_REMOVED";
  data: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

// --- moderation ------------------------------------------------------------------------------------------------

export interface ReportOut {
  id: string;
  target_type: TargetType;
  target_id: string;
  reporter: AuthorOut;
  reason: string;
  status: "OPEN" | "RESOLVED" | "DISMISSED";
  created_at: string;
  target_snippet: string | null;
  target_removed: boolean;
}
