"use client";

import { useState, useTransition } from "react";

import {
  clearSymbolPracticeAction,
  refreshRecentPricesAction,
} from "@/lib/actions/paper";

export function ClearPaperSymbolButton({
  portfolioId,
  symbol,
}: {
  portfolioId: string;
  symbol: string;
}) {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  return (
    <div className="clear-practice-actions">
      <button
        type="button"
        className="btn secondary"
        disabled={pending}
        onClick={() => {
          if (
            !window.confirm(
              `Remove the paper ${symbol} trade and its P&L history so Argus can restart with real prices? Paper cash invested in this trade will be restored. This does not affect live trading.`,
            )
          ) {
            return;
          }
          startTransition(async () => {
            const cleared = await clearSymbolPracticeAction({
              portfolioId,
              symbol,
            });
            if (!cleared.ok) {
              setMessage(cleared.message);
              return;
            }
            const refreshed = await refreshRecentPricesAction();
            setMessage(
              `${cleared.message} ${refreshed.message}`,
            );
          });
        }}
      >
        Remove paper {symbol} & refresh prices
      </button>
      {message ? <p className="muted-note">{message}</p> : null}
    </div>
  );
}
