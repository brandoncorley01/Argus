import type { InstitutionalRole } from "@/lib/types";

export type CreateUserPayload = {
  username: string;
  password: string;
  email: string | null;
  roles: InstitutionalRole[];
};
