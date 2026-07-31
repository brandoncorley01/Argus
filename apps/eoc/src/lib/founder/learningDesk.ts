/** Canonical Founder paper book — mirrors anticipated live starting capital. */
export const FOUNDER_LEARNING_DESK_NAME = "Founder Learning Desk";
export const LEARNING_STARTING_CASH = 300;

export function pickPrimaryPortfolio<T extends { name: string }>(
  portfolios: T[] | null | undefined,
): T | null {
  if (!portfolios?.length) return null;
  return (
    portfolios.find((p) => p.name === FOUNDER_LEARNING_DESK_NAME) ??
    portfolios[0] ??
    null
  );
}
