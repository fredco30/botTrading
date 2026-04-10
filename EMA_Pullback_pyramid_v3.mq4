//+------------------------------------------------------------------+
//|                                 EMA_Pullback_pyramid_v3.mq4      |
//|            EMA Pullback Trend Following + Anti-Martingale Pyramid |
//|                    H1 Trend + M15 Pullback Entry                   |
//|            + Reverse Trade on L0 SL + Martingale Hedge L1/L2      |
//|                                                                    |
//|  v2 features: reverse trade on L0 SL (opposite direction)         |
//|  v3 features: martingale hedge on L1/L2 at 75% of SL              |
//|    When L1/L2 reaches 75% of SL, open opposite direction trade    |
//|    TP = mother SL, SL = mother entry, lot = configurable mult     |
//+------------------------------------------------------------------+
#property copyright "EMA Pullback Pyramid EA v3.00"
#property link      ""
#property version   "2.00"
#property strict

//+------------------------------------------------------------------+
//| INPUTS                                                            |
//+------------------------------------------------------------------+
// EURUSD only — tested pyramid on GBPUSD (L0 PF 0.87), USDCHF (PF 1.01), not viable.
// Pyramid requires baseline PF > 2.0 to amplify. Only EURUSD qualifies.
// Tested M30 entry (PF 1.00), ADX Daily (nuisible), EMA200 Weekly + ATR Monthly (PF 0.88) — none improved.

// --- Risk Management ---
input double RiskPercent        = 1.0;     // Risk % per trade
input double MaxSpreadPips      = 3.0;     // Max spread allowed (pips)
input int    MagicNumber        = 20260410;// Magic number (pyramid version)
input double MinRR              = 2.5;     // Minimum Risk:Reward ratio
input double MinSL_Pips         = 15.0;    // Minimum SL distance (pips) — was 10, raised to filter weak setups
input double MaxSL_Pips         = 25.0;    // Maximum SL distance (pips) — was 30, tightened (25-30 bucket PF=0.98)

// --- ANTI-MARTINGALE PYRAMID (on wins) ---
// Pyramid mode pour demarrer rapidement avec des valeurs eprouvees.
// SAFE        : L0=1.0 L1=4.0 L2=2.5 -> Net 6y +$34k / DD 26% / PF 1.89 (tradeable live)
// AGGRESSIVE  : L0=2.0 L1=7.0 L2=4.0 -> Net 6y +$109k / DD 47% / PF 1.91 (experimental)
// CUSTOM      : utilise les inputs L0/L1/L2_LotMult ci-dessous
enum PYRAMID_MODE {
   MODE_SAFE       = 0,   // SAFE: L0=1.0 L1=4.0 L2=2.5 (DD 26%, tradeable live)
   MODE_AGGRESSIVE = 1,   // AGGRESSIVE: L0=2.0 L1=7.0 L2=4.0 (DD 47%, experimental)
   MODE_CUSTOM     = 2    // CUSTOM: use L0/L1/L2_LotMult inputs
};

input bool         UsePyramid    = true;           // activer pyramid lot sizing sur wins
input PYRAMID_MODE PyramidMode   = MODE_SAFE;      // preset mode (SAFE recommande pour live)
input double       L0_LotMult    = 1.0;            // L0 multiplier (used only if MODE_CUSTOM)
input double       L1_LotMult    = 4.0;            // L1 multiplier (used only if MODE_CUSTOM)
input double       L2_LotMult    = 2.5;            // L2 multiplier (used only if MODE_CUSTOM)
input int          MaxStreakLevel = 2;             // cap du streak (2 -> 3 niveaux: L0, L1, L2)

// --- Martingale Hedge (opposite trade at X% of SL) ---
// When a trade reaches X% of its SL, open opposite direction trade.
// TP = mother SL, SL = mother entry. Reduces DD when SL is hit.
input bool         UseMartingaleHedge = true;       // Master switch for hedge
input bool         HedgeOnL0         = true;        // Hedge on L0 trades
input bool         HedgeOnL1         = true;        // Hedge on L1 trades
input bool         HedgeOnL2         = true;        // Hedge on L2 trades
input double       HedgeSL_Percent   = 75.0;        // Trigger at X% of SL distance
input double       HedgeLotMult      = 2.0;         // Hedge lot multiplier vs mother trade lot

// --- Trend Filter (H1) ---
input int    TrendEMA_Period    = 50;      // H1 EMA period for trend direction
input int    TrendBars          = 5;       // H1 EMA must slope for X bars

// --- Entry (M15) ---
input int    EntryEMA_Period    = 20;      // M15 EMA period for pullback
input int    SL_SwingBars       = 3;       // Bars to look back for SL swing
input int    RSI_Period         = 14;      // RSI period for overbought/oversold filter
input int    RSI_OB             = 70;      // RSI overbought level (don't buy above)
input int    RSI_OS             = 30;      // RSI oversold level (don't sell below)

// --- Session Filter ---
input int    LondonStartHour    = 8;       // London session start (server time)
input int    LondonEndHour      = 12;      // London session end
input int    NYStartHour        = 13;      // New York session start
input int    NYEndHour          = 17;      // New York session end

// --- Trade Management ---
input bool   UseBreakeven       = true;    // Move SL to BE
input double BE_Trigger_R       = 1.5;     // Move SL to BE after X * R (1.5 = more room)
input int    MaxTradesPerDay    = 2;       // Max trades per day

// --- Volatility Filter (ATR) ---
input bool   UseATRFilter       = true;    // Only trade when ATR > threshold
input int    ATR_Period          = 14;      // ATR period on H1
input double ATR_MinPips         = 9.0;    // Min ATR in pips — was 6, raised per analysis
input double ATR_MaxPips         = 19.0;   // Max ATR in pips — 0 wins above 19 in 2025-2026

// --- Pullback Quality Filter ---
input bool   UseEMA50DistFilter  = true;   // Block entries too far from EMA50
input double MaxEMA50DistPips    = 30.0;   // Max distance from H1 EMA50 (winners avg 23, losers avg 35)
input bool   UsePullbackSizeFilter = false; // MASTER SWITCH (bool). OFF = filter ignored regardless of ratio
input double PB_MaxRatio         = 0.70;   // Max ratio pullback/trend (only read if UsePullbackSizeFilter=true)
input bool   UseStructureFilter  = false;  // Reject if last swing H/L is broken (OFF — tested, too aggressive)
input int    StructureSwingBars  = 5;      // Bars on each side to identify swing point

// --- Day/Hour Filters ---
input bool   BlockFriday         = true;   // Do not trade on Friday
input bool   BlockHour13         = true;   // Do not trade at 13:00 (NY open chaos)
input string BlockedHours        = "13";   // Comma-separated hours to block (server time)
input bool   BlockToxicCombos    = true;   // Block worst hour+day combos from analysis
input bool   ReduceThursdayRisk  = true;   // Halve risk on Thursday (weakest day PF=1.08)
input double ThursdayRiskMult    = 0.5;    // Thursday risk multiplier (0.5 = half risk)

//+------------------------------------------------------------------+
//| GLOBALS                                                           |
//+------------------------------------------------------------------+
double     g_pipValue;
int        g_digits;
datetime   g_lastBarTime = 0;
datetime   g_currentDay  = 0;
int        g_dailyTrades = 0;

// --- Pyramid state ---
struct PyramidState {
   int    streak;          // 0 = L0 (base), 1 = L1 (after 1 win), 2 = L2 (after 2 wins)
   int    lastTicket;      // last ticket opened (to detect close)
   bool   waitingForClose; // true if a trade is in flight
   int    lastTradeLevel;  // pyramid level of the trade in flight (0/1/2)
   int    lastTradeType;   // OP_BUY or OP_SELL of the trade in flight
};
PyramidState g_pyr;

// Pyramid counters
int g_pyr_wins = 0;
int g_pyr_losses = 0;
int g_pyr_maxStreak = 0;

// --- Martingale hedge state ---
int    g_hedgeTicket = 0;       // ticket of the hedge trade (0 = no hedge active)
bool   g_hedgeActive = false;   // true if a hedge is open
int    g_hedgeMotherTicket = 0; // ticket of the mother trade being hedged

// Pyramid runtime multipliers (applied by ApplyPyramidMode())
double r_L0_LotMult = 1.0;
double r_L1_LotMult = 4.0;
double r_L2_LotMult = 2.5;

// --- Runtime params (overridden by preset) ---
double  r_MaxSpreadPips;
double  r_MinRR;
double  r_MinSL_Pips;
double  r_MaxSL_Pips;
double  r_ATR_MinPips;
double  r_ATR_MaxPips;
double  r_MaxEMA50DistPips;
double  r_PB_MaxRatio;
double  r_BE_Trigger_R;
int     r_LondonStartHour;
int     r_LondonEndHour;
int     r_NYStartHour;
int     r_NYEndHour;
bool    r_UseLondonSession;
bool    r_BlockFriday;
bool    r_BlockMonday;
bool    r_BlockToxicCombos;
int     r_BlockedHoursArr[10];
int     r_BlockedHoursCount;
bool    r_ReduceThursdayRisk;
double  r_ThursdayRiskMult;
int     r_MaxTradesPerDay;
int     r_TrendBars;
int     r_SL_SwingBars;

//+------------------------------------------------------------------+
//| APPLY PYRAMID MODE                                                |
//+------------------------------------------------------------------+
// Configure les multiplicateurs L0/L1/L2 selon le mode choisi.
// Backtests EURUSD H1 2020-2026:
//   SAFE       : Net +$34,575 / DD 26.3% / PF 1.89 (tradeable live)
//   AGGRESSIVE : Net +$109,621 / DD 47.3% / PF 1.91 (risque psychologique eleve)
//   CUSTOM     : utilise les inputs L0/L1/L2_LotMult definis par l'utilisateur
void ApplyPyramidMode() {
   if(PyramidMode == MODE_SAFE) {
      r_L0_LotMult = 1.0;
      r_L1_LotMult = 4.0;
      r_L2_LotMult = 2.5;
   }
   else if(PyramidMode == MODE_AGGRESSIVE) {
      r_L0_LotMult = 2.0;
      r_L1_LotMult = 7.0;
      r_L2_LotMult = 4.0;
   }
   else {  // MODE_CUSTOM
      r_L0_LotMult = L0_LotMult;
      r_L1_LotMult = L1_LotMult;
      r_L2_LotMult = L2_LotMult;
   }
}

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit() {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(g_digits == 3 || g_digits == 5)
      g_pipValue = Point * 10;
   else
      g_pipValue = Point;

   ApplyPreset();
   ApplyPyramidMode();

   // Initialize pyramid state
   g_pyr.streak = 0;
   g_pyr.lastTicket = 0;
   g_pyr.waitingForClose = false;
   g_pyr.lastTradeLevel = 0;
   g_pyr.lastTradeType = -1;

   string pyrModeName = "SAFE";
   if(PyramidMode == MODE_AGGRESSIVE) pyrModeName = "AGGRESSIVE";
   else if(PyramidMode == MODE_CUSTOM) pyrModeName = "CUSTOM";
   Print("EMA Pullback Pyramid v3 EA initialized | Symbol: ", Symbol(),
         " | Pyramid: ", UsePyramid ? "ON" : "OFF",
         " | Mode: ", pyrModeName,
         " | Hedge: ", UseMartingaleHedge ? "ON" : "OFF",
         " | Lots L0:", DoubleToStr(r_L0_LotMult, 2),
         " L1:", DoubleToStr(r_L1_LotMult, 2),
         " L2:", DoubleToStr(r_L2_LotMult, 2));
   Print("EMA Pullback Pyramid v2 EA | EURUSD only | H1+M15",
         " | Pip value: ", g_pipValue,
         " | SL range: ", DoubleToStr(r_MinSL_Pips, 0), "-", DoubleToStr(r_MaxSL_Pips, 0), " pips",
         " | ATR: ", UseATRFilter ? DoubleToStr(r_ATR_MinPips, 0) + "-" + DoubleToStr(r_ATR_MaxPips, 0) + " pips" : "OFF",
         " | EMA50 dist max: ", UseEMA50DistFilter ? DoubleToStr(r_MaxEMA50DistPips, 0) + " pips" : "OFF",
         " | Friday: ", r_BlockFriday ? "BLOCKED" : "allowed",
         " | Spread max: ", DoubleToStr(r_MaxSpreadPips, 1),
         " | BE trigger: ", DoubleToStr(r_BE_Trigger_R, 1), "R");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| APPLY PRESET                                                      |
//+------------------------------------------------------------------+
void ApplyPreset() {
   // Default: copy inputs to runtime
   r_MaxSpreadPips     = MaxSpreadPips;
   r_MinRR             = MinRR;
   r_MinSL_Pips        = MinSL_Pips;
   r_MaxSL_Pips        = MaxSL_Pips;
   r_ATR_MinPips       = ATR_MinPips;
   r_ATR_MaxPips       = ATR_MaxPips;
   r_MaxEMA50DistPips  = MaxEMA50DistPips;
   r_PB_MaxRatio       = PB_MaxRatio;
   r_BE_Trigger_R      = BE_Trigger_R;
   r_LondonStartHour   = LondonStartHour;
   r_LondonEndHour     = LondonEndHour;
   r_NYStartHour       = NYStartHour;
   r_NYEndHour         = NYEndHour;
   r_UseLondonSession  = true;
   r_BlockFriday       = BlockFriday;
   r_BlockMonday       = false;
   r_BlockToxicCombos  = BlockToxicCombos;
   r_ReduceThursdayRisk = ReduceThursdayRisk;
   r_ThursdayRiskMult  = ThursdayRiskMult;
   r_MaxTradesPerDay   = MaxTradesPerDay;
   r_TrendBars         = TrendBars;
   r_SL_SwingBars      = SL_SwingBars;
   r_BlockedHoursCount = 0;
   ArrayInitialize(r_BlockedHoursArr, -1);

   // --- EURUSD blocked hours (from analysis) ---
   r_BlockedHoursCount = 1;
   r_BlockedHoursArr[0] = 13;       // NY open chaos
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   Print("EMA Pullback EA removed. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick() {
   // --- Manage open trades on every tick (breakeven) ---
   ManageOpenTrades();

   // --- Martingale hedge: check if L1/L2 approaching SL ---
   CheckMartingaleHedge();

   // --- Check hedge close (reset state) ---
   CheckHedgeClose();

   // --- Pyramid: detect closed trade and update streak (tick level) ---
   CheckPyramidClose();

   // --- New bar check (entry TF) ---
   datetime currentBarTime = iTime(Symbol(), PERIOD_M15, 0);
   if(currentBarTime == g_lastBarTime) return;
   g_lastBarTime = currentBarTime;

   // --- Reset daily counter ---
   datetime today = TimeCurrent() - TimeCurrent() % 86400;
   if(today != g_currentDay) {
      g_dailyTrades = 0;
      g_currentDay = today;
   }

   // --- Pre-checks ---
   if(!IsSessionActive()) return;
   if(SpreadTooWide()) return;
   if(IsDayBlocked()) return;
   if(IsHourBlocked()) return;
   if(UseATRFilter && !IsVolatilityOK()) return;
   if(!IsEMA50DistanceOK()) return;
   if(CountOpenTrades() >= 1) return;
   if(g_dailyTrades >= r_MaxTradesPerDay) return;

   // --- Check for entry ---
   CheckEntry();
}

//+------------------------------------------------------------------+
//| SESSION FILTER                                                    |
//+------------------------------------------------------------------+
bool IsSessionActive() {
   int hour = TimeHour(TimeCurrent());
   if(r_UseLondonSession && hour >= r_LondonStartHour && hour < r_LondonEndHour) return true;
   if(hour >= r_NYStartHour && hour < r_NYEndHour) return true;
   return false;
}

//+------------------------------------------------------------------+
//| SPREAD CHECK                                                      |
//+------------------------------------------------------------------+
bool SpreadTooWide() {
   double spread = MarketInfo(Symbol(), MODE_SPREAD) * Point / g_pipValue;
   return (spread > r_MaxSpreadPips);
}

//+------------------------------------------------------------------+
//| DAY FILTER (block Friday)                                         |
//+------------------------------------------------------------------+
bool IsDayBlocked() {
   int dow = TimeDayOfWeek(TimeCurrent());
   if(r_BlockFriday && dow == 5) return true;
   if(r_BlockMonday && dow == 1) return true;
   return false;
}

//+------------------------------------------------------------------+
//| HOUR FILTER (block toxic hours)                                   |
//+------------------------------------------------------------------+
bool IsHourBlocked() {
   int hour = TimeHour(TimeCurrent());
   int dow  = TimeDayOfWeek(TimeCurrent());

   // Quick check for the main blocked hour
   if(BlockHour13 && hour == 13) return true;

   // Check preset-specific blocked hours array
   for(int i = 0; i < r_BlockedHoursCount; i++) {
      if(hour == r_BlockedHoursArr[i]) return true;
   }

   // Parse additional blocked hours from comma-separated string
   if(StringLen(BlockedHours) > 0) {
      string parts[];
      int count = StringSplit(BlockedHours, ',', parts);
      for(int i = 0; i < count; i++) {
         StringReplace(parts[i], " ", "");
         int blocked = (int)StringToInteger(parts[i]);
         if(hour == blocked) return true;
      }
   }

   // Block toxic hour+day combos (EURUSD specific)
   if(r_BlockToxicCombos) {
      if(hour == 14 && dow == 2) return true;  // 14h/Tue
      if(hour == 11 && dow == 1) return true;  // 11h/Mon
      if(hour == 14 && dow == 4) return true;  // 14h/Thu
      if(hour == 16 && dow == 1) return true;  // 16h/Mon
   }

   return false;
}

//+------------------------------------------------------------------+
//| VOLATILITY FILTER (ATR on H1)                                     |
//+------------------------------------------------------------------+
bool IsVolatilityOK() {
   double atr = iATR(Symbol(), PERIOD_H1, ATR_Period, 0);
   double atrPips = atr / g_pipValue;

   // Too calm — no momentum for pullback
   if(atrPips < r_ATR_MinPips) return false;

   // Too volatile — pullbacks become retournements
   if(r_ATR_MaxPips > 0 && atrPips > r_ATR_MaxPips) return false;

   return true;
}

//+------------------------------------------------------------------+
//| EMA50 DISTANCE FILTER — reject overextended entries              |
//| Winners avg 23 pips from EMA50, Losers avg 35 pips              |
//+------------------------------------------------------------------+
bool IsEMA50DistanceOK() {
   if(!UseEMA50DistFilter) return true;

   double ema50 = iMA(Symbol(), PERIOD_H1, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
   double price = (MarketInfo(Symbol(), MODE_BID) + MarketInfo(Symbol(), MODE_ASK)) / 2.0;
   double distPips = MathAbs(price - ema50) / g_pipValue;

   if(distPips > r_MaxEMA50DistPips) return false;

   return true;
}

//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| PULLBACK SIZE FILTER                                              |
//| Compares pullback candle sizes vs trend candle sizes              |
//| Real pullback = small candles (low conviction retracement)        |
//| Retournement  = large candles (aggressive selling/buying)         |
//+------------------------------------------------------------------+
bool IsPullbackHealthy(int direction) {
   // BUG FIX: master switch (bool) — was dead code, now actually wired
   if(!UsePullbackSizeFilter) return true;  // filter OFF by default
   if(r_PB_MaxRatio >= 1.0) return true;    // ratio 1.0 also disables

   // Measure pullback candles: bars 1-2 (the retracement toward EMA)
   double pullbackSize = 0;
   int pbCount = 0;
   for(int i = 1; i <= 3; i++) {
      double h = iHigh(Symbol(), PERIOD_M15, i);
      double l = iLow(Symbol(), PERIOD_M15, i);
      double range = h - l;
      if(range > 0) {
         pullbackSize += range;
         pbCount++;
      }
   }
   if(pbCount == 0) return true;
   double avgPullback = pullbackSize / pbCount;

   // Measure trend candles: bars 4-8 (the impulsive move before pullback)
   double trendSize = 0;
   int trCount = 0;
   for(int i = 4; i <= 8; i++) {
      double h = iHigh(Symbol(), PERIOD_M15, i);
      double l = iLow(Symbol(), PERIOD_M15, i);
      double c = iClose(Symbol(), PERIOD_M15, i);
      double o = iOpen(Symbol(), PERIOD_M15, i);
      double range = h - l;

      // Only count candles in the trend direction
      if(direction == 1 && c > o) {     // Bullish trend candles
         trendSize += range;
         trCount++;
      }
      else if(direction == -1 && c < o) { // Bearish trend candles
         trendSize += range;
         trCount++;
      }
   }
   if(trCount == 0) return true;
   double avgTrend = trendSize / trCount;

   // If pullback candles are too large relative to trend = retournement
   if(avgTrend > 0 && avgPullback / avgTrend > r_PB_MaxRatio) {
      return false; // Pullback too aggressive = likely reversal
   }

   return true;
}

//+------------------------------------------------------------------+
//| STRUCTURE FILTER — Check if last swing H/L is intact             |
//| Buy: last swing low must NOT be broken (structure still bullish)  |
//| Sell: last swing high must NOT be broken (structure still bearish)|
//+------------------------------------------------------------------+
bool IsStructureIntact(int direction) {
   if(!UseStructureFilter) return true;

   int lookback = 30; // Scan last 30 bars for swing points

   if(direction == 1) {
      // BULLISH: find last swing low, check it's not broken
      for(int i = StructureSwingBars + 1; i < lookback; i++) {
         double low_i = iLow(Symbol(), PERIOD_M15, i);
         bool isSwingLow = true;

         for(int j = 1; j <= StructureSwingBars; j++) {
            if(iLow(Symbol(), PERIOD_M15, i - j) < low_i ||
               iLow(Symbol(), PERIOD_M15, i + j) < low_i) {
               isSwingLow = false;
               break;
            }
         }

         if(isSwingLow) {
            // Found swing low — check if any recent bar closed below it
            for(int k = 1; k < i; k++) {
               if(iClose(Symbol(), PERIOD_M15, k) < low_i) {
                  return false; // Structure broken — swing low violated
               }
            }
            return true; // Swing low intact — safe to buy
         }
      }
   }
   else if(direction == -1) {
      // BEARISH: find last swing high, check it's not broken
      for(int i = StructureSwingBars + 1; i < lookback; i++) {
         double high_i = iHigh(Symbol(), PERIOD_M15, i);
         bool isSwingHigh = true;

         for(int j = 1; j <= StructureSwingBars; j++) {
            if(iHigh(Symbol(), PERIOD_M15, i - j) > high_i ||
               iHigh(Symbol(), PERIOD_M15, i + j) > high_i) {
               isSwingHigh = false;
               break;
            }
         }

         if(isSwingHigh) {
            // Found swing high — check if any recent bar closed above it
            for(int k = 1; k < i; k++) {
               if(iClose(Symbol(), PERIOD_M15, k) > high_i) {
                  return false; // Structure broken — swing high violated
               }
            }
            return true; // Swing high intact — safe to sell
         }
      }
   }

   return true; // No swing found, allow trade
}

//+------------------------------------------------------------------+
//| COUNT OPEN TRADES                                                 |
//+------------------------------------------------------------------+
// Count only signal+reverse trades, NOT hedges (MagicNumber+1)
// Hedges are "passengers" of the mother trade, not standalone trades
int CountOpenTrades() {
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) {
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| GET H1 TREND DIRECTION                                            |
//| Returns: 1 = bullish, -1 = bearish, 0 = no trend                 |
//+------------------------------------------------------------------+
int GetTrendDirection() {
   double ema_now  = iMA(Symbol(), PERIOD_H1, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
   double ema_prev = iMA(Symbol(), PERIOD_H1, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, r_TrendBars);
   double close_tf = iClose(Symbol(), PERIOD_H1, 0);

   // Bullish: price above EMA AND EMA rising
   if(close_tf > ema_now && ema_now > ema_prev)
      return 1;

   // Bearish: price below EMA AND EMA falling
   if(close_tf < ema_now && ema_now < ema_prev)
      return -1;

   return 0;
}

//+------------------------------------------------------------------+
//| CHECK FOR PULLBACK ENTRY ON M15                                   |
//+------------------------------------------------------------------+
void CheckEntry() {
   int trend = GetTrendDirection();
   if(trend == 0) return;

   // Pullback quality: reject if pullback candles are too large vs trend
   if(!IsPullbackHealthy(trend)) return;

   // Structure check: reject if last swing H/L has been broken
   if(!IsStructureIntact(trend)) return;

   double ema20 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);

   // Last closed bar (bar 1)
   double open1  = iOpen(Symbol(), PERIOD_M15, 1);
   double close1 = iClose(Symbol(), PERIOD_M15, 1);
   double high1  = iHigh(Symbol(), PERIOD_M15, 1);
   double low1   = iLow(Symbol(), PERIOD_M15, 1);

   // Previous bar (bar 2) — must have touched/crossed EMA
   double open2  = iOpen(Symbol(), PERIOD_M15, 2);
   double close2 = iClose(Symbol(), PERIOD_M15, 2);
   double low2   = iLow(Symbol(), PERIOD_M15, 2);
   double high2  = iHigh(Symbol(), PERIOD_M15, 2);

   // Price action: body sizes
   double body1  = MathAbs(close1 - open1);
   double range1 = high1 - low1;
   double body2  = MathAbs(close2 - open2);

   double bid = MarketInfo(Symbol(), MODE_BID);
   double ask = MarketInfo(Symbol(), MODE_ASK);

   // RSI filter
   double rsi = iRSI(Symbol(), PERIOD_M15, RSI_Period, PRICE_CLOSE, 1);

   // ============ BULLISH PULLBACK ============
   if(trend == 1) {
      if(rsi > RSI_OB) return;  // Don't buy when overbought
      // Bar 2 must have dipped to or below EMA20 (pullback)
      double ema20_bar2 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 2);
      if(low2 > ema20_bar2) return;  // No pullback to EMA

      // Bar 1 must close above EMA20 (rejection/bounce)
      if(close1 <= ema20) return;
      // Bar 1 must be bullish
      if(close1 <= open1) return;
      // Price action: strong body (>60% of range) and stronger than pullback bar
      if(range1 > 0 && body1 / range1 < 0.6) return;
      if(body1 <= body2) return;

      // Calculate SL: lowest low of last r_SL_SwingBars bars
      double sl = low1;
      for(int i = 1; i <= r_SL_SwingBars; i++) {
         double l = iLow(Symbol(), PERIOD_M15, i);
         if(l < sl) sl = l;
      }
      sl = sl - 2 * g_pipValue;  // Buffer

      double slDist = (ask - sl) / g_pipValue;
      if(slDist < r_MinSL_Pips || slDist > r_MaxSL_Pips) return;

      double tp = ask + (ask - sl) * r_MinRR;

      ExecuteTrade(OP_BUY, ask, sl, tp, "EMA Pullback Buy");
   }

   // ============ BEARISH PULLBACK ============
   if(trend == -1) {
      if(rsi < RSI_OS) return;  // Don't sell when oversold
      // Bar 2 must have spiked to or above EMA20 (pullback)
      double ema20_bar2 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 2);
      if(high2 < ema20_bar2) return;  // No pullback to EMA

      // Bar 1 must close below EMA20 (rejection)
      if(close1 >= ema20) return;
      // Bar 1 must be bearish
      if(close1 >= open1) return;
      // Price action: strong body (>60% of range) and stronger than pullback bar
      if(range1 > 0 && body1 / range1 < 0.6) return;
      if(body1 <= body2) return;

      // Calculate SL: highest high of last r_SL_SwingBars bars
      double sl = high1;
      for(int i = 1; i <= r_SL_SwingBars; i++) {
         double h = iHigh(Symbol(), PERIOD_M15, i);
         if(h > sl) sl = h;
      }
      sl = sl + 2 * g_pipValue;  // Buffer

      double slDist = (sl - bid) / g_pipValue;
      if(slDist < r_MinSL_Pips || slDist > r_MaxSL_Pips) return;

      double tp = bid - (sl - bid) * r_MinRR;

      ExecuteTrade(OP_SELL, bid, sl, tp, "EMA Pullback Sell");
   }
}

//+------------------------------------------------------------------+
//| CHECK PYRAMID CLOSE (tick level) -> update streak on WIN/LOSS     |
//| + trigger reverse trade on L0 SL                                  |
//+------------------------------------------------------------------+
void CheckPyramidClose() {
   if(!UsePyramid) return;
   if(!g_pyr.waitingForClose) return;
   if(g_pyr.lastTicket <= 0) { g_pyr.waitingForClose = false; return; }

   // Check if ticket still open
   bool stillOpen = false;
   for(int i = 0; i < OrdersTotal(); i++) {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         if(OrderTicket() == g_pyr.lastTicket && OrderSymbol() == Symbol())
            stillOpen = true;
   }
   if(stillOpen) return;

   // Trade closed - find in history
   for(int i = OrdersHistoryTotal() - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderTicket() != g_pyr.lastTicket || OrderSymbol() != Symbol()) continue;

      double pnl = OrderProfit() + OrderSwap() + OrderCommission();

      g_pyr.waitingForClose = false;
      g_pyr.lastTicket = 0;

      // --- Update pyramid streak (hedges don't pass here, only signal trades) ---
      if(pnl > 0) {
         // WIN -> pyramid up (with cap)
         int oldStreak = g_pyr.streak;
         g_pyr_wins++;
         g_pyr.streak++;
         if(g_pyr.streak > MaxStreakLevel) g_pyr.streak = MaxStreakLevel;
         if(g_pyr.streak > g_pyr_maxStreak) g_pyr_maxStreak = g_pyr.streak;
         double nextMult = (g_pyr.streak == 0) ? r_L0_LotMult :
                           (g_pyr.streak == 1) ? r_L1_LotMult : r_L2_LotMult;
         Print("PYRAMID WIN pnl=", DoubleToStr(pnl, 2),
               " | streak ", oldStreak, " -> ", g_pyr.streak,
               " | next lot x", DoubleToStr(nextMult, 2));
      } else {
         // LOSS -> reset streak
         int oldStreak = g_pyr.streak;
         g_pyr_losses++;
         g_pyr.streak = 0;
         Print("PYRAMID LOSS pnl=", DoubleToStr(pnl, 2),
               " | streak reset (was ", oldStreak, ")");
      }
      return;
   }
}

//+------------------------------------------------------------------+
//| MARTINGALE HEDGE — open opposite trade when L1/L2 near SL        |
//| Trigger: mother trade at X% of SL distance (default 75%)         |
//| Hedge: opposite direction, configurable lot multiplier            |
//|   TP = mother's SL level                                          |
//|   SL = mother's entry level                                       |
//+------------------------------------------------------------------+
void CheckMartingaleHedge() {
   if(!UseMartingaleHedge) return;
   if(g_hedgeActive) return;  // already hedged this trade

   // Only hedge trades that are in flight and enabled for their level
   if(!g_pyr.waitingForClose) return;
   if(g_pyr.lastTradeLevel == 0 && !HedgeOnL0) return;
   if(g_pyr.lastTradeLevel == 1 && !HedgeOnL1) return;
   if(g_pyr.lastTradeLevel == 2 && !HedgeOnL2) return;

   // Find the mother trade
   int motherTicket = g_pyr.lastTicket;
   if(motherTicket <= 0) return;

   bool found = false;
   for(int i = 0; i < OrdersTotal(); i++) {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) {
         if(OrderTicket() == motherTicket && OrderSymbol() == Symbol()) {
            found = true;
            break;
         }
      }
   }
   if(!found) return;

   // Get mother trade info
   int    motherType  = OrderType();
   double motherOpen  = OrderOpenPrice();
   double motherSL    = OrderStopLoss();
   double motherLot   = OrderLots();

   if(motherSL == 0) return;

   double slDistance = MathAbs(motherOpen - motherSL);
   if(slDistance <= 0) return;

   // Check if price has reached X% of SL distance
   double currentPrice;
   double priceMoveTowardSL;

   if(motherType == OP_BUY) {
      currentPrice = MarketInfo(Symbol(), MODE_BID);
      priceMoveTowardSL = motherOpen - currentPrice;
   } else {
      currentPrice = MarketInfo(Symbol(), MODE_ASK);
      priceMoveTowardSL = currentPrice - motherOpen;
   }

   if(priceMoveTowardSL <= 0) return;  // not losing

   double percentToSL = (priceMoveTowardSL / slDistance) * 100.0;
   if(percentToSL < HedgeSL_Percent) return;  // not at threshold yet

   // === TRIGGER HEDGE ===
   double hedgeLot = NormalizeDouble(motherLot * HedgeLotMult, 2);
   double minLot = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot = MarketInfo(Symbol(), MODE_MAXLOT);
   if(hedgeLot < minLot) hedgeLot = minLot;
   if(hedgeLot > maxLot) hedgeLot = maxLot;

   int    hedgeType;
   double hedgePrice, hedgeSL, hedgeTP;

   if(motherType == OP_BUY) {
      hedgeType  = OP_SELL;
      hedgePrice = MarketInfo(Symbol(), MODE_BID);
      hedgeSL    = NormalizeDouble(motherOpen, g_digits);    // SL = mother entry
      hedgeTP    = NormalizeDouble(motherSL, g_digits);      // TP = mother SL
   } else {
      hedgeType  = OP_BUY;
      hedgePrice = MarketInfo(Symbol(), MODE_ASK);
      hedgeSL    = NormalizeDouble(motherOpen, g_digits);    // SL = mother entry
      hedgeTP    = NormalizeDouble(motherSL, g_digits);      // TP = mother SL
   }

   hedgePrice = NormalizeDouble(hedgePrice, g_digits);
   string comment = "HEDGE|L" + IntegerToString(g_pyr.lastTradeLevel)
                   + "|x" + DoubleToStr(HedgeLotMult, 1);

   int ticket = OrderSend(Symbol(), hedgeType, hedgeLot, hedgePrice, 3,
                          hedgeSL, hedgeTP, comment, MagicNumber + 1, 0, clrOrange);

   if(ticket > 0) {
      g_hedgeTicket = ticket;
      g_hedgeActive = true;
      g_hedgeMotherTicket = motherTicket;
      Print("HEDGE OPENED: L", g_pyr.lastTradeLevel,
            " at ", DoubleToStr(percentToSL, 1), "% of SL",
            " | ", hedgeType == OP_BUY ? "BUY" : "SELL",
            " | lot=", DoubleToStr(hedgeLot, 2),
            " | mother lot=", DoubleToStr(motherLot, 2));
   } else {
      Print("HEDGE FAILED: error=", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| CHECK HEDGE CLOSE — reset hedge state when hedge trade closes    |
//+------------------------------------------------------------------+
void CheckHedgeClose() {
   if(!g_hedgeActive) return;

   bool stillOpen = false;
   for(int i = 0; i < OrdersTotal(); i++) {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         if(OrderTicket() == g_hedgeTicket && OrderSymbol() == Symbol())
            stillOpen = true;
   }

   if(!stillOpen) {
      for(int i = OrdersHistoryTotal() - 1; i >= 0; i--) {
         if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
         if(OrderTicket() != g_hedgeTicket || OrderSymbol() != Symbol()) continue;
         double pnl = OrderProfit() + OrderSwap() + OrderCommission();
         Print("HEDGE CLOSED: pnl=", DoubleToStr(pnl, 2), pnl > 0 ? " [WIN]" : " [LOSS]");
         break;
      }
      g_hedgeActive = false;
      g_hedgeTicket = 0;
      g_hedgeMotherTicket = 0;
   }
}

//+------------------------------------------------------------------+
//| EXECUTE TRADE                                                     |
//+------------------------------------------------------------------+
void ExecuteTrade(int type, double price, double sl, double tp, string comment) {
   double slDist = MathAbs(price - sl);

   // Reduce risk on Thursday (weakest day PF=1.08)
   double riskMult = 1.0;
   if(r_ReduceThursdayRisk && TimeDayOfWeek(TimeCurrent()) == 4) {
      riskMult = r_ThursdayRiskMult;
      comment = comment + "|THU_REDUCED";
   }

   // Pyramid multiplier based on current streak level
   double pyrMult = 1.0;
   if(UsePyramid) {
      if(g_pyr.streak == 0)      pyrMult = r_L0_LotMult;
      else if(g_pyr.streak == 1) pyrMult = r_L1_LotMult;
      else                       pyrMult = r_L2_LotMult;
      riskMult *= pyrMult;
      comment = comment + "|L" + IntegerToString(g_pyr.streak);
   }

   double lotSize = CalculateLotSize(slDist, riskMult);

   if(lotSize <= 0) {
      Print("Lot size invalid: ", lotSize);
      return;
   }

   price = NormalizeDouble(price, g_digits);
   sl    = NormalizeDouble(sl, g_digits);
   tp    = NormalizeDouble(tp, g_digits);

   // Store initial risk in comment
   string fullComment = comment + "|R=" + DoubleToStr(slDist, g_digits);

   int ticket = OrderSend(Symbol(), type, lotSize, price, 3, sl, tp,
                           fullComment, MagicNumber, 0,
                           type == OP_BUY ? clrGreen : clrRed);

   if(ticket < 0) {
      Print("OrderSend failed: ", GetLastError(),
            " | Type: ", type,
            " | Price: ", price,
            " | SL: ", sl,
            " | TP: ", tp,
            " | Lots: ", lotSize);
   }
   else {
      g_dailyTrades++;
      // Track ticket for pyramid close detection
      g_pyr.lastTicket = ticket;
      g_pyr.waitingForClose = true;
      g_pyr.lastTradeLevel = g_pyr.streak;
      g_pyr.lastTradeType = type;
      Print("Trade opened #", ticket,
            " | ", comment,
            " | L", g_pyr.streak,
            " | Lots: ", lotSize,
            " | SL: ", sl,
            " | TP: ", tp,
            " | RR: ", DoubleToStr(MathAbs(tp - price) / slDist, 1));
   }
}

//+------------------------------------------------------------------+
//| CALCULATE LOT SIZE (Risk-based)                                  |
//+------------------------------------------------------------------+
double CalculateLotSize(double slDistance, double riskMultiplier = 1.0) {
   if(slDistance <= 0) return 0;

   double riskMoney = AccountBalance() * RiskPercent / 100.0 * riskMultiplier;
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   double tickSize  = MarketInfo(Symbol(), MODE_TICKSIZE);

   if(tickValue == 0 || tickSize == 0) return 0;

   double slTicks = slDistance / tickSize;
   double lotSize = riskMoney / (slTicks * tickValue);

   double minLot  = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot  = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);

   lotSize = MathFloor(lotSize / lotStep) * lotStep;
   lotSize = MathMax(minLot, MathMin(maxLot, lotSize));

   return NormalizeDouble(lotSize, 2);
}

//+------------------------------------------------------------------+
//| MANAGE OPEN TRADES (Breakeven)                                   |
//+------------------------------------------------------------------+
void ManageOpenTrades() {
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();

      // Get initial risk from comment
      string comment = OrderComment();
      double riskDist = GetInitialRisk(comment, MathAbs(openPrice - currentSL));
      if(riskDist <= 0) continue;

      if(OrderType() == OP_BUY) {
         double currentPrice = MarketInfo(Symbol(), MODE_BID);
         double profit = currentPrice - openPrice;

         // Breakeven at BE_Trigger_R (default 1.5R — gives trade more room)
         if(UseBreakeven && profit >= riskDist * r_BE_Trigger_R && currentSL < openPrice) {
            double beSL = openPrice + 1 * g_pipValue;
            if(!OrderModify(OrderTicket(), openPrice, NormalizeDouble(beSL, g_digits),
                           OrderTakeProfit(), 0, clrYellow))
               Print("BE modify failed: ", GetLastError());
         }
      }
      else if(OrderType() == OP_SELL) {
         double currentPrice = MarketInfo(Symbol(), MODE_ASK);
         double profit = openPrice - currentPrice;

         // Breakeven at BE_Trigger_R
         if(UseBreakeven && profit >= riskDist * r_BE_Trigger_R && currentSL > openPrice) {
            double beSL = openPrice - 1 * g_pipValue;
            if(!OrderModify(OrderTicket(), openPrice, NormalizeDouble(beSL, g_digits),
                           OrderTakeProfit(), 0, clrYellow))
               Print("BE modify failed: ", GetLastError());
         }
      }
   }
}

//+------------------------------------------------------------------+
//| GET INITIAL RISK from order comment                              |
//+------------------------------------------------------------------+
double GetInitialRisk(string comment, double fallback) {
   int pos = StringFind(comment, "|R=");
   if(pos < 0) return fallback;
   string rStr = StringSubstr(comment, pos + 3);
   double r = StringToDouble(rStr);
   return (r > 0) ? r : fallback;
}
//+------------------------------------------------------------------+
