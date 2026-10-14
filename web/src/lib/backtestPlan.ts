// Leaderboard backtest sizing in plain words (audit finding C-07).
//
// The page sends min_train_size = max(2 x season, n - windows x horizon - 1).
// With 24 monthly points, season 12 and horizon 6 that is 24, and the engine
// needs min_train_size + horizon = 30 points, so the run failed with a raw
// Python ValueError. This computes the same numbers BEFORE submitting and,
// when the history is too short, says why and which settings would work.

export interface BacktestPlanOk {
  ok: true;
  minTrainSize: number;
}
export interface BacktestPlanShort {
  ok: false;
  message: string;
}

/** Same formula the page has always sent (unchanged, so golden runs match). */
export function minTrainSize(n: number, season: number, horizon: number, windows: number): number {
  return Math.max(season * 2, n - windows * horizon - 1);
}

export function planBacktest(
  n: number,
  season: number,
  horizon: number,
  windows: number,
): BacktestPlanOk | BacktestPlanShort {
  const train = minTrainSize(n, season, horizon, windows);
  if (n >= train + horizon) return { ok: true, minTrainSize: train };

  const needed = train + horizon;
  const hints: string[] = [];
  // Largest horizon that fits with this season: n - 2 x season.
  const maxHorizon = n - season * 2;
  if (maxHorizon >= 1) hints.push(`a horizon of ${maxHorizon} or less`);
  // Largest season that fits with this horizon: floor((n - horizon) / 2).
  const maxSeason = Math.floor((n - horizon) / 2);
  if (maxSeason >= 2 && maxSeason < season) hints.push(`a season length of ${maxSeason} or less`);
  hints.push(`at least ${needed} periods of history`);
  return {
    ok: false,
    message:
      `Your history has ${n} periods. With a season length of ${season} and a horizon of ${horizon}, ` +
      `the leaderboard needs at least ${needed}: two full seasons (${season * 2}) to train each ` +
      `method on, plus ${horizon} to test its forecast against. ` +
      `Try ${hints.join(", or ")}.`,
  };
}
