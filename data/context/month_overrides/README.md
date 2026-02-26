# Month Override Contract

Create optional files at:
- `data/context/month_overrides/<period>.json`

Example:

```json
{
  "global_delta": -3,
  "score_adjustments": [
    {
      "dimension": "forecast_reliability",
      "delta": -8,
      "reason": "Budget challenge period"
    }
  ],
  "force_clarifier": "This month includes strategic one-offs. Confirm if I should normalize them out of score commentary."
}
```

