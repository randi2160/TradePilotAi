// All API calls go through the shared axios instance from useAuth
// which already has the JWT interceptor attached
import { api } from '../hooks/useAuth'

// Bot
export const getStatus        = ()               => api.get('/status').then(r => r.data)
export const startBot         = (mode, tm)       => api.post('/bot/start', { mode, trading_mode: tm }).then(r => r.data)
export const stopBot          = ()               => api.post('/bot/stop').then(r => r.data)
export const closeAll         = ()               => api.post('/positions/close-all').then(r => r.data)
export const retrain          = ()               => api.post('/train').then(r => r.data)
export const setTradingMode   = (m)              => api.put('/bot/trading-mode', { trading_mode: m }).then(r => r.data)
export const setWatchlistMode = (d)              => api.put('/bot/watchlist-mode', { dynamic: d }).then(r => r.data)

// Data
export const getTrades        = ()               => api.get('/trades').then(r => r.data)
export const getSignals       = ()               => api.get('/signals').then(r => r.data)
export const getPositions     = ()               => api.get('/positions').then(r => r.data)
export const getOrders        = ()               => api.get('/orders').then(r => r.data)
export const getChart         = (sym, tf)        => api.get(`/chart/${sym}?timeframe=${tf}&limit=200`).then(r => r.data)
export const getEquityHistory = (hours = 24)     => api.get(`/equity-history?hours=${hours}`).then(r => r.data)

// Manual trades
export const placeManualTrade = (body)           => api.post('/trades/manual', body).then(r => r.data)
export const closeManualTrade = (sym)            => api.post(`/trades/manual/close/${sym}`).then(r => r.data)

// Manual mode
export const getPendingTrades = ()               => api.get('/pending-trades').then(r => r.data)
export const approveTrade     = (sym)            => api.post(`/pending-trades/${sym}/approve`).then(r => r.data)
export const rejectTrade      = (sym)            => api.post(`/pending-trades/${sym}/reject`).then(r => r.data)

// AI
export const getAdvice        = (force = false)  => api.get(`/ai/advice?force=${force}`).then(r => r.data)
export const suggestWatchlist = ()               => api.get('/ai/watchlist-suggest').then(r => r.data)
export const getUnusualVolume = ()               => api.get('/ai/unusual-volume').then(r => r.data)

// News
export const getMarketNews    = (limit = 20)     => api.get(`/news/market?limit=${limit}`).then(r => r.data)
export const getSymbolNews    = (sym, limit)     => api.get(`/news/${sym}?limit=${limit}`).then(r => r.data)
export const getSentiment     = (sym)            => api.get(`/sentiment/${sym}`).then(r => r.data)
export const scanSentiment    = ()               => api.get('/sentiment/watchlist/all').then(r => r.data)

// Scanner
export const runScan          = ()               => api.get('/scanner/scan').then(r => r.data)
export const getGainers       = (n = 10)         => api.get(`/scanner/gainers?n=${n}`).then(r => r.data)
export const getLosers        = (n = 10)         => api.get(`/scanner/losers?n=${n}`).then(r => r.data)
export const getMostActive    = (n = 10)         => api.get(`/scanner/active?n=${n}`).then(r => r.data)

// Analytics
export const getPerformance   = (days = 30)      => api.get(`/analytics/performance?days=${days}`).then(r => r.data)
export const getTodayStats    = ()               => api.get('/analytics/today').then(r => r.data)
export const getPDTStatus     = ()               => api.get('/analytics/pdt').then(r => r.data)
export const runBacktest      = (sym, limit)     => api.post(`/analytics/backtest?symbol=${sym}&limit=${limit}`).then(r => r.data)

// Dashboard — daily P&L + compound tracking + Alpaca snapshot
export const getDashboardToday    = ()            => api.get('/dashboard/today').then(r => r.data)
export const getDashboardHistory  = (days = 30)   => api.get(`/dashboard/history?days=${days}`).then(r => r.data)
export const getAlpacaSnapshot    = ()            => api.get('/dashboard/alpaca-snapshot').then(r => r.data)
export const forceDailySnapshot   = ()            => api.post('/dashboard/snapshot').then(r => r.data)
export const getPositionsDetail   = ()            => api.get('/dashboard/positions-detail').then(r => r.data)

// Settings
export const getSettings      = ()               => api.get('/settings').then(r => r.data)
export const updateCapital    = (capital)        => api.put('/settings/capital', { capital }).then(r => r.data)
export const updateTargets    = (min, max, loss) =>
  api.put('/settings/targets', { daily_target_min: min, daily_target_max: max, max_daily_loss: loss }).then(r => r.data)

// Watchlist
export const getWatchlist     = ()               => api.get('/watchlist').then(r => r.data)
export const setWatchlist     = (symbols)        => api.put('/watchlist', { symbols }).then(r => r.data)
export const addSymbol        = (symbol)         => api.post('/watchlist/add', { symbol }).then(r => r.data)
export const removeSymbol     = (symbol)         => api.delete(`/watchlist/${symbol}`).then(r => r.data)
