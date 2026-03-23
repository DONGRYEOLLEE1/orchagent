export interface AuthUser {
  id: string;
  login_id: string;
  role: string;
  status: string;
  display_name: string | null;
  email: string | null;
  must_change_password: boolean;
}
