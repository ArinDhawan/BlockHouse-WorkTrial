import pandas as pd
import numpy as np
import itertools
import json
import matplotlib.pyplot as plt
from collections import defaultdict

def main():

    # Load data 
    df = pd.read_csv('l1_day.csv')

    # Sort and Preprocess : We only need one snapshot per venue per timestamp 
    df = df.sort_values(by=['ts_event']).drop_duplicates(subset=['ts_event', 'publisher_id'], keep='first')
    df = df[['ts_event', 'publisher_id', 'ask_px_00', 'ask_sz_00']].dropna()
    df['ask_px_00'] = df['ask_px_00'].astype(float)
    df['ask_sz_00'] = df['ask_sz_00'].astype(int)

    # Build per-timestamp market snapshots with best ask/size 
    snapshot_dict = defaultdict(list)
    for row in df.itertuples(index=False):
        snapshot_dict[row.ts_event].append({
            'publisher_id': row.publisher_id,
            'ask': row.ask_px_00,
            'ask_size': row.ask_sz_00,
            'fee': 0.002,
            'rebate': 0.001
        })

    ordered_snapshots = []
    for t in sorted(snapshot_dict.keys()):
        ordered_snapshots.append(snapshot_dict[t])

    # Grid search and Best parameter selection
    param_grid = list(itertools.product([0.01, 0.05], [0.01, 0.05], [0.001, 0.005]))
    results = []
    for lo, lu, theta in param_grid:
        cash, filled, _ = backtest(5000, lo, lu, theta, ordered_snapshots)
        avg_price = cash / filled if filled > 0 else float('inf')
        results.append({'params': {'lambda_over': lo, 'lambda_under': lu, 'theta_queue': theta},
                        'cash_spent': cash,'avg_price': avg_price,'filled': filled})

    best = min(results, key=lambda x: x['cash_spent'])

    # Final run with cumulative cost
    _, _, cumulative_cost = backtest(5000, best['params']['lambda_over'], best['params']['lambda_under'], best['params']['theta_queue'], ordered_snapshots)


    # Compute baselines
    best_ask_cash, best_ask_fill = best_ask_baseline(5000, ordered_snapshots)
    twap_cash, twap_fill = twap_baseline(5000, snapshot_dict)
    vwap_cash, vwap_fill = vwap_baseline(5000, ordered_snapshots)

    # JSON output
    res = {
        'best_params': best['params'],
        'optimized': {
            'cash_spent': best['cash_spent'],
            'avg_price': best['cash_spent'] / best['filled']
        },
        'best_ask': {
            'cash_spent': best_ask_cash,
            'avg_price': best_ask_cash / best_ask_fill
        },
        'twap': {
            'cash_spent': twap_cash,
            'avg_price': twap_cash / twap_fill
        },
        'vwap': {
            'cash_spent': vwap_cash,
            'avg_price': vwap_cash / vwap_fill
        },
        'savings_vs_baselines_bps': {
            'best_ask': bps_savings(best_ask_cash, best['cash_spent']),
            'twap': bps_savings(twap_cash, best['cash_spent']),
            'vwap': bps_savings(vwap_cash, best['cash_spent'])
        }
    }

    with open('best_params.json', 'w') as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))

    # (Optional) Cumulative-Cost Plot
    
    plt.figure(figsize=(10, 6))
    plt.plot(cumulative_cost)
    plt.xlabel('Snapshot Index')
    plt.ylabel('Cumulative Cash Spent')
    plt.title('Cumulative Cost Over Time')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig('results.png')


'''
Searches all feasible venue splits to minimize total cost 
using the static allocator from the paper.
'''

# As per the pseudocode 
def allocate(order_size, venues, lo, lu, theta):
    step = 100
    splits = [[]]
    for v in range(len(venues)):
        new_splits = []
        for alloc in splits:
            used = sum(alloc)
            max_v = min(order_size - used, venues[v]['ask_size'])
            for q in range(0, max_v + 1, step):
                new_splits.append(alloc + [q])
        splits = new_splits
    best_cost = float('inf')
    best_split = []
    for alloc in splits:
        if sum(alloc) != order_size:
            continue
        cost = compute_cost(alloc, venues, order_size, lo, lu, theta)
        if cost < best_cost:
            best_cost = cost
            best_split = alloc
    return best_split, best_cost

'''
Uses Cont & Kukanov's static cost model
including fees, rebates, under/overfill, and queue risk penalties.
'''

# As per the pseudocode 
def compute_cost(split, venues, order_size, lo, lu, theta):
    executed = 0
    cash_spent = 0
    for i in range(len(venues)):
        exe = min(split[i], venues[i]['ask_size'])
        executed += exe
        cash_spent += exe * (venues[i]['ask'] + venues[i]['fee'])
        rebate = max(split[i] - exe, 0) * venues[i]['rebate']
        cash_spent -= rebate
    underfill = max(order_size - executed, 0)
    overfill = max(executed - order_size, 0)
    return cash_spent + theta * (underfill + overfill) + lu * underfill + lo * overfill



def backtest(order_size, lo, lu, theta, snapshots):
    remaining = order_size
    cash_spent = 0
    total_filled = 0
    cumulative_cost = []
    for venues in snapshots:
        if remaining <= 0:
            break
        available_liquidity = sum(v['ask_size'] for v in venues)
        alloc_size = min(remaining, available_liquidity)
        if alloc_size == 0:
            cumulative_cost.append(cash_spent)
            continue
        alloc, _ = allocate(alloc_size, venues, lo, lu, theta)
        if not alloc:
            cumulative_cost.append(cash_spent)
            continue
        for i in range(len(alloc)):
            fill = min(alloc[i], venues[i]['ask_size'])
            cash_spent += fill * (venues[i]['ask'] + venues[i]['fee'])
            remaining -= fill
            total_filled += fill
        cumulative_cost.append(cash_spent)
    return cash_spent, total_filled, cumulative_cost

''' 
Baseline strategy that fills from the venue 
with the lowest ask price at each snapshot 
(naïve market order).
'''

def best_ask_baseline(order_size, snapshots):
    remaining = order_size
    cash_spent = 0
    for venues in snapshots:
        if remaining <= 0:
            break
        best_venue = min(venues, key=lambda v: v['ask'])
        fill = min(best_venue['ask_size'], remaining)
        cash_spent += fill * (best_venue['ask'] + best_venue['fee'])
        remaining -= fill
    return cash_spent, order_size - remaining

'''
Baseline that evenly splits order across fixed time intervals, 
executing at best price per chunk.
'''
def twap_baseline(order_size, snapshots, interval_secs=60):
    ts_keys = sorted(snapshots.keys())
    split_count = max(1, int(len(ts_keys) * 0.5 / interval_secs))
    chunk_size = len(snapshots) // split_count
    shares_per_chunk = order_size // split_count
    cash_spent, total_filled = 0, 0
    for i in range(split_count):
        venues = snapshots[ts_keys[i * chunk_size]]
        remaining = shares_per_chunk
        sorted_venues = sorted(venues, key=lambda v: v['ask'])
        for v in sorted_venues:
            fill = min(remaining, v['ask_size'])
            cash_spent += fill * (v['ask'] + v['fee'])
            total_filled += fill
            remaining -= fill
            if remaining <= 0:
                break
    return cash_spent, total_filled


'''
Baseline that fills in proportion to displayed size, 
weighted by venue ask prices (volume-weighted execution).
'''
def vwap_baseline(order_size, snapshots):
    px_qty = []
    for venues in snapshots:
        for v in venues:
            px_qty.append((v['ask'], v['ask_size']))
    px_qty = sorted(px_qty, key=lambda x: x[0])
    remaining = order_size
    cash_spent = 0
    for price, qty in px_qty:
        fill = min(qty, remaining)
        cash_spent += fill * (price + 0.002)
        remaining -= fill
        if remaining <= 0:
            break
    return cash_spent, order_size - remaining

'''
Computes savings over a baseline in basis points.
'''
def bps_savings(base, optimized):
    return 10000 * (base - optimized) / base

if __name__ == '__main__':
    main()