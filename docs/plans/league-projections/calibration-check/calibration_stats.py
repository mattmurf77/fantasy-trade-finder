"""Pure statistics for the playoff-odds calibration check. Standard library only.

A *panel* is a list of leagues; a league is a list of teams; a team is a list of
weekly projection errors (actual minus projected), the same weeks for every
team in the league. Nothing here reads files, the network or the clock.
"""
from __future__ import annotations

import math


def phi(z):
    """Standard normal CDF."""
    return .5 * math.erfc(-z / math.sqrt(2))


def win_probability(projected_a, projected_b, sd):
    """P(team a outscores team b) when both scores are independent Normal(projection, sd)."""
    if sd <= 0:
        return 1. if projected_a > projected_b else 0. if projected_a < projected_b else .5
    return phi((projected_a - projected_b) / (sd * math.sqrt(2)))


def _check(panel):
    for league in panel:
        if len(league) < 2 or len({len(team) for team in league}) != 1 or len(league[0]) < 2:
            raise ValueError("each league needs at least two teams with the same two or more weeks")


def relative(panel):
    """Remove each league-week's mean: what is left moves standings."""
    out = []
    for league in panel:
        weeks = len(league[0])
        means = [sum(team[w] for team in league) / len(league) for w in range(weeks)]
        out.append([[team[w] - means[w] for w in range(weeks)] for team in league])
    return out


def variance_components(panel):
    """Method-of-moments two-way decomposition, pooled over leagues.

    error = league mean + league-week shock + team effect + residual. Within a
    league the design is balanced (team x week, one error per cell), so the
    ANOVA mean squares give unbiased variance components:
      E[MS_resid] = s_resid^2
      E[MS_team]  = s_resid^2 + weeks * s_team^2
      E[MS_week]  = s_resid^2 + teams * s_week^2
    Returns variances (points squared); negative estimates are kept (they are
    noise around zero) and floored only in the derived `tau`.
    """
    _check(panel)
    ss_t = ss_w = ss_r = df_t = df_w = df_r = 0.
    weight_t = weight_w = 0.
    for league in panel:
        teams, weeks = len(league), len(league[0])
        grand = sum(map(sum, league)) / (teams * weeks)
        team_means = [sum(team) / weeks for team in league]
        week_means = [sum(team[w] for team in league) / teams for w in range(weeks)]
        ss_t += weeks * sum((m - grand) ** 2 for m in team_means)
        ss_w += teams * sum((m - grand) ** 2 for m in week_means)
        ss_r += sum((league[t][w] - team_means[t] - week_means[w] + grand) ** 2
                    for t in range(teams) for w in range(weeks))
        df_t += teams - 1
        df_w += weeks - 1
        df_r += (teams - 1) * (weeks - 1)
        weight_t += (teams - 1) * weeks
        weight_w += (weeks - 1) * teams
    ms_r = ss_r / df_r
    team = (ss_t - df_t * ms_r) / weight_t
    week = (ss_w - df_w * ms_r) / weight_w
    relative_total = team + ms_r
    return {"team": team, "league_week": week, "residual": ms_r,
            "tau": math.sqrt(max(team, 0.)),
            "team_share_of_relative": team / relative_total if relative_total > 0 else 0.,
            "team_share_of_total": team / (team + max(week, 0.) + ms_r)}


def lag_correlation(panel, lag):
    """Pooled correlation of a team's relative error with its own error `lag` weeks later."""
    xs, ys = [], []
    for league in relative(panel):
        for team in league:
            for w in range(len(team) - lag):
                xs.append(team[w])
                ys.append(team[w + lag])
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy)


def sum_variance_ratio(panel, window):
    """Observed variance of a team's error summed over `window` consecutive weeks,
    divided by what independence implies (window x weekly variance).

    Relative errors (league-week mean removed), every sliding window. Under
    independence the ratio is 1; with a persistent share rho it is about
    1 + (window - 1) * rho.
    """
    rel = relative(panel)
    single = [e for league in rel for team in league for e in team]
    weekly = sum(e * e for e in single) / len(single)
    sums = [sum(team[s:s + window]) for league in rel for team in league
            for s in range(len(team) - window + 1)]
    observed = sum(x * x for x in sums) / len(sums)
    return {"ratio": observed / (window * weekly), "observed_sd": math.sqrt(observed),
            "independent_sd": math.sqrt(window * weekly), "weekly_sd": math.sqrt(weekly), "windows": len(sums)}


def win_overdispersion(games, window):
    """games: list of teams; a team is a list of weeks; a week is a list of
    (result, p) pairs (result 1 win, 0 loss, .5 tie; p the pregame win probability).

    For every sliding window: D = wins - sum p, V = sum p(1-p). Returns
    sum D^2 / sum V, which is 1 when games are independent and p is right.
    """
    num = den = 0.
    count = 0
    for team in games:
        for s in range(len(team) - window + 1):
            block = [g for week in team[s:s + window] for g in week]
            if not block:
                continue
            num += (sum(r for r, _ in block) - sum(p for _, p in block)) ** 2
            den += sum(p * (1 - p) for _, p in block)
            count += 1
    return {"ratio": num / den if den else float("nan"), "windows": count}


def semivariogram(panel, max_lag, weeks=None):
    """Half the mean squared change of a team's relative series over `lag` weeks.

    Applied to projected totals: a flat curve means a team's projected strength
    only wobbles week to week; a curve rising with the lag means it drifts, so a
    projection made several weeks ahead is less certain than one made the week
    before. `weeks` restricts both ends of each pair to those week indexes.
    """
    rel = relative(panel)
    allowed = set(range(len(rel[0][0]))) if weeks is None else set(weeks)
    out = {}
    for lag in range(1, max_lag + 1):
        sq = [(team[w + lag] - team[w]) ** 2 for league in rel for team in league
              for w in range(len(team) - lag) if w in allowed and w + lag in allowed]
        if sq:
            out[lag] = sum(sq) / len(sq) / 2
    return out


def drift_step_variance(gamma):
    """Least-squares slope of the semivariogram on the lag, times two: the
    per-week variance of a random-walk drift (the flat part is week-to-week wobble)."""
    lags = sorted(gamma)
    mx = sum(lags) / len(lags)
    my = sum(gamma[h] for h in lags) / len(lags)
    slope = sum((h - mx) * (gamma[h] - my) for h in lags) / sum((h - mx) ** 2 for h in lags)
    return 2 * slope


def shuffle_within_team(panel, rng):
    """Permute each team's weeks: keeps every team's total, breaks week order."""
    out = []
    for league in panel:
        new = []
        for team in league:
            copy = team[:]
            rng.shuffle(copy)
            new.append(copy)
        out.append(new)
    return out


def shuffle_across_teams(panel, rng):
    """Within each league-week, hand the errors to teams at random: keeps every
    league-week shock, breaks any link between a team and its errors."""
    out = []
    for league in panel:
        weeks = len(league[0])
        columns = []
        for w in range(weeks):
            column = [team[w] for team in league]
            rng.shuffle(column)
            columns.append(column)
        out.append([[columns[w][t] for w in range(weeks)] for t in range(len(league))])
    return out


def resample_teams(panel, rng):
    """Cluster bootstrap: draw whole teams with replacement inside each league."""
    return [[league[rng.randrange(len(league))] for _ in league] for league in panel]


def interval(values, level=.95):
    ordered = sorted(v for v in values if v == v)
    if not ordered:
        return [None, None]
    low = ordered[int(math.floor((1 - level) / 2 * (len(ordered) - 1)))]
    high = ordered[int(math.ceil((1 + level) / 2 * (len(ordered) - 1)))]
    return [low, high]


def synthetic_panel(rng, leagues, teams, weeks, tau, residual_sd, week_sd=0.):
    """Errors with a known persistent team SD `tau` (for tests and checks)."""
    panel = []
    for _ in range(leagues):
        shocks = [rng.gauss(0, week_sd) for _ in range(weeks)]
        league = []
        for _ in range(teams):
            effect = rng.gauss(0, tau)
            league.append([effect + shocks[w] + rng.gauss(0, residual_sd) for w in range(weeks)])
        panel.append(league)
    return panel


def synthetic_games(rng, teams, weeks, tau, sd):
    """Head-to-head games whose true scores carry a persistent team draw of SD
    tau that the stated probabilities ignore. tau = 0 makes p exactly right."""
    weekly = math.sqrt(max(sd * sd - tau * tau, 0.))
    effects = [rng.gauss(0, tau) for _ in range(teams)]
    out = [[[] for _ in range(weeks)] for _ in range(teams)]
    for w in range(weeks):
        order = list(range(teams))
        rng.shuffle(order)
        means = [rng.gauss(120, 15) for _ in range(teams)]
        for a, b in zip(order[::2], order[1::2]):
            p = win_probability(means[a], means[b], sd)
            sa = means[a] + effects[a] + rng.gauss(0, weekly)
            sb = means[b] + effects[b] + rng.gauss(0, weekly)
            r = 1. if sa > sb else 0.
            out[a][w].append((r, p))
            out[b][w].append((1 - r, 1 - p))
    return out


__all__ = ["phi", "win_probability", "relative", "variance_components", "lag_correlation",
           "sum_variance_ratio", "win_overdispersion", "semivariogram", "drift_step_variance", "shuffle_within_team", "shuffle_across_teams",
           "resample_teams", "interval", "synthetic_panel", "synthetic_games"]
