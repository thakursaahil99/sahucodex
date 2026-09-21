/** Response shapes of the public profile API (see apps/api/app/modules/users/schemas.py and .../profiles/schemas.py). */

export interface PublicProfile {
  username: string;
  avatar_url: string | null;
  bio: string | null;
  country: string | null;
  website: string | null;
  github_url: string | null;
  joined_at: string;
}

export interface DifficultyCounts {
  easy: number;
  medium: number;
  hard: number;
  total: number;
}

export interface StreakInfo {
  current: number;
  longest: number;
  last_active_date: string | null; // ISO date, UTC
}

export interface AchievementInfo {
  key: string;
  name: string;
  description: string;
  icon: string;
  earned: boolean;
  earned_at: string | null;
}

export interface ActivityDay {
  date: string; // ISO date, UTC
  count: number;
}

export interface ProfileStats {
  solved: DifficultyCounts;
  total_submissions: number;
  accepted_submissions: number;
  acceptance_rate: number | null;
  streak: StreakInfo;
  achievements: AchievementInfo[];
  activity: ActivityDay[];
}
