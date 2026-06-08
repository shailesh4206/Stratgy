# TODO
- [x] Update Binance Open Interest history endpoint handling in `traderoom_bot/analysis/funding_rate.py`
  - [x] Try `https://fapi.binance.com/futures/data/openInterestHist` first
  - [x] Add ordered fallbacks for other known namespaces/routes if needed
  - [x] Preserve existing business logic for trend calculation
  - [x] Make OI history failure non-blocking (do not prevent trading)
- [x] Smoke test / run bot and confirm no more `ctx=funding/openInterestHist* status=404` in logs



