"""
Comprehensive Dual-Bookmaker Analysis
Compares V2 calibrated fair odds against BOTH Sportybet and Bet9ja actual 1UP odds.
"""

import sqlite3
import pandas as pd
import numpy as np

# Database connection
conn = sqlite3.connect('data/datas.db')

# Query complete V2 results with both bookmakers
query = """
SELECT
    ec.sportradar_id,
    ec.engine_name,
    ec.bookmaker,
    ec.lambda_home,
    ec.lambda_away,
    ec.lambda_total,
    ec.p_home_1up,
    ec.p_away_1up,
    ec.fair_home,
    ec.fair_away,
    ec.fair_draw,
    ec.actual_sporty_home,
    ec.actual_sporty_draw,
    ec.actual_sporty_away,
    ec.actual_bet9ja_home,
    ec.actual_bet9ja_draw,
    ec.actual_bet9ja_away,
    e.home_team,
    e.away_team,
    e.start_time
FROM engine_calculations ec
JOIN events e ON ec.sportradar_id = e.sportradar_id
WHERE ec.engine_name = 'Poisson-Calibrated'
  AND ec.bookmaker = 'pawa'
ORDER BY e.start_time DESC, ec.sportradar_id
"""

df = pd.read_sql_query(query, conn)
conn.close()

print(f"\n{'='*80}")
print(f"DUAL-BOOKMAKER ANALYSIS: V2 Calibrated Poisson Engine")
print(f"{'='*80}")
print(f"Total matches: {len(df)}")
print(f"Date range: {df['start_time'].min()} to {df['start_time'].max()}")

# Helper: De-vig two-way market
def devig_two_way(odds_a: float, odds_b: float):
    """Convert odds to fair probabilities using proportional devig"""
    if pd.isna(odds_a) or pd.isna(odds_b):
        return np.nan, np.nan
    p_a = 1 / odds_a
    p_b = 1 / odds_b
    total = p_a + p_b
    fair_a = odds_a * total
    fair_b = odds_b * total
    return fair_a, fair_b

# Calculate fair odds from both bookmakers
def calc_fair(row, bookie_prefix):
    """Calculate fair odds for a bookmaker (sporty or bet9ja)"""
    h_col = f'actual_{bookie_prefix}_home'
    a_col = f'actual_{bookie_prefix}_away'

    if pd.isna(row[h_col]) or pd.isna(row[a_col]):
        return pd.Series([np.nan, np.nan])

    fair_h, fair_a = devig_two_way(row[h_col], row[a_col])
    return pd.Series([fair_h, fair_a])

# Calculate Sportybet fair odds
df[['sporty_fair_h', 'sporty_fair_a']] = df.apply(
    lambda r: calc_fair(r, 'sporty'), axis=1
)

# Calculate Bet9ja fair odds
df[['bet9ja_fair_h', 'bet9ja_fair_a']] = df.apply(
    lambda r: calc_fair(r, 'bet9ja'), axis=1
)

# Calculate errors vs Sportybet
df['error_sporty_h'] = df['fair_home'] - df['sporty_fair_h']
df['error_sporty_a'] = df['fair_away'] - df['sporty_fair_a']
df['abs_error_sporty_h'] = df['error_sporty_h'].abs()
df['abs_error_sporty_a'] = df['error_sporty_a'].abs()

# Calculate errors vs Bet9ja
df['error_bet9ja_h'] = df['fair_home'] - df['bet9ja_fair_h']
df['error_bet9ja_a'] = df['fair_away'] - df['bet9ja_fair_a']
df['abs_error_bet9ja_h'] = df['error_bet9ja_h'].abs()
df['abs_error_bet9ja_a'] = df['error_bet9ja_a'].abs()

# Calculate lambda ratio
df['lambda_ratio'] = df[['lambda_home', 'lambda_away']].max(axis=1) / df[['lambda_home', 'lambda_away']].min(axis=1)

# Label underdog/favorite
df['home_is_underdog'] = df['lambda_home'] < df['lambda_away']

# Validate draw odds consistency
print(f"\n{'='*80}")
print("DRAW ODDS CONSISTENCY CHECK")
print(f"{'='*80}")

valid_draws = df[df['actual_sporty_draw'].notna() & df['actual_bet9ja_draw'].notna()]
draw_diff = (valid_draws['actual_sporty_draw'] - valid_draws['actual_bet9ja_draw']).abs()
print(f"Matches with both draw odds: {len(valid_draws)}")
print(f"Mean absolute difference: {draw_diff.mean():.4f}")
print(f"Max difference: {draw_diff.max():.4f}")
print(f"Identical draws: {(draw_diff < 0.01).sum()} / {len(valid_draws)} ({(draw_diff < 0.01).sum()/len(valid_draws)*100:.1f}%)")

if draw_diff.max() > 0.05:
    print("\n[!] WARNING: Some draw odds differ by >0.05 between bookmakers!")
    outliers = valid_draws[draw_diff > 0.05][['home_team', 'away_team', 'actual_sporty_draw', 'actual_bet9ja_draw']]
    print(outliers.head(10))
else:
    print("[OK] Draw odds are consistent between bookmakers (as expected)")

# Overall comparison
print(f"\n{'='*80}")
print("OVERALL PERFORMANCE: SPORTYBET vs BET9JA")
print(f"{'='*80}")

sporty_valid = df[df['sporty_fair_h'].notna()]
bet9ja_valid = df[df['bet9ja_fair_h'].notna()]

print(f"\nSportybet data available: {len(sporty_valid)} matches")
print(f"Bet9ja data available: {len(bet9ja_valid)} matches")

# Sportybet metrics
print(f"\n{'VS SPORTYBET':-^80}")
print(f"{'Home Side':30} MAE: {sporty_valid['abs_error_sporty_h'].mean():.4f}  Bias: {sporty_valid['error_sporty_h'].mean():+.4f}")
print(f"{'Away Side':30} MAE: {sporty_valid['abs_error_sporty_a'].mean():.4f}  Bias: {sporty_valid['error_sporty_a'].mean():+.4f}")

# Bet9ja metrics
print(f"\n{'VS BET9JA':-^80}")
print(f"{'Home Side':30} MAE: {bet9ja_valid['abs_error_bet9ja_h'].mean():.4f}  Bias: {bet9ja_valid['error_bet9ja_h'].mean():+.4f}")
print(f"{'Away Side':30} MAE: {bet9ja_valid['abs_error_bet9ja_a'].mean():.4f}  Bias: {bet9ja_valid['error_bet9ja_a'].mean():+.4f}")

# Underdog/Favorite breakdown
print(f"\n{'='*80}")
print("UNDERDOG vs FAVORITE BREAKDOWN")
print(f"{'='*80}")

def calc_underdog_metrics(data, bookie):
    """Calculate underdog/favorite metrics for a bookmaker"""
    # Home is underdog
    home_under = data[data['home_is_underdog']]
    underdog_mae_h = home_under[f'abs_error_{bookie}_h'].mean()
    favorite_mae_h = home_under[f'abs_error_{bookie}_a'].mean()
    underdog_bias_h = home_under[f'error_{bookie}_h'].mean()
    favorite_bias_h = home_under[f'error_{bookie}_a'].mean()

    # Away is underdog
    away_under = data[~data['home_is_underdog']]
    underdog_mae_a = away_under[f'abs_error_{bookie}_a'].mean()
    favorite_mae_a = away_under[f'abs_error_{bookie}_h'].mean()
    underdog_bias_a = away_under[f'error_{bookie}_a'].mean()
    favorite_bias_a = away_under[f'error_{bookie}_h'].mean()

    # Combined
    underdog_mae = (underdog_mae_h * len(home_under) + underdog_mae_a * len(away_under)) / len(data)
    favorite_mae = (favorite_mae_h * len(home_under) + favorite_mae_a * len(away_under)) / len(data)
    underdog_bias = (underdog_bias_h * len(home_under) + underdog_bias_a * len(away_under)) / len(data)
    favorite_bias = (favorite_bias_h * len(home_under) + favorite_bias_a * len(away_under)) / len(data)

    return underdog_mae, favorite_mae, underdog_bias, favorite_bias

# Sportybet underdog/favorite
s_u_mae, s_f_mae, s_u_bias, s_f_bias = calc_underdog_metrics(sporty_valid, 'sporty')
print(f"\n{'VS SPORTYBET':-^80}")
print(f"{'Underdog MAE':30} {s_u_mae:.4f}")
print(f"{'Favorite MAE':30} {s_f_mae:.4f}")
print(f"{'Underdog Bias':30} {s_u_bias:+.4f}")
print(f"{'Favorite Bias':30} {s_f_bias:+.4f}")

# Bet9ja underdog/favorite
b_u_mae, b_f_mae, b_u_bias, b_f_bias = calc_underdog_metrics(bet9ja_valid, 'bet9ja')
print(f"\n{'VS BET9JA':-^80}")
print(f"{'Underdog MAE':30} {b_u_mae:.4f}")
print(f"{'Favorite MAE':30} {b_f_mae:.4f}")
print(f"{'Underdog Bias':30} {b_u_bias:+.4f}")
print(f"{'Favorite Bias':30} {b_f_bias:+.4f}")

# Lambda ratio breakdown
print(f"\n{'='*80}")
print("BY LAMBDA RATIO (TEAM IMBALANCE)")
print(f"{'='*80}")

ratio_bins = [
    (0, 1.15, "Balanced <1.15"),
    (1.15, 1.5, "Slight 1.15-1.5"),
    (1.5, 2.0, "Moderate 1.5-2.0"),
    (2.0, 3.0, "High 2.0-3.0"),
    (3.0, 10.0, "Extreme >3.0"),
]

for min_r, max_r, label in ratio_bins:
    bin_data = df[(df['lambda_ratio'] >= min_r) & (df['lambda_ratio'] < max_r)]

    if len(bin_data) == 0:
        continue

    print(f"\n{label} ({len(bin_data)} matches)")
    print("-" * 80)

    # Sportybet metrics for this bin
    sporty_bin = bin_data[bin_data['sporty_fair_h'].notna()]
    if len(sporty_bin) > 0:
        s_u_mae, s_f_mae, s_u_bias, s_f_bias = calc_underdog_metrics(sporty_bin, 'sporty')
        print(f"  {'VS SPORTYBET':40} Under MAE: {s_u_mae:.4f}  Fav MAE: {s_f_mae:.4f}")
        print(f"  {'':40} Under Bias: {s_u_bias:+.4f}  Fav Bias: {s_f_bias:+.4f}")

    # Bet9ja metrics for this bin
    bet9ja_bin = bin_data[bin_data['bet9ja_fair_h'].notna()]
    if len(bet9ja_bin) > 0:
        b_u_mae, b_f_mae, b_u_bias, b_f_bias = calc_underdog_metrics(bet9ja_bin, 'bet9ja')
        print(f"  {'VS BET9JA':40} Under MAE: {b_u_mae:.4f}  Fav MAE: {b_f_mae:.4f}")
        print(f"  {'':40} Under Bias: {b_u_bias:+.4f}  Fav Bias: {b_f_bias:+.4f}")

# Which bookmaker are we closer to?
print(f"\n{'='*80}")
print("WHICH BOOKMAKER DO WE MATCH BETTER?")
print(f"{'='*80}")

both_valid = df[df['sporty_fair_h'].notna() & df['bet9ja_fair_h'].notna()]
print(f"\nMatches with both bookmakers: {len(both_valid)}")

if len(both_valid) > 0:
    # Overall MAE comparison
    sporty_overall_mae = (both_valid['abs_error_sporty_h'].mean() + both_valid['abs_error_sporty_a'].mean()) / 2
    bet9ja_overall_mae = (both_valid['abs_error_bet9ja_h'].mean() + both_valid['abs_error_bet9ja_a'].mean()) / 2

    print(f"\nOverall MAE (average of home + away):")
    print(f"  Sportybet: {sporty_overall_mae:.4f}")
    print(f"  Bet9ja:    {bet9ja_overall_mae:.4f}")

    if sporty_overall_mae < bet9ja_overall_mae:
        diff_pct = ((bet9ja_overall_mae - sporty_overall_mae) / sporty_overall_mae) * 100
        print(f"\n[OK] We are {diff_pct:.1f}% CLOSER to Sportybet than Bet9ja")
    else:
        diff_pct = ((sporty_overall_mae - bet9ja_overall_mae) / bet9ja_overall_mae) * 100
        print(f"\n[OK] We are {diff_pct:.1f}% CLOSER to Bet9ja than Sportybet")

    # Match-by-match comparison
    both_valid['closer_to_sporty'] = (
        (both_valid['abs_error_sporty_h'] + both_valid['abs_error_sporty_a']) <
        (both_valid['abs_error_bet9ja_h'] + both_valid['abs_error_bet9ja_a'])
    )

    sporty_wins = both_valid['closer_to_sporty'].sum()
    bet9ja_wins = len(both_valid) - sporty_wins

    print(f"\nMatch-by-match winner:")
    print(f"  Closer to Sportybet: {sporty_wins} matches ({sporty_wins/len(both_valid)*100:.1f}%)")
    print(f"  Closer to Bet9ja:    {bet9ja_wins} matches ({bet9ja_wins/len(both_valid)*100:.1f}%)")

# Top errors for each bookmaker
print(f"\n{'='*80}")
print("TOP 10 WORST PREDICTIONS")
print(f"{'='*80}")

print(f"\n{'VS SPORTYBET (worst underdog errors)':-^80}")
sporty_worst = sporty_valid.copy()
sporty_worst['underdog_error'] = sporty_worst.apply(
    lambda r: r['error_sporty_h'] if r['home_is_underdog'] else r['error_sporty_a'],
    axis=1
)
sporty_worst = sporty_worst.nlargest(10, 'underdog_error')
for _, row in sporty_worst.iterrows():
    side = 'Home' if row['home_is_underdog'] else 'Away'
    print(f"  {row['home_team']:25} vs {row['away_team']:25} | {side:4} | Error: {row['underdog_error']:+.3f} | Ratio: {row['lambda_ratio']:.2f}")

print(f"\n{'VS BET9JA (worst underdog errors)':-^80}")
bet9ja_worst = bet9ja_valid.copy()
bet9ja_worst['underdog_error'] = bet9ja_worst.apply(
    lambda r: r['error_bet9ja_h'] if r['home_is_underdog'] else r['error_bet9ja_a'],
    axis=1
)
bet9ja_worst = bet9ja_worst.nlargest(10, 'underdog_error')
for _, row in bet9ja_worst.iterrows():
    side = 'Home' if row['home_is_underdog'] else 'Away'
    print(f"  {row['home_team']:25} vs {row['away_team']:25} | {side:4} | Error: {row['underdog_error']:+.3f} | Ratio: {row['lambda_ratio']:.2f}")

# Recommendation
print(f"\n{'='*80}")
print("RECOMMENDATIONS")
print(f"{'='*80}")

if len(both_valid) > 0:
    if abs(sporty_overall_mae - bet9ja_overall_mae) < 0.01:
        print("\n[OK] Performance is nearly IDENTICAL between bookmakers")
        print("   -> Single unified calibration is appropriate")
    elif sporty_overall_mae < bet9ja_overall_mae * 0.9:
        print("\n[!] Significantly better match with Sportybet")
        print("   -> Consider bookmaker-specific calibrations")
        print("   -> Or optimize primarily for Sportybet")
    elif bet9ja_overall_mae < sporty_overall_mae * 0.9:
        print("\n[!] Significantly better match with Bet9ja")
        print("   -> Consider bookmaker-specific calibrations")
        print("   -> Or optimize primarily for Bet9ja")
    else:
        print("\n[OK] Performance is reasonably similar between bookmakers")
        print("   -> Single unified calibration is acceptable")

print(f"\n{'='*80}")
print("Analysis complete!")
print(f"{'='*80}\n")
