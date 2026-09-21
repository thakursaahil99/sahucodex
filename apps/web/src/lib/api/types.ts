/** Response shapes of the SahuCodeX API (see apps/api schemas). */

export interface Profile {
  avatar_url: string | null;
  bio: string | null;
  country: string | null;
  website: string | null;
  github_url: string | null;
}

export interface User {
  id: string;
  email: string;
  username: string;
  roles: string[];
  email_verified: boolean;
  created_at: string;
  profile: Profile;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

export interface RegisterResponse {
  user: User;
}

export interface MessageResponse {
  message: string;
}

export interface SessionInfo {
  id: string;
  ip_address: string | null;
  user_agent: string | null;
  last_active_at: string;
  current: boolean;
}
