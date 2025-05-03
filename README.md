# BlockHouse Work Trial Submission - Arin Dhawan 

## Smart Order Router – Cont & Kukanov Backtest

This my submission for the BlockHouse Work Trial. First off all, I want to acknoledge the team @BlockHouse. This trial was majorly based on Cont & Kukanov's paper *“Optimal Order Placement in Limit Order Markets.”*, which implements a a backtest for the static Smart Order Routing algorithm (2013). The script evaluates an optimal split of a 5,000-share buy order across multiple venues and benchmarks its performance against different strategies. 

## 🔍 Approach

The allocator minimizes expected execution cost by considering:
- Venue ask prices and displayed sizes
- Per-share transaction costs (fees/rebates)
- Risk penalties:
  - `lambda_under`: underfill penalty
  - `lambda_over`: overfill penalty
  - `theta_queue`: queue risk proxy

At each Level-1 snapshot, the static allocator searches over all feasible splits (in 100-share increments) to find the allocation that minimizes total cost. The script continues until the full 5,000-share order is filled or the data ends.

The following strategies are benchmarked:
- **Best Ask**: Naïve fill from the venue with the lowest ask.
- **TWAP**: Time-weighted average price using 60-second buckets.
- **VWAP**: Volume-weighted average price based on displayed ask sizes.

## ⚙️ Parameter Grid

A brute-force grid search is performed over the following ranges:

- `lambda_over`: [0.01, 0.05]
- `lambda_under`: [0.01, 0.05]
- `theta_queue`: [0.001, 0.005]

The best-performing parameter set (lowest total cost) is selected.

## 📊 Output

The script prints a single JSON object to stdout and saves it to `best_params.json`, containing:
- Best parameter set
- Cash spent and average fill price (optimized and baseline strategies)
- Savings over each baseline in basis points
- Optional cost plot saved as `results.png`

## 💡 Future Improvement: Fill Realism

 **Adverse Selection Penalty via Short-Term Price Drift**
   - Track recent price momentum for each venue.
   - Penalize fills from venues with negative short-term drift (for buys), which indicates potential toxic flow.
   - Adds realism to passive fills that get hit just before prices fall.


