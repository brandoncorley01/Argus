import type { CurrentUser, InstitutionalRole } from "@/lib/types";

export function hasRole(user: CurrentUser, role: InstitutionalRole): boolean {
  return user.roles.includes(role);
}

export function isFounder(user: CurrentUser): boolean {
  return hasRole(user, "FOUNDER");
}

export function isOperator(user: CurrentUser): boolean {
  return hasRole(user, "OPERATOR") || isFounder(user);
}

export function primaryRole(user: CurrentUser): InstitutionalRole {
  if (isFounder(user)) return "FOUNDER";
  if (hasRole(user, "OPERATOR")) return "OPERATOR";
  return "VIEWER";
}

export function roleLabel(role: InstitutionalRole): string {
  switch (role) {
    case "FOUNDER":
      return "Founder";
    case "OPERATOR":
      return "Operator";
    case "VIEWER":
      return "Viewer";
  }
}
